"""MindCare AI — accessible cognitive practice and caregiver support.

Educational, non-diagnostic mini project. No clinical inference is made from scores.
"""
from __future__ import annotations

import io
import hashlib
import hmac
import ipaddress
import time
import os
import random
import re
import secrets
import json
import smtplib
import ssl
from email.message import EmailMessage
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from functools import wraps
from zoneinfo import ZoneInfo
from statistics import mean

from flask import (Flask, abort, flash, g, jsonify, redirect, render_template,
                   request, send_file, session, url_for)
from flask_sqlalchemy import SQLAlchemy
from authlib.integrations.flask_client import OAuth
from authlib.integrations.base_client.errors import OAuthError
from sqlalchemy.exc import IntegrityError
from sqlalchemy import UniqueConstraint, func, or_, and_
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.middleware.proxy_fix import ProxyFix
from patient_labels import PATIENT_LABELS

app = Flask(__name__)
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///mindcare_local.db")
if (DATABASE_URL.startswith("postgres") or os.getenv("SECURE_COOKIES") == "1") and not os.getenv("SECRET_KEY"):
    raise RuntimeError("SECRET_KEY is required for production/database-backed deployment")
app.config.update(
    SECRET_KEY=os.getenv("SECRET_KEY", "development-only-change-me"),
    SQLALCHEMY_DATABASE_URI=(DATABASE_URL.replace("postgres://", "postgresql://", 1).replace("postgresql://", "postgresql+psycopg2://", 1)),
    SQLALCHEMY_TRACK_MODIFICATIONS=False,
    SQLALCHEMY_ENGINE_OPTIONS={"pool_pre_ping": True, "pool_recycle": 280},
    MAX_CONTENT_LENGTH=2 * 1024 * 1024,
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=os.getenv("SECURE_COOKIES", "0") == "1" or bool(os.getenv("RENDER_EXTERNAL_URL")),
    PERMANENT_SESSION_LIFETIME=timedelta(days=7),
)
# Render terminates HTTPS and provides a forwarded client IP. Only its final
# proxy hop is trusted; direct localhost requests ignore spoofed headers.
if os.getenv("RENDER_EXTERNAL_URL", "").startswith("https://"):
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1)

db = SQLAlchemy(app)

# OAuth client credentials and Firebase service-account credentials are secrets
# configured in Render. Never write them in source control or browser templates.
oauth = OAuth(app)
GOOGLE_OAUTH_READY = all(os.getenv(k) for k in (
    "GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET", "GOOGLE_REDIRECT_URI"))
if GOOGLE_OAUTH_READY:
    oauth.register(
        name="google",
        client_id=os.environ["GOOGLE_CLIENT_ID"],
        client_secret=os.environ["GOOGLE_CLIENT_SECRET"],
        server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
        client_kwargs={"scope": "openid profile email"},
    )


def firebase_phone_ready():
    return all(os.getenv(k) for k in (
        "FIREBASE_API_KEY", "FIREBASE_AUTH_DOMAIN", "FIREBASE_PROJECT_ID",
        "FIREBASE_APP_ID", "FIREBASE_SERVICE_ACCOUNT_JSON"))


def firebase_public_config():
    if not firebase_phone_ready():
        return None
    return {
        "apiKey": os.environ["FIREBASE_API_KEY"],
        "authDomain": os.environ["FIREBASE_AUTH_DOMAIN"],
        "projectId": os.environ["FIREBASE_PROJECT_ID"],
        "appId": os.environ["FIREBASE_APP_ID"],
    }




class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(90), nullable=False)
    email = db.Column(db.String(180), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(16), nullable=False)
    age = db.Column(db.Integer, nullable=True)
    region = db.Column(db.String(80), nullable=True)
    invite_code = db.Column(db.String(16), unique=True, index=True)
    created_at = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class AuthAttempt(db.Model):
    """Shared throttle counters: never store raw client IPs or email addresses."""
    __tablename__ = "auth_attempt"
    bucket_hash = db.Column(db.String(64), primary_key=True)
    attempts = db.Column(db.Integer, nullable=False, default=0)
    last_failure_epoch = db.Column(db.BigInteger, nullable=False)


class PasswordRecovery(db.Model):
    """Short-lived, single-use codes; raw codes are never persisted."""
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    code_hash = db.Column(db.String(64), nullable=False, unique=True, index=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False,
                           default=lambda: datetime.now(timezone.utc))
    expires_at = db.Column(db.DateTime(timezone=True), nullable=False)
    consumed_at = db.Column(db.DateTime(timezone=True), nullable=True)


class ExternalIdentity(db.Model):
    """Trusted external subject, never an email/phone guess or a client-supplied UID."""
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    provider = db.Column(db.String(24), nullable=False)
    subject = db.Column(db.String(180), nullable=False)
    label = db.Column(db.String(180), nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    __table_args__ = (
        UniqueConstraint("provider", "subject", name="uq_external_provider_subject"),
        UniqueConstraint("user_id", "provider", name="uq_one_identity_per_provider"),
    )


class PendingIdentity(db.Model):
    """Short-lived server-side state for choosing patient/caregiver after verification."""
    token_hash = db.Column(db.String(64), primary_key=True)
    provider = db.Column(db.String(24), nullable=False)
    subject = db.Column(db.String(180), nullable=False)
    email = db.Column(db.String(180), nullable=True)
    name = db.Column(db.String(90), nullable=True)
    label = db.Column(db.String(180), nullable=True)
    expires_at = db.Column(db.DateTime(timezone=True), nullable=False)


class CareLink(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    caregiver_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    patient_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    status = db.Column(db.String(12), nullable=False, default="pending")
    __table_args__ = (UniqueConstraint("caregiver_id", "patient_id", name="uq_care_link"),)


class GameResult(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    patient_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    game_type = db.Column(db.String(30), nullable=False)
    score = db.Column(db.Integer, nullable=False)
    mistakes = db.Column(db.Integer, default=0)
    duration_seconds = db.Column(db.Integer, default=0)
    difficulty = db.Column(db.Integer, default=1)
    played_at = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True)


class Reminder(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    patient_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    created_by = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    title = db.Column(db.String(110), nullable=False)
    category = db.Column(db.String(24), nullable=False)
    scheduled_time = db.Column(db.String(5), nullable=False)
    on_date = db.Column(db.Date, nullable=True)  # null means repeat every day
    notes = db.Column(db.String(240), nullable=True)
    active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class ReminderCheck(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    reminder_id = db.Column(db.Integer, db.ForeignKey("reminder.id"), nullable=False)
    checked_date = db.Column(db.Date, nullable=False)
    checked_at = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    __table_args__ = (UniqueConstraint("reminder_id", "checked_date", name="uq_reminder_day"),)


class FamilyMember(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    patient_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    name = db.Column(db.String(90), nullable=False)
    relation = db.Column(db.String(55), nullable=False)
    image_bytes = db.Column(db.LargeBinary, nullable=False)
    mime_type = db.Column(db.String(24), nullable=False)


class WellbeingCheck(db.Model):
    """Voluntary daily check-in; a request for support is not an automatic alert."""
    id = db.Column(db.Integer, primary_key=True)
    patient_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    checked_date = db.Column(db.Date, nullable=False)
    feeling = db.Column(db.String(18), nullable=False)
    note = db.Column(db.String(180), nullable=False, default="")
    checked_at = db.Column(db.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    __table_args__ = (UniqueConstraint("patient_id", "checked_date", name="uq_patient_daily_wellbeing"),)


class CaregiverSupportReview(db.Model):
    """Private caregiver acknowledgement of a patient's voluntary need-help check-in.

    This is NOT a delivered notification, emergency response, or clinical assessment.
    Acknowledging does not message or notify the patient.
    """
    id = db.Column(db.Integer, primary_key=True)
    caregiver_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    checkin_id = db.Column(db.Integer, db.ForeignKey("wellbeing_check.id"), nullable=False, index=True)
    reviewed_at = db.Column(db.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    __table_args__ = (UniqueConstraint("caregiver_id", "checkin_id", name="uq_caregiver_support_review"),)


class EmergencyContact(db.Model):
    """Patient-controlled dial shortcuts. The service does not call or SMS anyone."""
    id = db.Column(db.Integer, primary_key=True)
    patient_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    name = db.Column(db.String(90), nullable=False)
    relation = db.Column(db.String(55), nullable=False)
    phone = db.Column(db.String(18), nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))


class PatientPreference(db.Model):
    patient_id = db.Column(db.Integer, db.ForeignKey("user.id"), primary_key=True)
    language = db.Column(db.String(2), nullable=False, default="en")
    large_text = db.Column(db.Boolean, nullable=False, default=False)
    high_contrast = db.Column(db.Boolean, nullable=False, default=False)
    reduced_motion = db.Column(db.Boolean, nullable=False, default=False)


class PatientViewMode(db.Model):
    """Separate table avoids modifying existing production preference columns."""
    patient_id = db.Column(db.Integer, db.ForeignKey("user.id"), primary_key=True)
    simplified = db.Column(db.Boolean, nullable=False, default=False)


class VideoCall(db.Model):
    """Short-lived private WebRTC signaling session. No audio/video is stored."""
    id = db.Column(db.String(64), primary_key=True)
    patient_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    caregiver_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    initiator_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    status = db.Column(db.String(14), nullable=False, default="ringing")
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    expires_at = db.Column(db.DateTime(timezone=True), nullable=False)


class VideoSignal(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    call_id = db.Column(db.String(64), db.ForeignKey("video_call.id"), nullable=False, index=True)
    sender_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    kind = db.Column(db.String(12), nullable=False)
    payload = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))


GAMES = {
    "cards": ("Memory card matching", "Match pairs of familiar symbols", "🃏"),
    "words": ("Word recall", "Remember a few friendly words", "💬"),
    "numbers": ("Number sequence", "Remember and repeat numbers", "🔢"),
    "pictures": ("Picture recognition", "Recognise everyday objects", "🍊"),
    "puzzle": ("Picture puzzle", "Put a picture's pieces in order", "🧩"),
    "family": ("Family memory", "Practise names of your loved ones", "💛"),
}
CATEGORIES = {"medicine": "Medicine", "meal": "Meal", "appointment": "Appointment", "activity": "Activity", "family": "Family event"}
LEVEL_NAMES = {1: "Gentle", 2: "Growing", 3: "Challenge"}


FEELINGS = {"happy": "Happy", "okay": "Okay", "tired": "Tired", "need_help": "Need support"}
LANGUAGE_LABELS = {"en": "English", "hi": "हिन्दी", "kn": "ಕನ್ನಡ"}
# These translations cover the new patient pages and common patient navigation.
# Existing game content and speech instructions remain primarily in English.
PATIENT_TEXT = {
    "en": {
        "overview": "Overview", "games": "Brain games", "reminders": "Reminders", "people": "My people",
        "help": "Help & contacts", "settings": "My settings", "today": "Today, at your own pace",
        "today_sub": "You are in your MindCare space. Here is your day.", "my_name": "Your name",
        "local_time": "Local time in India", "next_step": "Your next little step",
        "no_next_step": "No more reminders scheduled today. Take your time.", "meet_people": "Familiar faces",
        "no_people": "Family photos will appear here when added.", "checkin": "How are you feeling today?",
        "checkin_sub": "Choose how you feel. You can change it later today.", "happy": "Happy", "okay": "Okay",
        "tired": "Tired", "need_help": "Need support", "note": "Something you want to share (optional)",
        "save_checkin": "Save today's check-in", "saved_checkin": "Today's check-in is saved",
        "support_hint": "If you need help now, please use Help & contacts to call someone. This check-in does not send an alert.",
        "help_title": "Help is close by", "help_sub": "Choose a trusted person to call, or dial emergency services.",
        "contacts": "My trusted phone contacts", "contact_name": "Name", "relationship": "Relationship",
        "phone": "Phone number", "add_contact": "Add trusted contact", "remove": "Remove",
        "call": "Call", "no_contacts": "No phone contacts added yet. Add someone you trust.",
        "india_emergency": "India emergency number", "emergency_note": "For emergencies in India, call 112. The website cannot place a call automatically or send your location.",
        "caregivers": "My approved caregivers", "no_caregivers": "You have no approved caregivers yet.",
        "video_call": "Start video call", "help_disclaimer": "Tapping Call opens your device's dialer. A phone or calling service is required. If you are in immediate danger, contact local emergency services.",
        "settings_title": "Make MindCare comfortable", "settings_sub": "Choose what is easiest for you to see and use.",
        "language": "Dashboard language", "large_text": "Larger text", "high_contrast": "Higher contrast",
        "reduced_motion": "Reduce animations", "save_settings": "Save my settings",
        "language_note": "Patient pages and core game instructions are available in English, Hindi and Kannada. Spoken voices depend on your device.",
        "quick_help": "I need help", "view_today": "My day", "open_settings": "Display settings"
    },
    "hi": {
        "overview":"सारांश","games":"दिमागी खेल","reminders":"याद दिलाने वाली बातें","people":"मेरे अपने",
        "help":"मदद और संपर्क","settings":"मेरी सेटिंग","today":"आज का दिन, आराम से",
        "today_sub":"आप अपने माइंडकेयर पेज पर हैं। यह आपका दिन है।","my_name":"आपका नाम",
        "local_time":"भारत में समय","next_step":"आपका अगला काम","no_next_step":"आज कोई और रिमाइंडर नहीं है। आराम करें।",
        "meet_people":"परिचित चेहरे","no_people":"परिवार की तस्वीरें यहाँ दिखाई देंगी।",
        "checkin":"आज आप कैसा महसूस कर रहे हैं?","checkin_sub":"अपनी भावना चुनें। आप इसे आज बदल सकते हैं।",
        "happy":"खुश","okay":"ठीक हूँ","tired":"थका हुआ","need_help":"मदद चाहिए",
        "note":"कुछ कहना चाहते हैं? (वैकल्पिक)","save_checkin":"आज की स्थिति सहेजें","saved_checkin":"आज की स्थिति सहेजी गई",
        "support_hint":"अभी मदद चाहिए तो संपर्क पेज से कॉल करें। यह फॉर्म अपने आप सूचना नहीं भेजता।",
        "help_title":"मदद पास है","help_sub":"किसी भरोसेमंद व्यक्ति या आपातकालीन सेवा को कॉल करें।",
        "contacts":"भरोसेमंद फ़ोन संपर्क","contact_name":"नाम","relationship":"रिश्ता","phone":"फ़ोन नंबर",
        "add_contact":"संपर्क जोड़ें","remove":"हटाएँ","call":"कॉल करें",
        "no_contacts":"अभी कोई संपर्क नहीं जोड़ा है।","india_emergency":"भारत का आपातकालीन नंबर",
        "emergency_note":"भारत में आपातकाल के लिए 112 डायल करें। वेबसाइट खुद कॉल नहीं करती या स्थान नहीं भेजती।",
        "caregivers":"मेरे स्वीकृत देखभालकर्ता","no_caregivers":"अभी कोई स्वीकृत देखभालकर्ता नहीं है।",
        "video_call":"वीडियो कॉल","help_disclaimer":"कॉल दबाने से फ़ोन का डायलर खुलेगा। तत्काल खतरे में स्थानीय आपातकालीन सेवाओं से संपर्क करें।",
        "settings_title":"माइंडकेयर को आरामदायक बनाएं","settings_sub":"पढ़ने और उपयोग करने की सुविधा चुनें।",
        "language":"डैशबोर्ड की भाषा","large_text":"बड़े अक्षर","high_contrast":"अधिक कंट्रास्ट",
        "reduced_motion":"कम एनिमेशन","save_settings":"सेटिंग सहेजें",
        "language_note":"मरीज के पेज और खेल के मुख्य निर्देश हिन्दी में उपलब्ध हैं। आवाज़ आपके डिवाइस पर निर्भर करती है।",
        "quick_help":"मुझे मदद चाहिए","view_today":"मेरा दिन","open_settings":"दिखावट बदलें"
    },
    "kn": {
        "overview":"ಒಟ್ಟಾರೆ ಮಾಹಿತಿ","games":"ಮೆದುಳಿನ ಆಟಗಳು","reminders":"ಜ್ಞಾಪನೆಗಳು","people":"ನನ್ನ ಕುಟುಂಬ",
        "help":"ಸಹಾಯ ಮತ್ತು ಸಂಪರ್ಕಗಳು","settings":"ನನ್ನ ಸೆಟ್ಟಿಂಗ್‌ಗಳು","today":"ಇಂದಿನ ದಿನ, ನಿಧಾನವಾಗಿ",
        "today_sub":"ಇದು ನಿಮ್ಮ ಮೈಂಡ್‌ಕೇರ್ ಪುಟ. ಇದು ನಿಮ್ಮ ದಿನ.","my_name":"ನಿಮ್ಮ ಹೆಸರು",
        "local_time":"ಭಾರತದ ಸಮಯ","next_step":"ನಿಮ್ಮ ಮುಂದಿನ ಕೆಲಸ","no_next_step":"ಇಂದು ಬೇರೆ ಜ್ಞಾಪನೆಗಳಿಲ್ಲ. ಆರಾಮವಾಗಿರಿ.",
        "meet_people":"ಪರಿಚಿತ ಮುಖಗಳು","no_people":"ಕುಟುಂಬದ ಚಿತ್ರಗಳು ಇಲ್ಲಿ ಕಾಣಿಸುತ್ತವೆ.",
        "checkin":"ಇಂದು ನಿಮಗೆ ಹೇಗನಿಸುತ್ತಿದೆ?","checkin_sub":"ನಿಮ್ಮ ಭಾವನೆ ಆಯ್ಕೆ ಮಾಡಿ. ನಂತರ ಬದಲಾಯಿಸಬಹುದು.",
        "happy":"ಸಂತೋಷ","okay":"ಪರವಾಗಿಲ್ಲ","tired":"ದಣಿದಿದ್ದೇನೆ","need_help":"ಸಹಾಯ ಬೇಕು",
        "note":"ಏನಾದರೂ ಹೇಳಬೇಕೇ? (ಐಚ್ಛಿಕ)","save_checkin":"ಇಂದಿನ ಮಾಹಿತಿ ಉಳಿಸಿ","saved_checkin":"ಇಂದಿನ ಮಾಹಿತಿ ಉಳಿಸಲಾಗಿದೆ",
        "support_hint":"ಈಗ ಸಹಾಯ ಬೇಕಿದ್ದರೆ ಸಂಪರ್ಕ ಪುಟದಿಂದ ಕರೆ ಮಾಡಿ. ಇದು ಸ್ವಯಂಚಾಲಿತ ಎಚ್ಚರಿಕೆ ಕಳುಹಿಸುವುದಿಲ್ಲ.",
        "help_title":"ಸಹಾಯ ಹತ್ತಿರದಲ್ಲಿದೆ","help_sub":"ನಂಬಿಕೆಯ ವ್ಯಕ್ತಿಗೆ ಅಥವಾ ತುರ್ತು ಸೇವೆಗೆ ಕರೆ ಮಾಡಿ.",
        "contacts":"ನಂಬಿಕೆಯ ಫೋನ್ ಸಂಪರ್ಕಗಳು","contact_name":"ಹೆಸರು","relationship":"ಸಂಬಂಧ","phone":"ಫೋನ್ ಸಂಖ್ಯೆ",
        "add_contact":"ಸಂಪರ್ಕ ಸೇರಿಸಿ","remove":"ತೆಗೆದುಹಾಕಿ","call":"ಕರೆ ಮಾಡಿ",
        "no_contacts":"ಇನ್ನೂ ಸಂಪರ್ಕಗಳನ್ನು ಸೇರಿಸಿಲ್ಲ.","india_emergency":"ಭಾರತದ ತುರ್ತು ಸಂಖ್ಯೆ",
        "emergency_note":"ಭಾರತದಲ್ಲಿ ತುರ್ತು ಪರಿಸ್ಥಿತಿಗೆ 112 ಕರೆ ಮಾಡಿ. ಈ ವೆಬ್‌ಸೈಟ್ ಸ್ವತಃ ಕರೆ ಅಥವಾ ಸ್ಥಳ ಕಳುಹಿಸುವುದಿಲ್ಲ.",
        "caregivers":"ನನ್ನ ಅನುಮೋದಿತ ಆರೈಕೆದಾರರು","no_caregivers":"ಇನ್ನೂ ಅನುಮೋದಿತ ಆರೈಕೆದಾರರಿಲ್ಲ.",
        "video_call":"ವೀಡಿಯೊ ಕರೆ","help_disclaimer":"ಕರೆ ಒತ್ತಿದರೆ ಫೋನ್ ಡಯಲರ್ ತೆರೆಯುತ್ತದೆ. ತುರ್ತು ಪರಿಸ್ಥಿತಿಯಲ್ಲಿ ಸ್ಥಳೀಯ ತುರ್ತು ಸೇವೆಗೆ ಕರೆ ಮಾಡಿ.",
        "settings_title":"ಮೈಂಡ್‌ಕೇರ್ ಬಳಸಲು ಸುಲಭವಾಗಲಿ","settings_sub":"ನಿಮಗೆ ಸುಲಭವಾದ ಆಯ್ಕೆಗಳನ್ನು ಆರಿಸಿ.",
        "language":"ಡ್ಯಾಶ್‌ಬೋರ್ಡ್ ಭಾಷೆ","large_text":"ದೊಡ್ಡ ಅಕ್ಷರ","high_contrast":"ಹೆಚ್ಚು ಕಾಂಟ್ರಾಸ್ಟ್",
        "reduced_motion":"ಕಡಿಮೆ ಚಲನೆ","save_settings":"ಸೆಟ್ಟಿಂಗ್‌ಗಳನ್ನು ಉಳಿಸಿ",
        "language_note":"ರೋಗಿಯ ಪುಟಗಳು ಮತ್ತು ಆಟದ ಪ್ರಮುಖ ಸೂಚನೆಗಳು ಕನ್ನಡದಲ್ಲಿವೆ. ಧ್ವನಿ ನಿಮ್ಮ ಸಾಧನದ ಲಭ್ಯತೆಯನ್ನು ಅವಲಂಬಿಸಿದೆ.",
        "quick_help":"ನನಗೆ ಸಹಾಯ ಬೇಕು","view_today":"ನನ್ನ ದಿನ","open_settings":"ಪ್ರದರ್ಶನ ಸೆಟ್ಟಿಂಗ್‌ಗಳು"
    },
}


def patient_preferences(user):
    if not user or user.role != "patient":
        return None
    return db.session.get(PatientPreference, user.id)


def is_simple_view(user):
    if not user or user.role != "patient":
        return False
    mode = db.session.get(PatientViewMode, user.id)
    return bool(mode and mode.simplified)


def t_for(preference):
    lang = preference.language if preference and preference.language in LANGUAGE_LABELS else "en"
    lexicon = PATIENT_TEXT[lang]
    extra = PATIENT_LABELS[lang]
    english_extra = PATIENT_LABELS["en"]
    return lambda key: lexicon.get(key, extra.get(key, PATIENT_TEXT["en"].get(key, english_extra.get(key, key))))


def now_utc():
    return datetime.now(timezone.utc)


def today_local():
    """India uses Asia/Kolkata; never rely on server UTC midnight."""
    return datetime.now(ZoneInfo("Asia/Kolkata")).date()


# Database-backed authentication throttling, shared by all Gunicorn workers.
LOGIN_WINDOW_SECONDS = 15 * 60
LOGIN_LIMIT_PER_ACCOUNT = 20
LOGIN_LIMIT_PER_IP = 50
LOGIN_LIMIT_PER_IP_ACCOUNT = 8
REGISTER_WINDOW_SECONDS = 60 * 60
REGISTER_LIMIT_PER_IP = 12


def _auth_client_ip():
    try:
        return str(ipaddress.ip_address(request.remote_addr or ""))
    except ValueError:
        return "unknown"


def _auth_bucket(kind, value):
    secret = app.config["SECRET_KEY"]
    if isinstance(secret, str):
        secret = secret.encode("utf-8")
    payload = (kind + ":" + value).encode("utf-8")
    return hmac.new(secret, payload, hashlib.sha256).hexdigest()


def _login_buckets(email):
    ip = _auth_client_ip()
    normalized = email.strip().lower()[:180]
    return (
        (_auth_bucket("login-account", normalized), LOGIN_LIMIT_PER_ACCOUNT),
        (_auth_bucket("login-ip", ip), LOGIN_LIMIT_PER_IP),
        (_auth_bucket("login-pair", ip + "|" + normalized), LOGIN_LIMIT_PER_IP_ACCOUNT),
    )


def _auth_retry_after(buckets, window_seconds):
    now = int(time.time())
    ids = [bucket for bucket, _ in buckets]
    rows = AuthAttempt.query.filter(AuthAttempt.bucket_hash.in_(ids)).all()
    by_id = {row.bucket_hash: row for row in rows}
    waiting = 0
    for bucket, limit in buckets:
        entry = by_id.get(bucket)
        if entry and entry.attempts >= limit:
            elapsed = now - entry.last_failure_epoch
            if 0 <= elapsed < window_seconds:
                waiting = max(waiting, window_seconds - elapsed)
    return waiting


def _record_auth_attempts(buckets, window_seconds):
    """Atomic counters using portable PostgreSQL/SQLite UPSERT syntax.

    Counters reset after a full quiet period; outdated opaque hashes are
    cleaned up opportunistically. No raw email, IP or password is persisted.
    """
    now = int(time.time())
    for bucket, _ in buckets:
        db.session.execute(db.text("""
            INSERT INTO auth_attempt (bucket_hash, attempts, last_failure_epoch)
            VALUES (:bucket, 1, :now)
            ON CONFLICT (bucket_hash) DO UPDATE SET
                attempts = CASE
                    WHEN auth_attempt.last_failure_epoch < :cutoff THEN 1
                    ELSE auth_attempt.attempts + 1 END,
                last_failure_epoch = :now
        """), {"bucket": bucket, "now": now, "cutoff": now - window_seconds})
    if secrets.randbelow(128) == 0:
        AuthAttempt.query.filter(AuthAttempt.last_failure_epoch < now - 86400).delete(
            synchronize_session=False)
    db.session.commit()


def _auth_rate_limited(retry_after):
    response = app.make_response((render_template("error.html",
        title="Too many attempts",
        detail="Please try again later. Your account information is safe."), 429))
    response.headers["Retry-After"] = str(max(1, int(retry_after)))
    response.headers["Cache-Control"] = "no-store"
    return response


def _password_session_stamp(user):
    """Bound to the password hash so a reset invalidates other login sessions."""
    key = app.config["SECRET_KEY"].encode("utf-8")
    return hmac.new(key, (str(user.id) + ":" + user.password_hash).encode(),
                    hashlib.sha256).hexdigest()


def _sign_in_user(user):
    session.clear()
    session["uid"] = user.id
    session["auth_stamp"] = _password_session_stamp(user)
    session.permanent = True


def _recovery_code_hash(code):
    return hmac.new(app.config["SECRET_KEY"].encode("utf-8"),
                    ("recovery:" + code).encode("utf-8"), hashlib.sha256).hexdigest()


def _recovery_mail_ready():
    return all(os.getenv(key) for key in
               ("SMTP_HOST", "SMTP_PORT", "SMTP_USERNAME", "SMTP_PASSWORD",
                "SMTP_FROM"))


def _send_recovery_mail(destination, code):
    """Require SMTP TLS; never log message contents, code or credentials."""
    if not _recovery_mail_ready():
        return False
    msg = EmailMessage()
    msg["From"] = os.environ["SMTP_FROM"]
    msg["To"] = destination
    msg["Subject"] = "MindCare password recovery code"
    msg.set_content(
        "A password reset was requested for your MindCare account.\\n\\n"
        "Recovery code: " + code + "\\n\\n"
        "Enter this code at the MindCare Reset password page. "
        "It expires in 15 minutes and works only once. "
        "If you did not request this, ignore this email.\\n")
    port = int(os.environ["SMTP_PORT"])
    if port not in (465, 587):
        raise ValueError("SMTP must use port 465 (TLS) or 587 (STARTTLS)")
    context = ssl.create_default_context()
    if port == 465:
        with smtplib.SMTP_SSL(os.environ["SMTP_HOST"], port, timeout=10,
                              context=context) as smtp:
            smtp.login(os.environ["SMTP_USERNAME"], os.environ["SMTP_PASSWORD"])
            smtp.send_message(msg)
    else:
        with smtplib.SMTP(os.environ["SMTP_HOST"], port, timeout=10) as smtp:
            smtp.ehlo()
            smtp.starttls(context=context)
            smtp.ehlo()
            smtp.login(os.environ["SMTP_USERNAME"], os.environ["SMTP_PASSWORD"])
            smtp.send_message(msg)
    return True


def current_user():
    return getattr(g, "user", None)


def require_login(role=None):
    def decorator(fn):
        @wraps(fn)
        def inner(*args, **kwargs):
            if not current_user():
                if request.is_json:
                    return jsonify(error="Please sign in"), 401
                return redirect(url_for("login", next=request.path))
            if role and current_user().role != role:
                abort(403)
            return fn(*args, **kwargs)
        return inner
    return decorator


def allowed_patient(patient_id):
    u = current_user()
    if not u:
        return False
    if u.role == "patient":
        return u.id == patient_id
    return db.session.query(CareLink.id).filter_by(caregiver_id=u.id, patient_id=patient_id, status="approved").first() is not None


def patient_or_403(patient_id):
    if not allowed_patient(patient_id):
        abort(403)
    p = db.session.get(User, patient_id)
    if not p or p.role != "patient":
        abort(404)
    return p


def caregiver_patients():
    ids = db.session.query(CareLink.patient_id).filter_by(caregiver_id=current_user().id, status="approved")
    return User.query.filter(User.id.in_(ids)).order_by(User.name).all()


def selected_patient():
    u = current_user()
    if u.role == "patient":
        return u
    raw = request.values.get("patient_id", "")
    if raw.isdecimal():
        return patient_or_403(int(raw))
    patients = caregiver_patients()
    return patients[0] if patients else None


# Per-game adaptive support, never a medical or diagnostic conclusion.
# Use only the current uninterrupted level streak, so a demotion cannot
# immediately re-promote the patient using stale results from another level.
STRONG_SCORE = 85
STRUGGLING_SCORE = 60
MIN_CONSECUTIVE_SESSIONS = 2


def difficulty_for(patient_id, game):
    latest = (GameResult.query.filter_by(patient_id=patient_id, game_type=game)
              .order_by(GameResult.id.desc()).limit(3).all())
    if not latest:
        return 1
    level = max(1, min(3, latest[0].difficulty))
    at_level = []
    for result in latest:
        if result.difficulty != level:
            break
        at_level.append(result)
    # A very difficult round at a higher level should feel reassuring,
    # not force a distressed patient to repeat the same challenge.
    if level > 1 and at_level[0].score <= 25 and at_level[0].mistakes >= 3:
        return level - 1
    if len(at_level) < MIN_CONSECUTIVE_SESSIONS:
        return level
    last_two = at_level[:2]
    if all(r.score >= STRONG_SCORE and r.mistakes <= 3 for r in last_two):
        return min(3, level + 1)
    if all((r.score <= STRUGGLING_SCORE or
            (r.score <= 72 and r.mistakes >= 4)) for r in last_two):
        return max(1, level - 1)
    return level


def performance(patient_id):
    results = (GameResult.query.filter_by(patient_id=patient_id)
               .order_by(GameResult.id.desc()).limit(100).all())
    total_count = GameResult.query.filter_by(patient_id=patient_id).count()
    if not results:
        return {"count": 0, "average": 0, "minutes": 0, "trend": "Getting started", "trend_help": "Play a few games to begin your activity history.", "delta": None, "series": []}
    # Compare sessions rather than diagnose cognition. At least 10 sessions required.
    recent = results[:5]
    baseline = results[5:10]
    delta = round(mean(r.score for r in recent) - mean(r.score for r in baseline)) if len(baseline) == 5 else None
    if delta is None:
        trend, help_text = "Building a baseline", "Activity patterns appear after at least 10 games."
    elif delta <= -18:
        trend, help_text = "Check in", "Recent game scores are lower. A caregiver may want to check on comfort, fatigue or distractions."
    elif delta <= -8:
        trend, help_text = "Needs attention", "Recent game scores dipped. Consider a gentler pace."
    else:
        trend, help_text = "Stable activity", "Recent game scores have been reasonably consistent."
    points = []
    daily = defaultdict(list)
    for item in results:
        daily[item.played_at.date().isoformat()].append(item.score)
    for day, scores in sorted(daily.items())[-7:]:
        points.append({"day": day[5:], "score": round(mean(scores))})
    return {"count": total_count, "average": round(mean(r.score for r in results)),
            "minutes": round(sum(r.duration_seconds for r in results) / 60), "trend": trend,
            "trend_help": help_text, "delta": delta, "series": points}


def reminders_for(patient_id):
    reminders = (Reminder.query.filter_by(patient_id=patient_id, active=True)
                 .filter(or_(Reminder.on_date.is_(None), Reminder.on_date == today_local()))
                 .order_by(Reminder.scheduled_time).all())
    checked = {c.reminder_id for c in ReminderCheck.query.filter(
        ReminderCheck.reminder_id.in_([r.id for r in reminders]), ReminderCheck.checked_date == today_local()).all()} if reminders else set()
    return [{"item": r, "done": r.id in checked} for r in reminders]


@app.before_request
def load_user_and_csrf():
    g.user = db.session.get(User, session["uid"]) if isinstance(session.get("uid"), int) else None
    if g.user and not hmac.compare_digest(
            str(session.get("auth_stamp", "")), _password_session_stamp(g.user)):
        # Stale sessions, including sessions from before this security rollout,
        # must authenticate again after deployment or password recovery.
        session.clear()
        g.user = None
    if "csrf_token" not in session:
        session["csrf_token"] = secrets.token_urlsafe(32)
    if request.method in ("POST", "PUT", "PATCH", "DELETE"):
        provided = request.headers.get("X-CSRF-Token") or request.form.get("csrf_token", "")
        if not secrets.compare_digest(provided, session["csrf_token"]):
            abort(400, "Security check failed. Refresh the page and try again.")


@app.context_processor
def inject_common():
    prefs = patient_preferences(current_user())
    return dict(me=current_user(), csrf_token=session.get("csrf_token"), GAMES=GAMES,
                CATEGORIES=CATEGORIES, LEVEL_NAMES=LEVEL_NAMES,
                patient_prefs=prefs, tr=t_for(prefs), LANGUAGES=LANGUAGE_LABELS,
                simple_view=is_simple_view(current_user()),
                google_login_ready=GOOGLE_OAUTH_READY,
                phone_login_ready=firebase_phone_ready(),
                firebase_web_config=firebase_public_config())


@app.after_request
def security_headers(response):
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "camera=(self), microphone=(self), geolocation=()"
    # Allow Firebase only on authentication pages; other private pages retain
    # the original more restrictive Content Security Policy.
    content_policy = ("default-src 'self'; img-src 'self' data:; style-src 'self'; "
                      "script-src 'self'; font-src 'self'; connect-src 'self' stun: turn: turns:; "
                      "media-src 'self' blob:; object-src 'none'; base-uri 'self'; frame-ancestors 'none'")
    public_firebase = firebase_public_config() if firebase_phone_ready() else None
    if public_firebase and public_firebase.get("authDomain") and request.endpoint in ("login", "register", "account_security"):
        content_policy = (
            "default-src 'self'; "
            "script-src 'self' https://www.gstatic.com https://www.google.com https://www.recaptcha.net; "
            "img-src 'self' data: https://www.gstatic.com https://www.google.com https://www.recaptcha.net; "
            "style-src 'self' 'unsafe-inline'; "
            "connect-src 'self' https://identitytoolkit.googleapis.com https://securetoken.googleapis.com "
            "https://www.googleapis.com https://www.gstatic.com; "
            "frame-src 'self' https://www.google.com https://www.recaptcha.net "
            "https://" + public_firebase["authDomain"] + "; "
            "font-src 'self' https://www.gstatic.com; object-src 'none'; base-uri 'self'; frame-ancestors 'none'"
        )
    response.headers["Content-Security-Policy"] = content_policy
    if current_user():
        response.headers["Cache-Control"] = "private, no-store"
    elif request.endpoint in ("login", "register", "auth_complete"):
        response.headers["Cache-Control"] = "no-store"
    if request.is_secure:
        response.headers["Strict-Transport-Security"] = "max-age=15552000"
    return response


@app.route("/health")
def health():
    try:
        db.session.execute(db.text("SELECT 1"))
        return jsonify(status="ok", database="connected")
    except Exception:
        return jsonify(status="error", database="unavailable"), 503


@app.route("/")
def home():
    if current_user():
        return redirect(url_for("dashboard"))
    return render_template("home.html")



# --- External identity login and account linking ----------------------------
# Never match a Google or phone login to a password account based only on
# email or phone. A user must first log into that account and connect it.
AUTH_PENDING_SECONDS = 600


def external_login_session(user):
    _sign_in_user(user)


def make_phone_account_email():
    # Internal, unguessable identity; a phone user can later link Google.
    return "phone-" + secrets.token_hex(16) + "@internal.mindcare.invalid"


def pending_identity_or_none():
    raw = session.get("pending_identity_token")
    if not isinstance(raw, str) or len(raw) < 32:
        return None
    row = db.session.get(PendingIdentity, hashlib.sha256(raw.encode()).hexdigest())
    if not row:
        return None
    expiry = row.expires_at.replace(tzinfo=timezone.utc) if row.expires_at.tzinfo is None else row.expires_at
    if now_utc() >= expiry:
        db.session.delete(row)
        db.session.commit()
        session.pop("pending_identity_token", None)
        return None
    return row


def complete_verified_external_identity(provider, subject, name="", email="", label=""):
    """Use only after Google OIDC/Firebase Admin successfully verified the token."""
    if provider not in ("google", "firebase_phone") or not isinstance(subject, str) or not 1 <= len(subject) <= 180:
        abort(400)
    existing = ExternalIdentity.query.filter_by(provider=provider, subject=subject).first()
    if existing:
        if current_user() and existing.user_id != current_user().id:
            flash("This sign-in method is already connected to another account.", "error")
            return redirect(url_for("account_security"))
        user = db.session.get(User, existing.user_id)
        if not user:
            abort(403)
        external_login_session(user)
        flash("You are securely signed in.", "success")
        return redirect(url_for("dashboard"))
    if current_user():
        user = current_user()
        if (provider == "google" and not user.email.endswith("@internal.mindcare.invalid")
                and (not email or email.lower() != user.email.lower())):
            flash("Use a Google account with your existing MindCare email to link it.", "error")
            return redirect(url_for("account_security"))
        if ExternalIdentity.query.filter_by(user_id=user.id, provider=provider).first():
            flash("A different account from this provider is already connected.", "error")
            return redirect(url_for("account_security"))
        try:
            db.session.add(ExternalIdentity(
                user_id=user.id, provider=provider, subject=subject, label=label[:180]
            ))
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            flash("Could not connect this sign-in method. Please try again.", "error")
            return redirect(url_for("account_security"))
        flash("Your sign-in method has been connected.", "success")
        return redirect(url_for("account_security"))
    if email and User.query.filter(func.lower(User.email) == email.lower()).first():
        flash("This email already has a MindCare account. Sign in with your password, then connect Google from Account security.", "info")
        return redirect(url_for("login"))
    # Store verified identity in Postgres, not in an editable form or the
    # signed-but-not-encrypted Flask session cookie.
    random_token = secrets.token_urlsafe(36)
    pending = PendingIdentity(
        token_hash=hashlib.sha256(random_token.encode()).hexdigest(),
        provider=provider, subject=subject,
        email=email[:180] if provider == "google" else None,
        name=name[:90], label=label[:180],
        expires_at=now_utc() + timedelta(seconds=AUTH_PENDING_SECONDS)
    )
    db.session.add(pending)
    db.session.commit()
    session.pop("pending_identity_token", None)
    session["pending_identity_token"] = random_token
    return redirect(url_for("auth_complete"))


@app.route("/auth/google")
def google_auth_start():
    if not GOOGLE_OAUTH_READY:
        flash("Google sign-in is not configured yet. Please use your email and password.", "info")
        return redirect(url_for("login"))
    if current_user():
        # Linking is a distinct user-initiated action, never an accidental login.
        if request.args.get("mode") != "link":
            return redirect(url_for("account_security"))
        session["google_link_user"] = current_user().id
    else:
        session.pop("google_link_user", None)
    return oauth.google.authorize_redirect(os.environ["GOOGLE_REDIRECT_URI"])


@app.route("/auth/google/callback")
def google_auth_callback():
    if not GOOGLE_OAUTH_READY:
        abort(404)
    try:
        token = oauth.google.authorize_access_token()
        profile = token.get("userinfo") or {}
    except (OAuthError, ValueError, KeyError):
        flash("Google could not verify this sign-in. Please try again.", "error")
        return redirect(url_for("login"))
    subject = profile.get("sub")
    email = profile.get("email") or ""
    verified = profile.get("email_verified") is True or profile.get("email_verified") == "true"
    if not verified or not isinstance(email, str) or not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email):
        flash("Please choose a Google account with a verified email address.", "error")
        return redirect(url_for("login"))
    expected_link = session.pop("google_link_user", None)
    if current_user() and expected_link != current_user().id:
        abort(403)
    if expected_link is not None and (not current_user() or expected_link != current_user().id):
        abort(403)
    return complete_verified_external_identity(
        "google", subject, name=profile.get("name") or "",
        email=email.lower(), label=email.lower()
    )


def verify_firebase_phone_id_token(token):
    """Verify ID token signature, issuer, project and revocation via Firebase Admin."""
    import firebase_admin
    from firebase_admin import auth as firebase_auth, credentials
    try:
        fb = firebase_admin.get_app("mindcare-phone")
    except ValueError:
        details = json.loads(os.environ["FIREBASE_SERVICE_ACCOUNT_JSON"])
        fb = firebase_admin.initialize_app(
            credentials.Certificate(details),
            {"projectId": os.environ["FIREBASE_PROJECT_ID"]}, name="mindcare-phone"
        )
    claims = firebase_auth.verify_id_token(token, app=fb, check_revoked=True)
    if claims.get("firebase", {}).get("sign_in_provider") != "phone":
        raise ValueError("Not a phone-verified identity")
    phone = claims.get("phone_number")
    subject = claims.get("uid")
    if (not isinstance(phone, str) or not re.fullmatch(r"\+[1-9][0-9]{7,14}", phone)
            or not isinstance(subject, str) or not subject):
        raise ValueError("Phone verification is incomplete")
    return subject, phone


@app.route("/auth/phone-session", methods=["POST"])
def phone_session():
    if not firebase_phone_ready():
        return jsonify(error="Phone OTP sign-in is not configured."), 503
    data = request.get_json(silent=True) or {}
    token = data.get("id_token", "")
    if not isinstance(token, str) or not 30 <= len(token) <= 12000:
        return jsonify(error="Invalid phone verification."), 400
    try:
        subject, phone = verify_firebase_phone_id_token(token)
    except (ValueError, KeyError, TypeError, json.JSONDecodeError):
        return jsonify(error="Could not verify that SMS code. Please try again."), 401
    except Exception:
        app.logger.warning("Firebase verification unavailable")
        return jsonify(error="Phone verification is temporarily unavailable."), 503
    response = complete_verified_external_identity(
        "firebase_phone", subject, label=phone
    )
    return jsonify(ok=True, next_url=response.location)


@app.route("/auth/complete", methods=["GET", "POST"])
def auth_complete():
    if current_user():
        return redirect(url_for("dashboard"))
    pending = pending_identity_or_none()
    if not pending:
        flash("The verified sign-in session expired. Please start again.", "info")
        return redirect(url_for("login"))
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        role = request.form.get("role", "")
        age_raw = request.form.get("age", "").strip()
        if not 2 <= len(name) <= 90 or role not in ("patient", "caregiver"):
            flash("Choose a patient or caregiver account and enter your name.", "error")
        elif age_raw and (not age_raw.isdecimal() or not 1 <= int(age_raw) <= 120):
            flash("Please choose a valid age.", "error")
        elif pending.email and User.query.filter(func.lower(User.email) == pending.email.lower()).first():
            flash("This email already has an account. Sign in with your password to connect it.", "error")
            return redirect(url_for("login"))
        elif ExternalIdentity.query.filter_by(provider=pending.provider, subject=pending.subject).first():
            flash("This identity is already connected. Sign in again.", "error")
            return redirect(url_for("login"))
        else:
            invite = secrets.token_hex(4).upper() if role == "patient" else None
            while invite and User.query.filter_by(invite_code=invite).first():
                invite = secrets.token_hex(4).upper()
            user = User(
                name=name, email=pending.email or make_phone_account_email(),
                role=role, age=int(age_raw) if role == "patient" and age_raw else None,
                password_hash=generate_password_hash(secrets.token_urlsafe(48)),
                invite_code=invite,
            )
            try:
                db.session.add(user)
                db.session.flush()
                db.session.add(ExternalIdentity(
                    user_id=user.id, provider=pending.provider,
                    subject=pending.subject, label=pending.label
                ))
                db.session.delete(pending)
                db.session.commit()
            except IntegrityError:
                db.session.rollback()
                flash("This identity has already been used. Please try signing in.", "error")
                return redirect(url_for("login"))
            external_login_session(user)
            flash("Welcome to MindCare. Your space is ready.", "success")
            return redirect(url_for("dashboard"))
    return render_template("auth_complete.html", pending=pending)


@app.route("/account/security")
@require_login()
def account_security():
    identities = ExternalIdentity.query.filter_by(user_id=current_user().id).all()
    return render_template("account_security.html", identities=identities)


@app.route("/register", methods=["GET", "POST"])
def register():
    if current_user():
        return redirect(url_for("dashboard"))
    if request.method == "POST":
        registration_bucket = ((_auth_bucket("register-ip", _auth_client_ip()), REGISTER_LIMIT_PER_IP),)
        retry_after = _auth_retry_after(registration_bucket, REGISTER_WINDOW_SECONDS)
        if retry_after:
            return _auth_rate_limited(retry_after)
        _record_auth_attempts(registration_bucket, REGISTER_WINDOW_SECONDS)
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        role = request.form.get("role", "")
        age_raw = request.form.get("age", "").strip()
        if not (2 <= len(name) <= 90) or not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email):
            flash("Please enter a valid name and email.", "error")
        elif len(password) < 10 or len(password) > 128:
            flash("Please use a password with at least 10 characters.", "error")
        elif role not in ("patient", "caregiver"):
            flash("Please select who will use this account.", "error")
        elif User.query.filter_by(email=email).first():
            flash("An account already uses this email.", "error")
        elif role == "patient" and age_raw and (not age_raw.isdecimal() or not 1 <= int(age_raw) <= 120):
            flash("Please enter a valid age.", "error")
        else:
            invite = secrets.token_hex(4).upper() if role == "patient" else None
            while invite and User.query.filter_by(invite_code=invite).first():
                invite = secrets.token_hex(4).upper()
            user = User(name=name, email=email, role=role, age=int(age_raw) if role == "patient" and age_raw else None,
                        region=request.form.get("region", "").strip()[:80] if role == "patient" else None,
                        invite_code=invite, password_hash=generate_password_hash(password))
            db.session.add(user)
            db.session.commit()
            _sign_in_user(user)
            flash("Your MindCare space is ready!", "success")
            return redirect(url_for("dashboard"))
    return render_template("auth.html", mode="register")


@app.route("/login", methods=["GET", "POST"])
def login():
    if current_user():
        return redirect(url_for("dashboard"))
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        buckets = _login_buckets(email)
        retry_after = _auth_retry_after(buckets, LOGIN_WINDOW_SECONDS)
        if retry_after:
            return _auth_rate_limited(retry_after)
        user = User.query.filter_by(email=email).first()
        if user and check_password_hash(user.password_hash, request.form.get("password", "")):
            # The per-IP total remains in place to deter credential stuffing.
            # Only the account and IP/account counters reset on successful login.
            AuthAttempt.query.filter(AuthAttempt.bucket_hash.in_(
                [buckets[0][0], buckets[2][0]])).delete(synchronize_session=False)
            db.session.commit()
            _sign_in_user(user)
            flash("Welcome back!", "success")
            return redirect(url_for("dashboard"))
        _record_auth_attempts(buckets, LOGIN_WINDOW_SECONDS)
        flash("Email or password was not recognised.", "error")
    return render_template("auth.html", mode="login")



RECOVERY_EXPIRY_MINUTES = 15
RECOVERY_REQUEST_LIMIT = 4
RECOVERY_VERIFY_LIMIT = 10
RECOVERY_WINDOW_SECONDS = 3600
RECOVERY_GENERIC_MESSAGE = (
    "If this address belongs to an email/password account and recovery "
    "is enabled, a recovery code will be sent. Check your inbox."
)


@app.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()[:180]
        buckets = (
            (_auth_bucket("recovery-request-ip", _auth_client_ip()), RECOVERY_REQUEST_LIMIT),
            (_auth_bucket("recovery-request-account", email), RECOVERY_REQUEST_LIMIT),
        )
        delay = _auth_retry_after(buckets, RECOVERY_WINDOW_SECONDS)
        if delay:
            return _auth_rate_limited(delay)
        _record_auth_attempts(buckets, RECOVERY_WINDOW_SECONDS)
        # Never reveal existence, provider or delivery status. Internal phone
        # identities cannot receive an email recovery code.
        user = User.query.filter(func.lower(User.email) == email).first()
        if (user and not email.endswith("@internal.mindcare.invalid")
                and _recovery_mail_ready()):
            code = secrets.token_urlsafe(32)
            db.session.add(PasswordRecovery(
                user_id=user.id, code_hash=_recovery_code_hash(code),
                expires_at=now_utc() + timedelta(minutes=RECOVERY_EXPIRY_MINUTES)))
            db.session.commit()
            try:
                _send_recovery_mail(email, code)
            except (OSError, smtplib.SMTPException, ValueError) as exc:
                # Failed-delivery codes must not remain usable.
                PasswordRecovery.query.filter_by(
                    code_hash=_recovery_code_hash(code), consumed_at=None
                ).update({"consumed_at": now_utc()}, synchronize_session=False)
                db.session.commit()
                # Do not leak the code, address or SMTP credentials to logs.
                app.logger.warning("Recovery mail transport failed: %s",
                                   type(exc).__name__)
        flash(RECOVERY_GENERIC_MESSAGE, "info")
        return redirect(url_for("reset_password"))
    return render_template("password_recovery.html", mode="request",
                           configured=_recovery_mail_ready())


@app.route("/reset-password", methods=["GET", "POST"])
def reset_password():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()[:180]
        code = request.form.get("code", "").strip()
        new_password = request.form.get("password", "")
        buckets = (
            (_auth_bucket("recovery-verify-ip", _auth_client_ip()), RECOVERY_VERIFY_LIMIT),
            (_auth_bucket("recovery-verify-account", email), RECOVERY_VERIFY_LIMIT),
        )
        delay = _auth_retry_after(buckets, RECOVERY_WINDOW_SECONDS)
        if delay:
            return _auth_rate_limited(delay)
        _record_auth_attempts(buckets, RECOVERY_WINDOW_SECONDS)
        if not 10 <= len(new_password) <= 128:
            flash("Choose a new password between 10 and 128 characters.", "error")
        elif not re.fullmatch(r"[^\\s@]+@[^\\s@]+\\.[^\\s@]+", email) or len(code) != 43:
            flash("Invalid or expired recovery details. Request a new code.", "error")
        else:
            user = User.query.filter(func.lower(User.email) == email).first()
            recovery = (PasswordRecovery.query.filter_by(
                code_hash=_recovery_code_hash(code), user_id=user.id).first()
                if user else None)
            if recovery:
                expiry = recovery.expires_at
                expiry = expiry.replace(tzinfo=timezone.utc) if expiry.tzinfo is None else expiry
                if recovery.consumed_at is None and expiry > now_utc():
                    used = (db.session.query(PasswordRecovery)
                        .filter(PasswordRecovery.id == recovery.id,
                                PasswordRecovery.consumed_at.is_(None),
                                PasswordRecovery.expires_at > now_utc())
                        .update({"consumed_at": now_utc()}, synchronize_session=False))
                    if used == 1:
                        user.password_hash = generate_password_hash(new_password)
                        (PasswordRecovery.query.filter(
                            PasswordRecovery.user_id == user.id,
                            PasswordRecovery.consumed_at.is_(None))
                            .update({"consumed_at": now_utc()}, synchronize_session=False))
                        db.session.commit()
                        session.clear()
                        flash("Password updated. Sign in again on all devices.", "success")
                        return redirect(url_for("login"))
            flash("Invalid or expired recovery details. Request a new code.", "error")
    return render_template("password_recovery.html", mode="reset",
                           configured=_recovery_mail_ready())


@app.route("/logout", methods=["POST"])
@require_login()
def logout():
    session.clear()
    return redirect(url_for("home"))


def caregiver_care_overview(patients):
    """Summaries are strictly limited to patients who approved this caregiver."""
    today = today_local()
    since = today - timedelta(days=6)
    patient_ids = [p.id for p in patients]
    if not patient_ids:
        return {
            "summaries": [], "support_queue": [],
            "counts": {"patients": 0, "checkins": 0, "support": 0,
                       "overdue": 0, "no_checkin": 0},
            "today_date": today,
        }
    checkins = (WellbeingCheck.query
                .filter(WellbeingCheck.patient_id.in_(patient_ids),
                        WellbeingCheck.checked_date >= since,
                        WellbeingCheck.checked_date <= today)
                .order_by(WellbeingCheck.checked_date.desc(), WellbeingCheck.checked_at.desc())
                .all())
    by_patient = defaultdict(list)
    for checkin in checkins:
        by_patient[checkin.patient_id].append(checkin)
    support_checkins = [c for c in checkins if c.feeling == "need_help"]
    seen = set()
    if support_checkins:
        seen = {review.checkin_id for review in CaregiverSupportReview.query.filter(
            CaregiverSupportReview.caregiver_id == current_user().id,
            CaregiverSupportReview.checkin_id.in_([c.id for c in support_checkins])
        ).all()}
    clock = datetime.now(ZoneInfo("Asia/Kolkata")).strftime("%H:%M")
    summaries = []
    queue = []
    total_overdue = 0
    checked_today = 0
    for patient in patients:
        recent = by_patient[patient.id]
        today_checkin = next((c for c in recent if c.checked_date == today), None)
        if today_checkin:
            checked_today += 1
        reminders = reminders_for(patient.id)
        overdue = sum(1 for row in reminders if not row["done"]
                      and row["item"].scheduled_time < clock)
        total_overdue += overdue
        completed = sum(1 for row in reminders if row["done"])
        upcoming = next((row for row in reminders if not row["done"]
                         and row["item"].scheduled_time >= clock), None)
        pending_support = [c for c in recent if c.feeling == "need_help" and c.id not in seen]
        for checkin in pending_support:
            queue.append({"patient": patient, "checkin": checkin})
        summaries.append({
            "patient": patient,
            "stats": performance(patient.id),
            "reminders": reminders,
            "done_count": completed,
            "overdue_count": overdue,
            "upcoming": upcoming,
            "checkin": today_checkin,
            "latest_checkin": recent[0] if recent else None,
            "pending_support": len(pending_support),
            "family_count": FamilyMember.query.filter_by(patient_id=patient.id).count(),
        })
    queue.sort(key=lambda row: (row["checkin"].checked_date,
                               row["checkin"].checked_at or datetime.min.replace(tzinfo=timezone.utc)),
               reverse=True)
    return {
        "summaries": summaries,
        "support_queue": queue,
        "counts": {
            "patients": len(patients), "checkins": checked_today,
            "support": len(queue), "overdue": total_overdue,
            "no_checkin": len(patients) - checked_today,
        },
        "today_date": today,
    }


@app.route("/dashboard")
@require_login()
def dashboard():
    if current_user().role == "caregiver":
        patients = caregiver_patients()
        overview = caregiver_care_overview(patients)
        pending = [{"link": link, "patient": db.session.get(User, link.patient_id)} for link in CareLink.query.filter_by(caregiver_id=current_user().id, status="pending").all()]
        return render_template("caregiver.html", pending=pending, **overview)
    stats = performance(current_user().id)
    reminders = reminders_for(current_user().id)
    pending_links = [{"link": link, "caregiver": db.session.get(User, link.caregiver_id)} for link in CareLink.query.filter_by(patient_id=current_user().id, status="pending").all()]
    approved_links = [{"link": link, "caregiver": db.session.get(User, link.caregiver_id)} for link in CareLink.query.filter_by(patient_id=current_user().id, status="approved").all()]
    recent = (GameResult.query.filter_by(patient_id=current_user().id)
              .order_by(GameResult.id.desc()).limit(4).all())
    checkin = WellbeingCheck.query.filter_by(patient_id=current_user().id, checked_date=today_local()).first()
    family_faces = FamilyMember.query.filter_by(patient_id=current_user().id).order_by(FamilyMember.name).limit(3).all()
    current_minute = datetime.now(ZoneInfo("Asia/Kolkata")).strftime("%H:%M")
    # Never hide an unfinished morning reminder just because its scheduled time passed.
    # Show the next upcoming item or the earliest missed, unfinished item.
    next_reminder = next((r for r in reminders if not r["done"] and r["item"].scheduled_time >= current_minute),
                         next((r for r in reminders if not r["done"]), None))
    trusted = EmergencyContact.query.filter_by(patient_id=current_user().id).order_by(EmergencyContact.id).all()
    support_contact = next((contact for contact in trusted if whatsapp_chat_url(contact.phone)), None)
    support_url = whatsapp_chat_url(support_contact.phone) if support_contact else ""
    context = dict(stats=stats, reminders=reminders, recent=recent,
                   checkin=checkin, family_faces=family_faces, next_reminder=next_reminder,
                   today_pretty=today_local().strftime("%A, %d %B %Y"),
                   now_minute=current_minute,
                   suggested=list(GAMES.items())[:5], pending_links=pending_links,
                   approved_links=approved_links, support_contact=support_contact, support_url=support_url)
    if is_simple_view(current_user()):
        return render_template("dashboard_simple.html", **context)
    return render_template("dashboard.html", **context)



@app.route("/patient/view-mode", methods=["POST"])
@require_login("patient")
def patient_view_mode():
    """Opt-in low-distraction dashboard; switching back is always visible."""
    requested = request.form.get("simplified")
    if requested not in ("1", "0"):
        abort(400, "Choose a valid view mode.")
    mode = db.session.get(PatientViewMode, current_user().id)
    if not mode:
        mode = PatientViewMode(patient_id=current_user().id)
        db.session.add(mode)
    mode.simplified = requested == "1"
    db.session.commit()
    return redirect(url_for("dashboard"))


@app.route("/wellbeing/check-in", methods=["POST"])
@require_login("patient")
def wellbeing_checkin():
    feeling = request.form.get("feeling", "").strip()
    quick_support = request.form.get("quick_support") == "1"
    note = request.form.get("note", "").strip()
    if feeling not in FEELINGS or len(note) > 180:
        abort(400, "Choose a feeling and keep your note under 180 characters.")
    today = today_local()
    record = WellbeingCheck.query.filter_by(patient_id=current_user().id, checked_date=today).first()
    # The dedicated one-tap support button must not erase a previously
    # written note. Pressing it again re-opens a reviewed request.
    if quick_support and feeling == "need_help" and record:
        note = record.note
    if not record:
        record = WellbeingCheck(patient_id=current_user().id, checked_date=today, feeling=feeling, note=note)
        db.session.add(record)
    else:
        # A new or changed request for support must reappear for approved
        # caregivers even if they reviewed an earlier version today.
        if feeling == "need_help" and (quick_support or record.feeling != "need_help" or record.note != note):
            CaregiverSupportReview.query.filter_by(checkin_id=record.id).delete(synchronize_session=False)
        record.feeling = feeling
        record.note = note
        record.checked_at = now_utc()
    db.session.commit()
    if feeling == "need_help":
        flash(t_for(patient_preferences(current_user()))("flash_support"), "info")
    else:
        flash(t_for(patient_preferences(current_user()))("flash_checkin"), "success")
    return redirect(url_for("dashboard", _anchor="wellbeing"))


@app.template_filter("whatsapp_chat_url")
def whatsapp_chat_url(phone):
    """Safe official WhatsApp chat link; it NEVER initiates a phone call.

    Assume Indian country code only for a local 10-digit saved number.
    All other countries must be saved with an explicit +country code.
    """
    number = (phone or "").strip()
    if not re.fullmatch(r"\+?[0-9]{10,15}", number):
        return ""
    if number.startswith("+"):
        digits = number[1:]
    elif len(number) == 10:
        digits = "91" + number
    elif len(number) == 12 and number.startswith("91"):
        digits = number
    else:
        return ""
    if not re.fullmatch(r"[1-9][0-9]{9,14}", digits):
        return ""
    return f"https://wa.me/{digits}"


@app.route("/help")
@require_login("patient")
def patient_help():
    contacts = EmergencyContact.query.filter_by(patient_id=current_user().id).order_by(EmergencyContact.id).all()
    links = CareLink.query.filter_by(patient_id=current_user().id, status="approved").all()
    caregivers = [db.session.get(User, link.caregiver_id) for link in links]
    return render_template("patient_help.html", contacts=contacts, caregivers=[c for c in caregivers if c])


@app.route("/help/contacts/add", methods=["POST"])
@require_login("patient")
def contact_add():
    name = request.form.get("name", "").strip()
    relation = request.form.get("relation", "").strip()
    raw_phone = request.form.get("phone", "").strip()
    normalized = re.sub(r"[\s().-]", "", raw_phone)
    if not (2 <= len(name) <= 90 and 2 <= len(relation) <= 55):
        abort(400, "Enter a name and relationship.")
    if not re.fullmatch(r"\+?[0-9]{10,15}", normalized):
        abort(400, "Enter a phone number with 10 to 15 digits; an optional + country code is allowed.")
    if EmergencyContact.query.filter_by(patient_id=current_user().id).count() >= 5:
        abort(400, "You can save up to five trusted contacts.")
    db.session.add(EmergencyContact(patient_id=current_user().id, name=name,
                                    relation=relation, phone=normalized))
    db.session.commit()
    flash(t_for(patient_preferences(current_user()))("flash_contact_add"), "success")
    return redirect(url_for("patient_help"))



@app.route("/help/contacts/<int:contact_id>/edit", methods=["POST"])
@require_login("patient")
def contact_edit(contact_id):
    contact = db.session.get(EmergencyContact, contact_id)
    if not contact or contact.patient_id != current_user().id:
        abort(404)
    name = request.form.get("name", "").strip()
    relation = request.form.get("relation", "").strip()
    phone = re.sub(r"[\s().-]", "", request.form.get("phone", "").strip())
    if not 2 <= len(name) <= 90 or not 2 <= len(relation) <= 55 or not re.fullmatch(r"\+?[0-9]{10,15}", phone):
        abort(400, "Enter a valid contact name, relationship and phone number.")
    contact.name, contact.relation, contact.phone = name, relation, phone
    db.session.commit()
    flash(t_for(patient_preferences(current_user()))("flash_contact_edit"), "success")
    return redirect(url_for("patient_help"))


@app.route("/help/contacts/<int:contact_id>/delete", methods=["POST"])
@require_login("patient")
def contact_delete(contact_id):
    contact = db.session.get(EmergencyContact, contact_id)
    if not contact or contact.patient_id != current_user().id:
        abort(404)
    db.session.delete(contact)
    db.session.commit()
    flash(t_for(patient_preferences(current_user()))("flash_contact_removed"), "success")
    return redirect(url_for("patient_help"))


@app.route("/settings", methods=["GET", "POST"])
@require_login("patient")
def patient_settings():
    prefs = db.session.get(PatientPreference, current_user().id)
    if request.method == "POST":
        language = request.form.get("language", "")
        if language not in LANGUAGE_LABELS:
            abort(400, "Choose a supported interface language.")
        if not prefs:
            prefs = PatientPreference(patient_id=current_user().id)
            db.session.add(prefs)
        prefs.language = language
        prefs.large_text = request.form.get("large_text") == "on"
        prefs.high_contrast = request.form.get("high_contrast") == "on"
        prefs.reduced_motion = request.form.get("reduced_motion") == "on"
        mode = db.session.get(PatientViewMode, current_user().id)
        if not mode:
            mode = PatientViewMode(patient_id=current_user().id)
            db.session.add(mode)
        mode.simplified = request.form.get("simplified_mode") == "on"
        db.session.commit()
        flash(t_for(patient_preferences(current_user()))("flash_settings_saved"), "success")
        return redirect(url_for("patient_settings"))
    return render_template("patient_settings.html", preferences=prefs)


@app.route("/games")
@require_login("patient")
def games():
    levels = {slug: difficulty_for(current_user().id, slug) for slug in GAMES}
    family_count = FamilyMember.query.filter_by(patient_id=current_user().id).count()
    return render_template("games.html", levels=levels, family_count=family_count)


@app.route("/games/<slug>")
@require_login("patient")
def play_game(slug):
    if slug not in GAMES:
        abort(404)
    family = FamilyMember.query.filter_by(patient_id=current_user().id).all() if slug == "family" else []
    level = difficulty_for(current_user().id, slug)
    return render_template("play.html", slug=slug, level=level,
                           family=[{"id": m.id, "name": m.name, "relation": m.relation,
                                    "image": url_for("family_photo", member_id=m.id)} for m in family])


@app.route("/api/games/finish", methods=["POST"])
@require_login("patient")
def finish_game():
    payload = request.get_json(silent=True) or {}
    slug = payload.get("game")
    if slug not in GAMES:
        return jsonify(error="Unknown game"), 400
    try:
        score = int(payload.get("score"))
        errors = int(payload.get("mistakes"))
        seconds = int(payload.get("seconds"))
        difficulty = int(payload.get("difficulty"))
    except (TypeError, ValueError):
        return jsonify(error="Invalid game result"), 400
    if not (0 <= score <= 100 and 0 <= errors <= 100 and 1 <= seconds <= 3600 and 1 <= difficulty <= 3):
        return jsonify(error="Invalid game result"), 400
    expected = difficulty_for(current_user().id, slug)
    if difficulty != expected:
        return jsonify(error="Game level changed. Please refresh."), 409
    db.session.add(GameResult(patient_id=current_user().id, game_type=slug, score=score,
                              mistakes=errors, duration_seconds=seconds, difficulty=difficulty))
    db.session.commit()
    new_level = difficulty_for(current_user().id, slug)
    # The current play is saved at the level used, even if the next play changes.
    return jsonify(ok=True, new_level=new_level,
                   level_change=new_level - difficulty,
                   next_level_name=LEVEL_NAMES[new_level],
                   stats=performance(current_user().id))


@app.route("/reminders")
@require_login()
def reminders_page():
    p = selected_patient()
    upcoming = (Reminder.query.filter_by(patient_id=p.id, active=True).filter(Reminder.on_date > today_local())
                .order_by(Reminder.on_date, Reminder.scheduled_time).limit(20).all()) if p else []
    return render_template("reminders.html", patient=p, patients=caregiver_patients() if current_user().role == "caregiver" else [],
                           reminders=reminders_for(p.id) if p else [], upcoming=upcoming)


@app.route("/reminders/create", methods=["POST"])
@require_login()
def reminder_create():
    p = selected_patient()
    if not p:
        abort(400, "Link a patient account before creating reminders.")
    title = request.form.get("title", "").strip()[:110]
    category = request.form.get("category", "")
    when = request.form.get("scheduled_time", "")
    date_raw = request.form.get("on_date", "").strip()
    try:
        on_date = date.fromisoformat(date_raw) if date_raw else None
    except ValueError:
        on_date = date.min
    if on_date is not None and on_date < today_local():
        flash("Please choose today or a future date for a one-time reminder.", "error")
        return redirect(url_for("reminders_page", patient_id=p.id))
    if not title or category not in CATEGORIES or not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", when):
        flash("Add a title, category and valid reminder time.", "error")
    else:
        db.session.add(Reminder(patient_id=p.id, created_by=current_user().id, title=title,
                                category=category, scheduled_time=when, on_date=on_date, notes=request.form.get("notes", "").strip()[:240]))
        db.session.commit()
        flash(t_for(patient_preferences(current_user()))("flash_reminder_added"), "success")
    return redirect(url_for("reminders_page", patient_id=p.id))



@app.route("/reminders/<int:reminder_id>/edit", methods=["POST"])
@require_login()
def reminder_edit(reminder_id):
    reminder = db.session.get(Reminder, reminder_id)
    if not reminder or not reminder.active or not allowed_patient(reminder.patient_id):
        abort(404)
    title = request.form.get("title", "").strip()
    category = request.form.get("category", "")
    scheduled_time = request.form.get("scheduled_time", "")
    notes = request.form.get("notes", "").strip()
    raw_date = request.form.get("on_date", "").strip()
    try:
        on_date = date.fromisoformat(raw_date) if raw_date else None
    except ValueError:
        abort(400, "Enter a valid reminder date.")
    if (not 1 <= len(title) <= 110 or category not in CATEGORIES
        or not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", scheduled_time)
        or len(notes) > 240 or (on_date is not None and on_date < today_local())):
        abort(400, "Enter valid reminder details and a date that is not in the past.")
    changed_schedule = reminder.scheduled_time != scheduled_time or reminder.on_date != on_date
    reminder.title, reminder.category = title, category
    reminder.scheduled_time, reminder.on_date, reminder.notes = scheduled_time, on_date, notes
    if changed_schedule:
        # A rescheduled reminder should not inherit the earlier completion tick.
        ReminderCheck.query.filter_by(reminder_id=reminder.id, checked_date=today_local()).delete()
    db.session.commit()
    flash(t_for(patient_preferences(current_user()))("flash_reminder_edit"), "success")
    return redirect(url_for("reminders_page", patient_id=reminder.patient_id))


@app.route("/reminders/<int:reminder_id>/check", methods=["POST"])
@require_login("patient")
def reminder_check(reminder_id):
    reminder = db.session.get(Reminder, reminder_id)
    if not reminder or reminder.patient_id != current_user().id or not reminder.active:
        abort(404)
    if reminder.on_date and reminder.on_date != today_local():
        abort(400, "You can only acknowledge a one-time reminder on its scheduled day.")
    if not ReminderCheck.query.filter_by(reminder_id=reminder_id, checked_date=today_local()).first():
        db.session.add(ReminderCheck(reminder_id=reminder_id, checked_date=today_local()))
        db.session.commit()
    flash(t_for(patient_preferences(current_user()))("flash_reminder_done"), "success")
    return redirect(request.form.get("next") if request.form.get("next") in ("/dashboard", "/reminders") else url_for("reminders_page"))


@app.route("/reminders/<int:reminder_id>/delete", methods=["POST"])
@require_login()
def reminder_delete(reminder_id):
    reminder = db.session.get(Reminder, reminder_id)
    if not reminder or not allowed_patient(reminder.patient_id):
        abort(404)
    reminder.active = False
    db.session.commit()
    flash(t_for(patient_preferences(current_user()))("flash_reminder_removed"), "success")
    return redirect(url_for("reminders_page", patient_id=reminder.patient_id))


@app.route("/api/reminders/today")
@require_login("patient")
def api_reminders():
    rows = reminders_for(current_user().id)
    return jsonify(reminders=[{"id": r["item"].id, "title": r["item"].title, "time": r["item"].scheduled_time,
                               "category": r["item"].category, "done": r["done"]} for r in rows])


@app.route("/family")
@require_login()
def family_page():
    p = selected_patient()
    members = FamilyMember.query.filter_by(patient_id=p.id).order_by(FamilyMember.name).all() if p else []
    return render_template("family.html", patient=p, members=members,
                           patients=caregiver_patients() if current_user().role == "caregiver" else [])


@app.route("/family/add", methods=["POST"])
@require_login("caregiver")
def family_add():
    p = selected_patient()
    if not p:
        abort(400)
    name = request.form.get("name", "").strip()[:90]
    relation = request.form.get("relation", "").strip()[:55]
    file = request.files.get("photo")
    data = file.read(1_000_001) if file else b""
    mime = file.mimetype if file else ""
    # Magic-byte checks, not just untrusted browser MIME type.
    if mime == "image/jpeg" and data.startswith(b"\xff\xd8\xff"):
        pass
    elif mime == "image/png" and data.startswith(b"\x89PNG\r\n\x1a\n"):
        pass
    elif mime == "image/webp" and data.startswith(b"RIFF") and data[8:12] == b"WEBP":
        pass
    else:
        mime = ""
    if not name or not relation or not mime or not 0 < len(data) <= 1_000_000:
        flash("Enter a name and relationship, and upload a JPG, PNG or WebP photo under 1 MB.", "error")
    else:
        db.session.add(FamilyMember(patient_id=p.id, name=name, relation=relation, image_bytes=data, mime_type=mime))
        db.session.commit()
        flash("Family photo saved privately.", "success")
    return redirect(url_for("family_page", patient_id=p.id))


@app.route("/family/photo/<int:member_id>")
@require_login()
def family_photo(member_id):
    member = db.session.get(FamilyMember, member_id)
    if not member or not allowed_patient(member.patient_id):
        abort(404)
    response = send_file(io.BytesIO(member.image_bytes), mimetype=member.mime_type, max_age=0)
    response.headers["Cache-Control"] = "private, no-store"
    return response


@app.route("/family/<int:member_id>/delete", methods=["POST"])
@require_login("caregiver")
def family_delete(member_id):
    member = db.session.get(FamilyMember, member_id)
    if not member or not allowed_patient(member.patient_id):
        abort(404)
    patient_id = member.patient_id
    db.session.delete(member)
    db.session.commit()
    flash("Photo removed.", "success")
    return redirect(url_for("family_page", patient_id=patient_id))


@app.route("/caregiver/link", methods=["POST"])
@require_login("caregiver")
def caregiver_link():
    code = request.form.get("invite_code", "").strip().upper()
    p = User.query.filter_by(role="patient", invite_code=code).first() if code else None
    if not p:
        flash("That patient connection code was not found.", "error")
    elif CareLink.query.filter_by(caregiver_id=current_user().id, patient_id=p.id).first():
        flash("A request to this patient has already been sent.", "info")
    else:
        db.session.add(CareLink(caregiver_id=current_user().id, patient_id=p.id))
        db.session.commit()
        flash(f"Your request was sent to {p.name}. They must approve it before you can view their information.", "success")
    return redirect(url_for("dashboard"))


@app.route("/caregiver/approve/<int:link_id>", methods=["POST"])
@require_login("patient")
def caregiver_approve(link_id):
    link = db.session.get(CareLink, link_id)
    if not link or link.patient_id != current_user().id or link.status != "pending":
        abort(404)
    link.status = "approved"
    db.session.commit()
    flash("Caregiver approved. You can revoke their access whenever you need.", "success")
    return redirect(url_for("dashboard"))


@app.route("/caregiver/revoke/<int:link_id>", methods=["POST"])
@require_login("patient")
def caregiver_revoke(link_id):
    link = db.session.get(CareLink, link_id)
    if not link or link.patient_id != current_user().id:
        abort(404)
    active_calls = VideoCall.query.filter_by(patient_id=link.patient_id, caregiver_id=link.caregiver_id).filter(
        VideoCall.status.in_(["ringing", "accepted"])).all()
    for call in active_calls:
        call.status = "ended"
        VideoSignal.query.filter_by(call_id=call.id).delete(synchronize_session=False)
    db.session.delete(link)
    db.session.commit()
    flash("Caregiver access removed.", "success")
    return redirect(url_for("dashboard"))


@app.route("/caregiver/support/<int:checkin_id>/review", methods=["POST"])
@require_login("caregiver")
def caregiver_support_review(checkin_id):
    """Review means 'seen in dashboard', never 'patient was contacted'."""
    checkin = db.session.get(WellbeingCheck, checkin_id)
    if not checkin or checkin.feeling != "need_help" or not allowed_patient(checkin.patient_id):
        abort(404)
    existing = CaregiverSupportReview.query.filter_by(
        caregiver_id=current_user().id, checkin_id=checkin.id
    ).first()
    if not existing:
        db.session.add(CaregiverSupportReview(
            caregiver_id=current_user().id, checkin_id=checkin.id
        ))
        db.session.commit()
    flash("Marked as reviewed on your dashboard. This does not contact the patient.", "success")
    if request.form.get("return_to") == "patient":
        return redirect(url_for("caregiver_detail", patient_id=checkin.patient_id, _anchor="wellbeing"))
    return redirect(url_for("dashboard", _anchor="support-requests"))


@app.route("/caregiver/patient/<int:patient_id>")
@require_login("caregiver")
def caregiver_detail(patient_id):
    p = patient_or_403(patient_id)
    stats = performance(patient_id)
    results = GameResult.query.filter_by(patient_id=patient_id).order_by(GameResult.id.desc()).limit(20).all()
    checks = (WellbeingCheck.query.filter_by(patient_id=patient_id)
              .order_by(WellbeingCheck.checked_date.desc()).limit(14).all())
    reviewed = {row.checkin_id for row in CaregiverSupportReview.query.filter(
        CaregiverSupportReview.caregiver_id == current_user().id,
        CaregiverSupportReview.checkin_id.in_([c.id for c in checks])
    ).all()} if checks else set()
    return render_template("patient_detail.html", patient=p, stats=stats, results=results,
                           reminders=reminders_for(patient_id), recent_checkins=checks,
                           reviewed_support=reviewed)



# One-tap caregiver video calls: browser-to-browser WebRTC media. This server
# carries only short-lived offer/answer/ICE signaling; it cannot record calls.
# Both participants must be signed in AND retain an approved care link.
CALL_RING_SECONDS = 180
CALL_MAX_MINUTES = 45


def call_expired(call):
    expiry = call.expires_at
    if expiry.tzinfo is None:  # SQLite returns naive DateTime even with timezone=True.
        expiry = expiry.replace(tzinfo=timezone.utc)
    return now_utc() >= expiry


def call_approved(call):
    return CareLink.query.filter_by(patient_id=call.patient_id,
                                    caregiver_id=call.caregiver_id,
                                    status="approved").first() is not None


def call_or_404(token):
    call = db.session.get(VideoCall, token)
    if (not call or current_user().id not in (call.patient_id, call.caregiver_id)
            or not call_approved(call)):
        abort(404)
    if call.status in ("ringing", "accepted") and call_expired(call):
        call.status = "expired"
        VideoSignal.query.filter_by(call_id=call.id).delete(synchronize_session=False)
        db.session.commit()
    return call


def peer_name(call):
    peer_id = call.caregiver_id if current_user().id == call.patient_id else call.patient_id
    user = db.session.get(User, peer_id)
    return user.name if user else "your loved one"


@app.route("/calls/start", methods=["POST"])
@require_login()
def start_video_call():
    u = current_user()
    raw = request.form.get("contact_id", "")
    if not raw.isdecimal():
        abort(400, "Choose a connected family member to call.")
    contact_id = int(raw)
    if contact_id == u.id:
        abort(400)
    if u.role == "patient":
        patient_id, caregiver_id = u.id, contact_id
    else:
        patient_id, caregiver_id = contact_id, u.id
    link = CareLink.query.filter_by(patient_id=patient_id,
                                    caregiver_id=caregiver_id,
                                    status="approved").first()
    if not link:
        abort(403)
    # Opportunistically clear old signaling offers, candidates and call tokens.
    # This avoids indefinite SDP/IP-metadata retention without a paid cron worker.
    stale = VideoCall.query.filter(VideoCall.expires_at < now_utc()-timedelta(hours=1)).limit(100).all()
    for old in stale:
        VideoSignal.query.filter_by(call_id=old.id).delete(synchronize_session=False)
        db.session.delete(old)
    # Reuse the pair's ongoing session; never create a surprise parallel call.
    live = (VideoCall.query.filter_by(patient_id=patient_id, caregiver_id=caregiver_id)
            .filter(VideoCall.status.in_(["ringing", "accepted"]))
            .order_by(VideoCall.created_at.desc()).limit(5).all())
    for call in live:
        if not call_expired(call):
            db.session.commit()  # Retain expired-call cleanup performed above.
            return redirect(url_for("video_call_page", token=call.id))
        call.status = "expired"
    call = VideoCall(id=secrets.token_urlsafe(24), patient_id=patient_id,
                     caregiver_id=caregiver_id, initiator_id=u.id,
                     status="ringing", expires_at=now_utc()+timedelta(seconds=CALL_RING_SECONDS))
    db.session.add(call)
    db.session.commit()
    return redirect(url_for("video_call_page", token=call.id))


@app.route("/video-call/<token>")
@require_login()
def video_call_page(token):
    call = call_or_404(token)
    return render_template("video_call.html", call=call, peer_name=peer_name(call),
                           caller=call.initiator_id == current_user().id,
                           turn_url=os.getenv("TURN_URL", ""),
                           turn_user=os.getenv("TURN_USERNAME", ""),
                           turn_password=os.getenv("TURN_PASSWORD", ""))


@app.route("/api/calls/incoming")
@require_login()
def incoming_calls():
    u = current_user()
    pairs = (VideoCall.query
             .filter(or_(VideoCall.patient_id == u.id, VideoCall.caregiver_id == u.id))
             .filter(VideoCall.initiator_id != u.id, VideoCall.status == "ringing",
                     VideoCall.expires_at > now_utc())
             .order_by(VideoCall.created_at.desc()).limit(5).all())
    return jsonify(calls=[{"id": c.id, "from": peer_name(c),
                           "url": url_for("video_call_page", token=c.id)}
                          for c in pairs if call_approved(c)])


@app.route("/api/calls/<token>/accept", methods=["POST"])
@require_login()
def accept_video_call(token):
    call = call_or_404(token)
    if call.initiator_id == current_user().id or call.status not in ("ringing", "accepted"):
        return jsonify(error="This incoming call is no longer available"), 409
    call.status = "accepted"
    call.expires_at = now_utc()+timedelta(minutes=CALL_MAX_MINUTES)
    db.session.commit()
    return jsonify(ok=True)


@app.route("/api/calls/<token>/decline", methods=["POST"])
@require_login()
def decline_video_call(token):
    call = call_or_404(token)
    if call.initiator_id == current_user().id or call.status != "ringing":
        return jsonify(error="This incoming call is no longer available"), 409
    call.status = "declined"
    VideoSignal.query.filter_by(call_id=call.id).delete(synchronize_session=False)
    db.session.commit()
    return jsonify(ok=True)


@app.route("/api/calls/<token>/end", methods=["POST"])
@require_login()
def end_video_call(token):
    call = call_or_404(token)
    if call.status in ("ringing", "accepted"):
        call.status = "ended"
        VideoSignal.query.filter_by(call_id=call.id).delete(synchronize_session=False)
        db.session.commit()
    return jsonify(ok=True)


@app.route("/api/calls/<token>/events")
@require_login()
def call_events(token):
    call = call_or_404(token)
    raw = request.args.get("after", "0")
    if not raw.isdecimal():
        return jsonify(error="Invalid cursor"), 400
    after = max(0, min(int(raw), 2**31-1))
    rows = (VideoSignal.query.filter_by(call_id=call.id)
            .filter(VideoSignal.id > after, VideoSignal.sender_id != current_user().id)
            .order_by(VideoSignal.id).limit(80).all())
    return jsonify(status=call.status, events=[{"id": row.id, "kind": row.kind,
                                                 "payload": json.loads(row.payload)} for row in rows])


@app.route("/api/calls/<token>/signal", methods=["POST"])
@require_login()
def signal_video_call(token):
    call = call_or_404(token)
    if call.status not in ("ringing", "accepted"):
        return jsonify(error="Call is no longer active"), 409
    body = request.get_json(silent=True) or {}
    kind, payload = body.get("kind"), body.get("payload")
    if kind not in ("offer", "answer", "candidate") or not isinstance(payload, dict):
        return jsonify(error="Invalid signal"), 400
    is_caller = current_user().id == call.initiator_id
    if kind == "offer" and not is_caller:
        return jsonify(error="Only the caller can send an offer"), 403
    if kind == "answer" and (is_caller or call.status != "accepted"):
        return jsonify(error="Only an answered call can send an answer"), 403
    if kind == "candidate" and not is_caller and call.status != "accepted":
        return jsonify(error="Answer the call before connecting"), 403
    if kind in ("offer", "answer") and (payload.get("type") != kind or
           not isinstance(payload.get("sdp"), str) or len(payload["sdp"]) > 20000):
        return jsonify(error="Invalid session description"), 400
    if kind == "candidate" and (not isinstance(payload.get("candidate"), str) or
           len(payload["candidate"]) > 6000):
        return jsonify(error="Invalid connection candidate"), 400
    value = json.dumps(payload, separators=(",", ":"))
    if len(value) > 24000:
        return jsonify(error="Signal is too large"), 413
    if VideoSignal.query.filter_by(call_id=call.id).count() >= 150:
        return jsonify(error="Too many connection messages"), 429
    db.session.add(VideoSignal(call_id=call.id, sender_id=current_user().id,
                               kind=kind, payload=value))
    db.session.commit()
    return jsonify(ok=True)


@app.errorhandler(403)
def forbidden(_):
    return render_template("error.html", title="This space is private", detail="You don't have access to that patient record."), 403


@app.errorhandler(404)
def missing(_):
    return render_template("error.html", title="Page not found", detail="The page may have moved or been removed."), 404


@app.errorhandler(400)
def bad_request(error):
    return render_template("error.html", title="Something needs checking", detail=str(getattr(error, "description", "Please review your request."))), 400


with app.app_context():
    db.create_all()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "5000")), debug=os.getenv("FLASK_DEBUG") == "1")
