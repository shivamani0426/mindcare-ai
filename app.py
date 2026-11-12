"""MindCare AI — accessible cognitive practice and caregiver support.

Educational, non-diagnostic mini project. No clinical inference is made from scores.
"""
from __future__ import annotations

import io
import os
import random
import re
import secrets
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from functools import wraps
from zoneinfo import ZoneInfo
from statistics import mean

from flask import (Flask, abort, flash, g, jsonify, redirect, render_template,
                   request, send_file, session, url_for)
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import UniqueConstraint, func, or_
from werkzeug.security import check_password_hash, generate_password_hash

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
db = SQLAlchemy(app)


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


def now_utc():
    return datetime.now(timezone.utc)


def today_local():
    """India uses Asia/Kolkata; never rely on server UTC midnight."""
    return datetime.now(ZoneInfo("Asia/Kolkata")).date()


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


def difficulty_for(patient_id, game):
    latest = (GameResult.query.filter_by(patient_id=patient_id, game_type=game)
              .order_by(GameResult.id.desc()).limit(4).all())
    if not latest:
        return 1
    level = latest[0].difficulty
    if len(latest) >= 3:
        recent = latest[:3]
        average_score = mean(x.score for x in recent)
        average_errors = mean(x.mistakes for x in recent)
        if average_score >= 82 and average_errors <= 2:
            level = min(3, level + 1)
        elif average_score < 48 or average_errors >= 5:
            level = max(1, level - 1)
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
    if "csrf_token" not in session:
        session["csrf_token"] = secrets.token_urlsafe(32)
    if request.method in ("POST", "PUT", "PATCH", "DELETE"):
        provided = request.headers.get("X-CSRF-Token") or request.form.get("csrf_token", "")
        if not secrets.compare_digest(provided, session["csrf_token"]):
            abort(400, "Security check failed. Refresh the page and try again.")


@app.context_processor
def inject_common():
    return dict(me=current_user(), csrf_token=session.get("csrf_token"), GAMES=GAMES,
                CATEGORIES=CATEGORIES, LEVEL_NAMES=LEVEL_NAMES)


@app.after_request
def security_headers(response):
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    response.headers["Content-Security-Policy"] = ("default-src 'self'; img-src 'self' data:; style-src 'self'; "
                                                   "script-src 'self'; font-src 'self'; connect-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'none'")
    if current_user():
        response.headers["Cache-Control"] = "private, no-store"
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


@app.route("/register", methods=["GET", "POST"])
def register():
    if current_user():
        return redirect(url_for("dashboard"))
    if request.method == "POST":
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
            session.clear()
            session["uid"] = user.id
            session.permanent = True
            flash("Your MindCare space is ready!", "success")
            return redirect(url_for("dashboard"))
    return render_template("auth.html", mode="register")


@app.route("/login", methods=["GET", "POST"])
def login():
    if current_user():
        return redirect(url_for("dashboard"))
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        user = User.query.filter_by(email=email).first()
        if user and check_password_hash(user.password_hash, request.form.get("password", "")):
            session.clear()
            session["uid"] = user.id
            session.permanent = True
            flash("Welcome back!", "success")
            return redirect(url_for("dashboard"))
        flash("Email or password was not recognised.", "error")
    return render_template("auth.html", mode="login")


@app.route("/logout", methods=["POST"])
@require_login()
def logout():
    session.clear()
    return redirect(url_for("home"))


@app.route("/dashboard")
@require_login()
def dashboard():
    if current_user().role == "caregiver":
        patients = caregiver_patients()
        summaries = [{"patient": p, "stats": performance(p.id), "reminders": reminders_for(p.id)} for p in patients]
        pending = [{"link": link, "patient": db.session.get(User, link.patient_id)} for link in CareLink.query.filter_by(caregiver_id=current_user().id, status="pending").all()]
        return render_template("caregiver.html", summaries=summaries, pending=pending)
    stats = performance(current_user().id)
    reminders = reminders_for(current_user().id)
    pending_links = [{"link": link, "caregiver": db.session.get(User, link.caregiver_id)} for link in CareLink.query.filter_by(patient_id=current_user().id, status="pending").all()]
    approved_links = [{"link": link, "caregiver": db.session.get(User, link.caregiver_id)} for link in CareLink.query.filter_by(patient_id=current_user().id, status="approved").all()]
    recent = (GameResult.query.filter_by(patient_id=current_user().id)
              .order_by(GameResult.id.desc()).limit(4).all())
    return render_template("dashboard.html", stats=stats, reminders=reminders, recent=recent,
                           suggested=list(GAMES.items())[:5], pending_links=pending_links, approved_links=approved_links)


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
    return jsonify(ok=True, new_level=difficulty_for(current_user().id, slug), stats=performance(current_user().id))


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
        flash("Reminder added. Keep the app open to hear browser announcements.", "success")
    return redirect(url_for("reminders_page", patient_id=p.id))


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
    flash("Marked as done for today. This is a self-report, not verification of medicine intake.", "success")
    return redirect(request.form.get("next") if request.form.get("next") in ("/dashboard", "/reminders") else url_for("reminders_page"))


@app.route("/reminders/<int:reminder_id>/delete", methods=["POST"])
@require_login()
def reminder_delete(reminder_id):
    reminder = db.session.get(Reminder, reminder_id)
    if not reminder or not allowed_patient(reminder.patient_id):
        abort(404)
    reminder.active = False
    db.session.commit()
    flash("Reminder removed.", "success")
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
    db.session.delete(link)
    db.session.commit()
    flash("Caregiver access removed.", "success")
    return redirect(url_for("dashboard"))


@app.route("/caregiver/patient/<int:patient_id>")
@require_login("caregiver")
def caregiver_detail(patient_id):
    p = patient_or_403(patient_id)
    stats = performance(patient_id)
    results = GameResult.query.filter_by(patient_id=patient_id).order_by(GameResult.id.desc()).limit(20).all()
    return render_template("patient_detail.html", patient=p, stats=stats, results=results,
                           reminders=reminders_for(patient_id))


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
