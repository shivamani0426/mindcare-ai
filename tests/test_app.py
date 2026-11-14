"""Run with `pip install -r requirements.txt pytest` then `pytest -q`."""
import os
os.environ["DATABASE_URL"] = "sqlite://"
os.environ["SECRET_KEY"] = "test-secret-only-not-for-production"
os.environ["SECURE_COOKIES"] = "0"

import pytest
from app import app, db, User, CareLink, GameResult, VideoCall, VideoSignal, WellbeingCheck, EmergencyContact, PatientPreference, difficulty_for


@pytest.fixture
def client():
    app.config.update(TESTING=True, SESSION_COOKIE_SECURE=False)
    with app.app_context():
        db.drop_all()
        db.create_all()
    with app.test_client() as c:
        yield c
    with app.app_context():
        db.session.remove()
        db.drop_all()


def token(client, path="/"):
    client.get(path)
    with client.session_transaction() as s:
        return s["csrf_token"]


def register(client, name, email, role):
    return client.post("/register", data={"csrf_token": token(client, "/register"), "name": name,
        "email": email, "password": "very-long-demo-password", "role": role}, follow_redirects=True)


def logout(client):
    return client.post("/logout", data={"csrf_token": token(client, "/dashboard")}, follow_redirects=True)


def login(client, email):
    return client.post("/login", data={"csrf_token": token(client, "/login"), "email": email,
        "password": "very-long-demo-password"}, follow_redirects=True)


def test_health_and_registration(client):
    assert client.get("/health").json["status"] == "ok"
    resp = register(client, "Asha Sharma", "asha@example.org", "patient")
    assert b"Hello, Asha" in resp.data
    with app.app_context():
        patient = User.query.filter_by(email="asha@example.org").one()
        assert patient.invite_code and len(patient.invite_code) == 8


def test_csrf_required(client):
    assert client.post("/register", data={"name": "Unknown"}).status_code == 400


def test_patient_must_approve_caregiver(client):
    register(client, "Asha Sharma", "asha@example.org", "patient")
    with app.app_context():
        patient = User.query.filter_by(email="asha@example.org").one()
        patient_id, code = patient.id, patient.invite_code
    logout(client)
    register(client, "Ramesh", "ramesh@example.org", "caregiver")
    resp = client.post("/caregiver/link", data={"csrf_token": token(client, "/dashboard"),
                         "invite_code": code}, follow_redirects=True)
    assert b"request was sent" in resp.data
    assert client.get(f"/caregiver/patient/{patient_id}").status_code == 403
    with app.app_context():
        link_id = CareLink.query.one().id
    logout(client)
    login(client, "asha@example.org")
    client.post(f"/caregiver/approve/{link_id}", data={"csrf_token": token(client, "/dashboard")})
    logout(client)
    login(client, "ramesh@example.org")
    assert client.get(f"/caregiver/patient/{patient_id}").status_code == 200
    logout(client)
    login(client, "asha@example.org")
    client.post(f"/caregiver/revoke/{link_id}", data={"csrf_token": token(client, "/dashboard")})
    logout(client)
    login(client, "ramesh@example.org")
    assert client.get(f"/caregiver/patient/{patient_id}").status_code == 403


def test_reminders_and_game_saved(client):
    register(client, "Asha Sharma", "asha@example.org", "patient")
    t = token(client, "/reminders")
    resp = client.post("/reminders/create", data={"csrf_token": t, "title": "Morning medicine",
                    "category": "medicine", "scheduled_time": "09:00"}, follow_redirects=True)
    assert b"Morning medicine" in resp.data
    assert client.get("/api/reminders/today").json["reminders"][0]["done"] is False
    reminder_id=client.get("/api/reminders/today").json["reminders"][0]["id"]
    client.post(f"/reminders/{reminder_id}/check", data={"csrf_token": token(client, "/dashboard")})
    assert client.get("/api/reminders/today").json["reminders"][0]["done"] is True
    data={"game":"cards","score":91,"mistakes":0,"seconds":55,"difficulty":1}
    response=client.post("/api/games/finish", json=data, headers={"X-CSRF-Token":token(client,"/games")})
    assert response.json["ok"] and response.json["stats"]["count"] == 1
    with app.app_context():
        assert GameResult.query.count() == 1


def test_adaptive_level_after_three_good_games(client):
    register(client, "Asha Sharma", "asha@example.org", "patient")
    with app.app_context():
        patient_id=User.query.filter_by(email="asha@example.org").one().id
        for _ in range(3):
            db.session.add(GameResult(patient_id=patient_id, game_type="cards", score=91,
                                      mistakes=0, duration_seconds=35, difficulty=1))
        db.session.commit()
        assert difficulty_for(patient_id,"cards") == 2


def test_difficulty_changes_independently_and_only_one_level_per_streak(client):
    register(client, "Asha Sharma", "asha@example.org", "patient")
    with app.app_context():
        uid = User.query.filter_by(email="asha@example.org").one().id
        assert difficulty_for(uid, "cards") == 1
        assert difficulty_for(uid, "puzzle") == 1

        for _ in range(2):
            db.session.add(GameResult(patient_id=uid,game_type="cards",score=95,
                                      mistakes=0,duration_seconds=40,difficulty=1))
        db.session.commit()
        assert difficulty_for(uid, "cards") == 2
        assert difficulty_for(uid, "puzzle") == 1

        # One success at the new level must NOT immediately leap to level 3,
        # even when the previous two low-level games were excellent.
        db.session.add(GameResult(patient_id=uid,game_type="cards",score=96,
                                  mistakes=0,duration_seconds=50,difficulty=2))
        db.session.commit()
        assert difficulty_for(uid, "cards") == 2

        db.session.add(GameResult(patient_id=uid,game_type="cards",score=93,
                                  mistakes=0,duration_seconds=50,difficulty=2))
        db.session.commit()
        assert difficulty_for(uid, "cards") == 3

        # Repeated difficulty at level 3 steps down only one level.
        for _ in range(2):
            db.session.add(GameResult(patient_id=uid,game_type="cards",score=30,
                                      mistakes=7,duration_seconds=180,difficulty=3))
        db.session.commit()
        assert difficulty_for(uid, "cards") == 2


def test_api_returns_next_level_after_two_confident_plays(client):
    register(client,"Asha Sharma","asha@example.org","patient")
    headers={"X-CSRF-Token":token(client,"/games")}
    payload={"game":"numbers","score":100,"mistakes":0,"seconds":45,"difficulty":1}
    first=client.post("/api/games/finish",json=payload,headers=headers)
    assert first.status_code == 200
    assert first.json["new_level"] == 1
    assert first.json["level_change"] == 0
    second=client.post("/api/games/finish",json=payload,headers=headers)
    assert second.status_code == 200
    assert second.json["new_level"] == 2
    assert second.json["level_change"] == 1
    assert second.json["next_level_name"] == "Growing"
    assert b'Growing level' in client.get('/games/numbers').data


@pytest.mark.parametrize("game", ["cards", "words", "numbers", "pictures", "puzzle", "family"])
def test_difficulty_goes_back_down_after_struggle_for_every_game(client, game):
    register(client, "Asha Sharma", "asha@example.org", "patient")
    with app.app_context():
        patient = User.query.filter_by(email="asha@example.org").one()
        # Start directly at Challenge to exercise a supported historical state.
        for score in (54, 49):
            db.session.add(GameResult(patient_id=patient.id, game_type=game,
                                      difficulty=3, score=score, mistakes=5,
                                      duration_seconds=110))
        db.session.commit()
        assert difficulty_for(patient.id, game) == 2
        # Once a lower-level game is played, don't bounce up based on old rows.
        db.session.add(GameResult(patient_id=patient.id, game_type=game,
                                  difficulty=2, score=50, mistakes=4,
                                  duration_seconds=70))
        db.session.commit()
        assert difficulty_for(patient.id, game) == 2
        db.session.add(GameResult(patient_id=patient.id, game_type=game,
                                  difficulty=2, score=58, mistakes=4,
                                  duration_seconds=75))
        db.session.commit()
        assert difficulty_for(patient.id, game) == 1


def test_severe_difficulty_eases_after_one_very_poor_game(client):
    register(client, "Asha Sharma", "asha@example.org", "patient")
    with app.app_context():
        patient_id = User.query.filter_by(email="asha@example.org").one().id
        db.session.add(GameResult(patient_id=patient_id, game_type="words", difficulty=3,
                                  score=20, mistakes=6, duration_seconds=130))
        db.session.commit()
        assert difficulty_for(patient_id, "words") == 2


def test_live_api_can_raise_then_lower_game_difficulty(client):
    register(client, "Asha Sharma", "asha@example.org", "patient")
    headers = {"X-CSRF-Token": token(client, "/games")}
    def finish(level, score, mistakes):
        return client.post("/api/games/finish", json={"game":"numbers", "score":score,
             "mistakes":mistakes, "seconds":60, "difficulty":level}, headers=headers)
    assert finish(1,95,0).json["new_level"] == 1
    assert finish(1,95,0).json["new_level"] == 2
    first = finish(2,55,4)
    assert first.status_code == 200 and first.json["new_level"] == 2
    second = finish(2,55,4)
    assert second.status_code == 200
    assert second.json["new_level"] == 1 and second.json["level_change"] == -1
    assert b'Gentle level' in client.get('/games/numbers').data


def connect_accounts(client):
    register(client, "Asha Sharma", "asha@example.org", "patient")
    with app.app_context():
        patient = User.query.filter_by(email="asha@example.org").one()
        pid, code = patient.id, patient.invite_code
    logout(client)
    register(client, "Sita Care", "sita@example.org", "caregiver")
    with app.app_context():
        cid = User.query.filter_by(email="sita@example.org").one().id
    client.post("/caregiver/link", data={"csrf_token":token(client),"invite_code":code})
    with app.app_context():
        link_id = CareLink.query.one().id
    logout(client)
    login(client, "asha@example.org")
    client.post(f"/caregiver/approve/{link_id}", data={"csrf_token":token(client)})
    return pid, cid, link_id


def test_only_approved_users_can_start_a_call(client):
    register(client, "Asha Sharma", "asha@example.org", "patient")
    response = client.post('/calls/start', data={'csrf_token':token(client), 'contact_id':'9999'})
    assert response.status_code == 403
    logout(client)
    assert client.get('/api/calls/incoming').status_code == 302


def test_video_call_consent_signaling_and_leave(client):
    pid, cid, link_id = connect_accounts(client)
    start = client.post('/calls/start', data={"csrf_token":token(client), "contact_id":str(cid)})
    assert start.status_code == 302
    address = start.headers['Location']
    call_id = address.rsplit('/',1)[-1]
    assert client.get(address).status_code == 200
    assert 'camera=(self)' in client.get(address).headers['Permissions-Policy']
    assert b'Video call with Sita Care' in client.get(address).data
    offer = {"type":"offer","sdp":"v=0\r\n"}
    t = token(client)
    assert client.post(f'/api/calls/{call_id}/signal',json={"kind":"offer","payload":offer},
                       headers={"X-CSRF-Token":t}).status_code == 200
    assert client.get('/api/calls/incoming').json['calls'] == []
    logout(client)
    login(client, 'sita@example.org')
    incoming = client.get('/api/calls/incoming').json['calls']
    assert len(incoming) == 1 and incoming[0]['id'] == call_id
    events = client.get(f'/api/calls/{call_id}/events').json['events']
    assert len(events) == 1 and events[0]['kind'] == 'offer'
    assert client.post(f'/api/calls/{call_id}/signal',json={"kind":"answer","payload":{"type":"answer","sdp":"v=0"}},
                       headers={"X-CSRF-Token":token(client)}).status_code == 403
    assert client.post(f'/api/calls/{call_id}/accept',headers={"X-CSRF-Token":token(client)}).status_code == 200
    assert client.post(f'/api/calls/{call_id}/signal',json={"kind":"answer","payload":{"type":"answer","sdp":"v=0"}},
                       headers={"X-CSRF-Token":token(client)}).status_code == 200
    logout(client)
    login(client, 'asha@example.org')
    events = client.get(f'/api/calls/{call_id}/events').json['events']
    assert len(events) == 1 and events[0]['kind'] == 'answer'
    assert client.post(f'/api/calls/{call_id}/end',headers={"X-CSRF-Token":token(client)}).status_code == 200
    assert client.get(f'/api/calls/{call_id}/events').json['status'] == 'ended'
    with app.app_context():
        assert VideoSignal.query.filter_by(call_id=call_id).count() == 0


def test_revoking_caregiver_access_invalidates_video_call(client):
    pid, cid, link_id = connect_accounts(client)
    response = client.post('/calls/start',data={"csrf_token":token(client),"contact_id":str(cid)})
    url = response.headers['Location']
    assert client.get(url).status_code == 200
    client.post(f'/caregiver/revoke/{link_id}',data={"csrf_token":token(client)})
    assert client.get(url).status_code == 404
    assert client.get(url.replace('/video-call/','/api/calls/')+'/events').status_code == 404
    logout(client)
    login(client,'sita@example.org')
    assert client.get(url).status_code == 404
    assert client.get('/api/calls/incoming').json['calls'] == []


def test_patient_today_checkin_and_edit_same_day(client):
    register(client, "Asha Sharma", "asha@example.org", "patient")
    assert b"How are you feeling today?" in client.get("/dashboard").data
    t = token(client, "/dashboard")
    response = client.post("/wellbeing/check-in", data={"csrf_token":t,"feeling":"happy","note":"Nice morning"}, follow_redirects=True)
    assert response.status_code == 200 and b"check-in is saved" in response.data
    response = client.post("/wellbeing/check-in", data={"csrf_token":t,"feeling":"need_help","note":"Please call"}, follow_redirects=True)
    assert b"does not send an alert" in response.data
    with app.app_context():
        checks=WellbeingCheck.query.all()
        assert len(checks)==1 and checks[0].feeling=="need_help" and checks[0].note=="Please call"
    assert client.post("/wellbeing/check-in", data={"csrf_token":t,"feeling":"unknown"}).status_code==400


def test_help_contact_privacy_validation_and_deletion(client):
    register(client, "Asha", "asha@example.org", "patient")
    t=token(client,"/help")
    bad=client.post("/help/contacts/add",data={"csrf_token":t,"name":"Priya","relation":"Daughter","phone":"javascript:alert(1)"})
    assert bad.status_code==400
    ok=client.post("/help/contacts/add",data={"csrf_token":t,"name":"Priya","relation":"Daughter","phone":"+91 98765 43210"},follow_redirects=True)
    assert b"tel:+919876543210" in ok.data and b"tel:112" in ok.data
    with app.app_context():
        contact=EmergencyContact.query.one()
        cid=contact.id
    logout(client)
    register(client,"Ram","ram@example.org","patient")
    assert b"tel:+919876543210" not in client.get("/help").data
    assert client.post(f"/help/contacts/{cid}/delete", data={"csrf_token":token(client,"/help")}).status_code == 404
    logout(client)
    login(client,"asha@example.org")
    resp=client.post(f"/help/contacts/{cid}/delete",data={"csrf_token":token(client,"/help")},follow_redirects=True)
    assert resp.status_code==200
    with app.app_context(): assert EmergencyContact.query.count()==0


def test_patient_settings_persist_and_restrict_caregivers(client):
    register(client,"Asha Sharma","asha@example.org","patient")
    t=token(client,"/settings")
    response=client.post("/settings",data={"csrf_token":t,"language":"kn","large_text":"on","high_contrast":"on","reduced_motion":"on"},follow_redirects=True)
    assert response.status_code==200
    content=client.get("/dashboard").data.decode("utf-8")
    assert "ಇಂದಿನ ದಿನ" in content and 'high-contrast' in content and 'reduced-motion' in content
    with app.app_context():
        p=PatientPreference.query.one()
        assert p.language=="kn" and p.large_text and p.high_contrast and p.reduced_motion
    assert client.post("/settings",data={"csrf_token":t,"language":"zz"}).status_code==400
    logout(client)
    register(client,"Caregiver","care@example.org","caregiver")
    assert client.get("/settings").status_code==403
    assert client.get("/help").status_code==403
    assert client.post("/wellbeing/check-in",data={"csrf_token":token(client,"/dashboard"),"feeling":"happy"}).status_code==403


def test_patient_checkins_not_mixed_between_accounts(client):
    register(client,"Asha","asha@example.org","patient")
    client.post("/wellbeing/check-in",data={"csrf_token":token(client,"/dashboard"),"feeling":"tired"})
    logout(client)
    register(client,"Lila","lila@example.org","patient")
    assert b"checkin-saved" not in client.get("/dashboard").data
    client.post("/wellbeing/check-in",data={"csrf_token":token(client,"/dashboard"),"feeling":"happy"})
    with app.app_context():
        assert WellbeingCheck.query.count()==2
        assert len({x.patient_id for x in WellbeingCheck.query.all()})==2


def test_help_phone_links_explain_device_limitations_and_allow_copy(client):
    """Phone numbers remain private to the patient and never trigger server-side calls."""
    register(client, "Leela", "leela-phone@example.org", "patient")
    page = client.get("/help")
    assert page.status_code == 200
    assert b'href="tel:112"' in page.data
    assert b'data-phone-emergency="1"' in page.data
    assert b'data-phone-copy' in page.data
    assert b'id="phone-call-options"' in page.data
    assert b'patient-help-calls.js' in page.data
    response = client.post("/help/contacts/add", data={
        "csrf_token": token(client, "/help"), "name": "Priya",
        "relation": "Daughter", "phone": "+91 98765 43210",
    }, follow_redirects=True)
    assert response.status_code == 200
    assert b'href="tel:+919876543210"' in response.data
    assert b'data-phone-number="+919876543210"' in response.data
    assert b'aria-label="Copy phone number for Priya"' in response.data


def test_whatsapp_contact_chat_links_are_patient_only_and_preserve_phone_call_options(client):
    register(client, "Leela", "leela-wa@example.org", "patient")
    page = client.get("/help")
    assert page.status_code == 200
    assert b"Call family on WhatsApp" in page.data
    assert b"tel:112" in page.data
    assert b"wa.me/112" not in page.data
    assert b"tap the phone icon" in page.data

    t = token(client, "/help")
    response = client.post("/help/contacts/add", data={
        "csrf_token": t, "name": "Priya", "relation": "Daughter",
        "phone": "9876543210",
    }, follow_redirects=True)
    assert response.status_code == 200
    assert b'href="https://wa.me/919876543210"' in response.data
    assert b'href="tel:9876543210"' in response.data
    assert b'target="_blank" rel="noopener noreferrer external"' in response.data
    assert b"Then tap" in response.data
    assert b"wa.me/112" not in response.data

    logout(client)
    register(client, "Other Patient", "other-wa@example.org", "patient")
    assert b"wa.me/919876543210" not in client.get("/help").data
    logout(client)
    register(client, "Caregiver", "care-wa@example.org", "caregiver")
    assert client.get("/help").status_code == 403


@pytest.mark.parametrize("phone, expected", [
    ("9876543210", "https://wa.me/919876543210"),
    ("919876543210", "https://wa.me/919876543210"),
    ("+919876543210", "https://wa.me/919876543210"),
    ("+14155552671", "https://wa.me/14155552671"),
    ("112", ""),
    ("javascript:alert(1)", ""),
    ("+01987654321", ""),
    ("09876543210", ""),
    ("14155552671", ""),
    ("", ""),
])
def test_whatsapp_chat_url_does_not_guess_non_indian_country_code(phone, expected):
    from app import whatsapp_chat_url
    assert whatsapp_chat_url(phone) == expected


def test_simple_dashboard_persists_and_returns_to_full_view(client):
    register(client, "Patient Asha", "simple@example.org", "patient")
    full = client.get("/dashboard")
    assert b"patient-mode-shortcut" in full.data
    assert b"Your activity" in full.data
    bad = client.post("/patient/view-mode", data={
        "csrf_token": token(client, "/dashboard"), "simplified": "sometimes"})
    assert bad.status_code == 400
    response = client.post("/patient/view-mode", data={
        "csrf_token": token(client, "/dashboard"), "simplified": "1"},follow_redirects=True)
    assert response.status_code == 200
    assert b"simple-dashboard" in response.data
    assert b"simple-feelings" in response.data
    assert b"Your activity" not in response.data
    assert b"href=\"tel:112\"" in response.data
    assert b"patient-notifications.js" in response.data
    logout(client)
    login(client, "simple@example.org")
    assert b"simple-dashboard" in client.get("/dashboard").data
    response = client.post("/patient/view-mode", data={
        "csrf_token": token(client, "/dashboard"), "simplified": "0"},follow_redirects=True)
    assert b"patient-mode-shortcut" in response.data
    assert b"simple-dashboard" not in response.data


def test_simple_mode_settings_and_caregiver_separation(client):
    register(client, "Patient Asha", "simple-prefs@example.org", "patient")
    response = client.post("/settings", data={
        "csrf_token": token(client, "/settings"), "language": "hi",
        "large_text": "on", "simplified_mode": "on", "high_contrast":"on",
    }, follow_redirects=True)
    assert response.status_code == 200
    assert b'name="simplified_mode" checked' in response.data
    assert "आसान मरीज डैशबोर्ड" in response.get_data(as_text=True)
    assert "मेरी याद दिलाने वाली बातें" in client.get("/dashboard").get_data(as_text=True)
    logout(client)
    register(client, "Caregiver Test", "simple-caregiver@example.org", "caregiver")
    assert client.post("/patient/view-mode", data={
        "csrf_token": token(client, "/dashboard"), "simplified": "1"
    }).status_code == 403
    assert b"simple-dashboard" not in client.get("/dashboard").data


def test_patient_can_edit_own_contact_without_breaking_whatsapp(client):
    register(client, "Patient Asha", "edit-contacts@example.org", "patient")
    client.post("/help/contacts/add", data={
        "csrf_token": token(client, "/help"), "name": "Maya",
        "relation": "Daughter", "phone": "+919876543210"
    })
    with app.app_context():
        ident = EmergencyContact.query.one().id
    page = client.get("/help")
    assert b"contact-edit-details" in page.data
    assert b"wa.me/919876543210" in page.data
    bad = client.post(f"/help/contacts/{ident}/edit", data={
        "csrf_token": token(client, "/help"), "name": "<script>",
        "relation": "Friend", "phone":"tel:9999999999"
    })
    assert bad.status_code == 400
    update = client.post(f"/help/contacts/{ident}/edit", data={
        "csrf_token": token(client, "/help"), "name": "Family Maya",
        "relation": "Sister", "phone":"+91 91234 56789"
    },follow_redirects=True)
    assert update.status_code == 200
    assert b"wa.me/919123456789" in update.data
    assert b"tel:+919123456789" in update.data
    assert b"tel:112" in update.data
    logout(client)
    register(client, "Other Patient", "edit-other@example.org", "patient")
    forbidden = client.post(f"/help/contacts/{ident}/edit", data={
        "csrf_token": token(client, "/help"),"name":"Wrong Person",
        "relation":"Friend","phone":"9876543210"
    })
    assert forbidden.status_code == 404
    assert b"wa.me/919123456789" not in client.get("/help").data


def test_reminder_edit_updates_schedule_resets_today_tick_and_rejects_cross_patient(client):
    register(client, "Patient Asha", "edit-reminders@example.org", "patient")
    added = client.post("/reminders/create", data={
        "csrf_token": token(client, "/reminders"),"title":"Morning",
        "category":"medicine","scheduled_time":"09:00"
    },follow_redirects=True)
    assert added.status_code == 200
    with app.app_context():
        from app import Reminder
        rid = Reminder.query.one().id
    client.post(f"/reminders/{rid}/check", data={
        "csrf_token": token(client, "/dashboard")
    })
    with app.app_context():
        from app import ReminderCheck
        assert ReminderCheck.query.filter_by(reminder_id=rid).count() == 1
    changed = client.post(f"/reminders/{rid}/edit",data={
        "csrf_token": token(client, "/reminders"),
        "title": "Afternoon medicine", "category":"medicine",
        "scheduled_time":"15:30","notes":"With water", "on_date":""
    },follow_redirects=True)
    assert changed.status_code == 200
    assert b"Afternoon medicine" in changed.data
    assert b'15:30' in changed.data
    assert b"reminder-edit-details" in changed.data
    with app.app_context():
        from app import Reminder, ReminderCheck
        assert Reminder.query.get(rid).notes == "With water"
        assert ReminderCheck.query.filter_by(reminder_id=rid).count() == 0
    invalid = client.post(f"/reminders/{rid}/edit",data={
        "csrf_token":token(client,"/reminders"),"title":"",
        "category":"medicine","scheduled_time":"55:90","on_date":""
    })
    assert invalid.status_code == 400
    logout(client)
    register(client, "Other Patient", "reminders-other@example.org", "patient")
    assert client.post(f"/reminders/{rid}/edit",data={
        "csrf_token":token(client,"/reminders"),"title":"Hacked",
        "category":"activity","scheduled_time":"10:00","on_date":""
    }).status_code == 404


def test_need_support_shows_explicit_contact_action_not_false_alert(client):
    register(client, "Patient Asha", "support-cta@example.org", "patient")
    client.post("/help/contacts/add",data={
        "csrf_token":token(client,"/help"),"name":"My Son",
        "relation":"Son","phone":"9876543210"
    })
    result = client.post("/wellbeing/check-in",data={
        "csrf_token":token(client,"/dashboard"),"feeling":"need_help"
    },follow_redirects=True)
    assert result.status_code == 200
    assert b"support-help-box" in result.data
    assert b"wa.me/919876543210" in result.data
    assert b"did not notify anyone" in result.data
    assert b"patient-mode-shortcut" in result.data
    with app.app_context():
        from app import WellbeingCheck
        assert WellbeingCheck.query.one().feeling == "need_help"


def test_patient_language_labels_are_localized_on_all_major_pages(client):
    register(client, "Patient Asha", "translation@example.org", "patient")
    for locale, examples in {
        "hi": [("dashboard", "आपकी गतिविधि"),("reminders", "प्यार से याद दिलाना"),
               ("games", "आराम से खेलें"),("family", "परिचित चेहरे, प्यारी यादें"),
               ("help", "व्हाट्सऐप पर परिवार को कॉल करें"),("settings", "हिन्दी")],
        "kn": [("dashboard", "ನಿಮ್ಮ ಚಟುವಟಿಕೆ"),("reminders", "ಮೃದುವಾದ ಜ್ಞಾಪನೆಗಳು"),
               ("games", "ನಿಮ್ಮ ವೇಗದಲ್ಲಿ ಆಡಿ"),("family", "ಪರಿಚಿತ ಮುಖಗಳು, ಸಿಹಿ ನೆನಪುಗಳು"),
               ("help", "ವಾಟ್ಸಾಪ್‌ನಲ್ಲಿ ಕುಟುಂಬಕ್ಕೆ ಕರೆ ಮಾಡಿ"),("settings", "ಕನ್ನಡ")]
    }.items():
        update=client.post("/settings",data={"csrf_token":token(client,"/settings"),
            "language":locale},follow_redirects=True)
        assert update.status_code==200
        for path, expected in examples:
            page=client.get("/"+path).get_data(as_text=True)
            assert expected in page, f"Missing {locale} translation on {path}: {expected}"
        play = client.get("/games/cards")
        assert play.status_code == 200
        assert b"game-i18n.js" in play.data
        assert b"patient-notifications.js" in play.data


def test_optional_notification_has_clear_device_limit_and_whatsapp_stays_intact(client):
    register(client, "Patient Asha", "notify@example.org", "patient")
    page=client.get("/reminders")
    assert page.status_code == 200
    assert b'id="reminder-notify-button"' in page.data
    assert b'id="reminder-notify-status"' in page.data
    assert b"while MindCare is open" in page.data
    help_page=client.get("/help").data
    assert b"whatsapp-howto" in help_page
    assert b'href="tel:112"' in help_page
    assert b"guest-voice" not in help_page


def test_patient_translation_key_parity_and_template_coverage():
    from pathlib import Path
    import re
    from patient_labels import PATIENT_LABELS
    from app import PATIENT_TEXT
    for locale in ("hi", "kn"):
        assert set(PATIENT_LABELS[locale]) == set(PATIENT_LABELS["en"])
        assert set(PATIENT_TEXT[locale]) == set(PATIENT_TEXT["en"])
    known = set(PATIENT_LABELS["en"]) | set(PATIENT_TEXT["en"])
    patient_pages = (
        "base.html", "dashboard.html", "dashboard_simple.html",
        "patient_help.html", "patient_settings.html", "reminders.html",
        "games.html", "play.html", "family.html"
    )
    missing = set()
    for name in patient_pages:
        content = (Path(__file__).resolve().parents[1] / "templates" / name).read_text()
        for key in re.findall(r"tr\('([^']+)'\)", content):
            # The dynamic category_, game_, trend_, level_ prefixes are resolved at runtime.
            if key.endswith("_"):
                continue
            if key not in known:
                missing.add((name, key))
    assert not missing, f"Untranslated patient page labels: {missing}"


def test_simple_mode_retains_uncompleted_reminders_after_due_time(client):
    register(client, "Leela", "overdue-simple@example.org", "patient")
    client.post("/reminders/create", data={
        "csrf_token":token(client, "/reminders"),
        "title":"Early morning breakfast","category":"meal","scheduled_time":"00:00"
    })
    response=client.post("/patient/view-mode", data={
        "csrf_token":token(client,"/dashboard"), "simplified":"1"
    },follow_redirects=True)
    assert response.status_code == 200
    assert b"Early morning breakfast" in response.data
    assert b"simple-next-time" in response.data


def test_patient_pref_translation_and_reminder_alert_scripts_remain_available(client):
    register(client, "Leela", "assets-simple@example.org", "patient")
    for asset in ("patient-notifications.js","game-i18n.js","voice.js"):
        response=client.get("/static/"+asset)
        assert response.status_code == 200
        assert b"function" in response.data or b"(() => {" in response.data
    response=client.post("/settings",data={
        "csrf_token":token(client,"/settings"),"language":"kn",
        "simplified_mode":"on","reduced_motion":"on"
    },follow_redirects=True)
    assert response.status_code == 200
    assert b"reduced-motion" in client.get("/dashboard").data
    assert "ನನ್ನ ಮುಂದಿನ ಜ್ಞಾಪನೆ" in client.get("/dashboard").get_data(as_text=True)


# Caregiver Dashboard 2.0: consent, daily summaries, wellbeing and reviews.
def setup_caregiver_v2(client):
    register(client, "Patient Asha", "care2-patient@example.org", "patient")
    with app.app_context():
        p = User.query.filter_by(email="care2-patient@example.org").one()
        patient_id, code = p.id, p.invite_code
    client.post("/wellbeing/check-in", data={
        "csrf_token": token(client, "/dashboard"), "feeling": "need_help",
        "note": "<script>not executable</script> I need a call"
    })
    client.post("/reminders/create", data={
        "csrf_token": token(client, "/reminders"), "title": "Breakfast",
        "category": "meal", "scheduled_time": "00:00"
    })
    logout(client)
    register(client, "Caregiver Priya", "care2-helper@example.org", "caregiver")
    client.post("/caregiver/link", data={
        "csrf_token": token(client, "/dashboard"), "invite_code": code
    })
    with app.app_context():
        link_id = CareLink.query.filter_by(patient_id=patient_id).one().id
        checkin_id = WellbeingCheck.query.filter_by(patient_id=patient_id).one().id
    return patient_id, link_id, checkin_id


def test_caregiver_v2_never_exposes_unapproved_patient_checkins(client):
    patient_id, link_id, checkin_id = setup_caregiver_v2(client)
    dashboard = client.get("/dashboard")
    assert dashboard.status_code == 200
    assert b"caregiver-v2" in dashboard.data
    assert b"Waiting for approval" in dashboard.data
    assert b"not executable" not in dashboard.data
    assert b"caregiver-patient-card" not in dashboard.data
    assert client.get(f"/caregiver/patient/{patient_id}").status_code == 403
    csrf = token(client, "/dashboard")
    assert client.post(f"/caregiver/support/{checkin_id}/review",
        data={"csrf_token": csrf}).status_code == 404
    assert client.post(f"/caregiver/support/{checkin_id}/review",
        data={}).status_code == 400
    logout(client)
    login(client, "care2-patient@example.org")
    client.post(f"/caregiver/approve/{link_id}", data={
        "csrf_token": token(client, "/dashboard")})
    logout(client)
    login(client, "care2-helper@example.org")
    dashboard = client.get("/dashboard")
    assert b"caregiver-patient-card" in dashboard.data
    assert b"Caregiver Dashboard" not in dashboard.data or b"caregiver-v2" in dashboard.data
    assert b"&lt;script&gt;not executable&lt;/script&gt;" in dashboard.data
    assert b'<script>not executable</script>' not in dashboard.data
    assert b"Caregiver Priya" not in dashboard.data or b"caregiver-v2" in dashboard.data
    assert b"Support check-ins" in dashboard.data
    assert b"Past-due reminders" in dashboard.data
    assert b"data-care-support=\"1\"" in dashboard.data
    assert b"patient-notifications.js" not in dashboard.data
    assert client.get("/static/caregiver-dashboard.js").status_code == 200


def test_caregiver_v2_support_review_is_private_idempotent_and_reopened(client):
    patient_id, link_id, checkin_id = setup_caregiver_v2(client)
    logout(client)
    login(client, "care2-patient@example.org")
    client.post(f"/caregiver/approve/{link_id}", data={
        "csrf_token": token(client, "/dashboard")})
    # Patient isn't authorized to mark a caregiver review.
    assert client.post(f"/caregiver/support/{checkin_id}/review", data={
        "csrf_token": token(client, "/dashboard")}).status_code == 403
    logout(client)
    login(client, "care2-helper@example.org")
    csrf = token(client, "/dashboard")
    reviewed = client.post(f"/caregiver/support/{checkin_id}/review", data={
        "csrf_token": csrf, "return_to": "patient"}, follow_redirects=True)
    assert reviewed.status_code == 200
    assert b"You marked this entry reviewed" in reviewed.data
    assert b"caregiver-wellbeing-entry" in reviewed.data
    assert client.post(f"/caregiver/support/{checkin_id}/review", data={
        "csrf_token": csrf}).status_code == 302
    with app.app_context():
        from app import CaregiverSupportReview
        assert CaregiverSupportReview.query.filter_by(checkin_id=checkin_id).count() == 1
    assert b"caregiver-support-item" not in client.get("/dashboard").data
    logout(client)
    login(client, "care2-patient@example.org")
    client.post("/wellbeing/check-in", data={
        "csrf_token": token(client, "/dashboard"), "feeling": "need_help",
        "note": "Please call soon"
    })
    with app.app_context():
        from app import CaregiverSupportReview
        assert CaregiverSupportReview.query.filter_by(checkin_id=checkin_id).count() == 0
    logout(client)
    login(client, "care2-helper@example.org")
    assert b"Please call soon" in client.get("/dashboard").data
    assert b"caregiver-support-item" in client.get("/dashboard").data
    assert b"caregiver-support-item" in client.get(f"/caregiver/patient/{patient_id}").data or b"caregiver-wellbeing-entry" in client.get(f"/caregiver/patient/{patient_id}").data
    # A revoked link immediately blocks the detail and review action.
    logout(client)
    login(client, "care2-patient@example.org")
    client.post(f"/caregiver/revoke/{link_id}", data={
        "csrf_token": token(client, "/dashboard")})
    logout(client)
    login(client, "care2-helper@example.org")
    assert client.get(f"/caregiver/patient/{patient_id}").status_code == 403
    assert client.post(f"/caregiver/support/{checkin_id}/review", data={
        "csrf_token": token(client, "/dashboard")}).status_code == 404
    assert b"Please call soon" not in client.get("/dashboard").data


def test_caregiver_v2_multiple_patients_have_independent_states(client):
    patient_id, link_id, checkin_id = setup_caregiver_v2(client)
    logout(client)
    register(client, "Patient Leela", "care2-other@example.org", "patient")
    with app.app_context():
        other = User.query.filter_by(email="care2-other@example.org").one()
        other_id, other_code = other.id, other.invite_code
    client.post("/wellbeing/check-in", data={
        "csrf_token": token(client, "/dashboard"), "feeling": "happy", "note": "Lovely day"
    })
    logout(client)
    login(client, "care2-helper@example.org")
    client.post("/caregiver/link", data={
        "csrf_token": token(client, "/dashboard"), "invite_code": other_code
    })
    with app.app_context():
        other_link = CareLink.query.filter_by(patient_id=other_id).one().id
    logout(client)
    login(client, "care2-patient@example.org")
    client.post(f"/caregiver/approve/{link_id}", data={
        "csrf_token": token(client, "/dashboard")})
    logout(client)
    login(client, "care2-helper@example.org")
    assert b"Patient Leela" not in client.get("/dashboard").data or b"Waiting for approval" in client.get("/dashboard").data
    assert client.get(f"/caregiver/patient/{other_id}").status_code == 403
    logout(client)
    login(client, "care2-other@example.org")
    client.post(f"/caregiver/approve/{other_link}", data={
        "csrf_token": token(client, "/dashboard")})
    logout(client)
    login(client, "care2-helper@example.org")
    dash = client.get("/dashboard").data
    assert dash.count(b'data-care-patient') == 2
    assert b"Lovely day" in dash
    assert b"Support check-ins" in dash
    assert b"data-care-support=\"1\"" in dash
    assert b"data-care-support=\"0\"" in dash
    assert client.get(f"/caregiver/patient/{other_id}").status_code == 200
    assert client.get(f"/caregiver/patient/{patient_id}").status_code == 200
    # A caregiver cannot access patients not connected to that caregiver.
    logout(client)
    register(client, "Unrelated Helper", "care2-unrelated@example.org", "caregiver")
    assert client.get(f"/caregiver/patient/{patient_id}").status_code == 403
    assert b"Lovely day" not in client.get("/dashboard").data
    assert client.post(f"/caregiver/support/{checkin_id}/review", data={
        "csrf_token": token(client, "/dashboard")}).status_code == 404


def test_one_tap_need_support_is_obvious_in_both_patient_views(client):
    register(client, "Patient Leela", "quick-support-patient@example.org", "patient")
    full = client.get("/dashboard")
    assert full.status_code == 200
    assert full.data.count(b'data-quick-support-button') == 1
    assert b'quick_support" value="1"' in full.data
    assert b'I need support' in full.data
    assert b"when they open MindCare" in full.data
    assert b'data-patient-today' in full.data
    assert b"patient-mode-shortcut" in full.data
    # No need to find a radio choice or fill a note to ask for support.
    submitted = client.post("/wellbeing/check-in", data={
        "csrf_token": token(client, "/dashboard"),
        "quick_support": "1", "feeling": "need_help"
    }, follow_redirects=True)
    assert submitted.status_code == 200
    assert b'patient-support-quick-saved' in submitted.data
    assert b'support-help-box' in submitted.data
    with app.app_context():
        assert WellbeingCheck.query.one().feeling == "need_help"
    simple = client.post("/patient/view-mode", data={
        "csrf_token": token(client, "/dashboard"), "simplified": "1"
    }, follow_redirects=True)
    assert simple.status_code == 200
    assert b"simple-dashboard" in simple.data
    assert simple.data.count(b'data-quick-support-button') == 1
    assert b'quick_support" value="1"' in simple.data
    assert b'patient-support-quick-saved' in simple.data
    assert b'href="tel:112"' in simple.data


def test_one_tap_support_preserves_patient_note_and_reopens_caregiver_queue(client):
    register(client, "Patient Leela", "quick-support-leela@example.org", "patient")
    with app.app_context():
        patient = User.query.filter_by(email="quick-support-leela@example.org").one()
        code, patient_id = patient.invite_code, patient.id
    created = client.post("/wellbeing/check-in", data={
        "csrf_token": token(client, "/dashboard"), "feeling": "need_help",
        "note": "Please check my morning medicine"
    })
    assert created.status_code == 302
    with app.app_context():
        record = WellbeingCheck.query.filter_by(patient_id=patient_id).one()
        checkin_id = record.id
    logout(client)
    register(client, "Caregiver Priya", "quick-support-priya@example.org", "caregiver")
    # An unapproved caregiver cannot see or review the support check-in.
    assert b"Please check my morning medicine" not in client.get("/dashboard").data
    assert client.post(f"/caregiver/support/{checkin_id}/review", data={
        "csrf_token": token(client, "/dashboard")
    }).status_code == 404
    client.post("/caregiver/link", data={
        "csrf_token": token(client, "/dashboard"), "invite_code": code
    })
    with app.app_context():
        link_id = CareLink.query.filter_by(patient_id=patient_id).one().id
    logout(client)
    login(client, "quick-support-leela@example.org")
    client.post(f"/caregiver/approve/{link_id}", data={
        "csrf_token": token(client, "/dashboard")
    })
    logout(client)
    login(client, "quick-support-priya@example.org")
    assert b"Please check my morning medicine" in client.get("/dashboard").data
    reviewed = client.post(f"/caregiver/support/{checkin_id}/review", data={
        "csrf_token": token(client, "/dashboard")
    }, follow_redirects=True)
    assert reviewed.status_code == 200
    assert b'caregiver-support-item' not in reviewed.data
    logout(client)
    login(client, "quick-support-leela@example.org")
    one_tap = client.post("/wellbeing/check-in", data={
        "csrf_token": token(client, "/dashboard"),
        "quick_support": "1", "feeling": "need_help"
    }, follow_redirects=True)
    assert one_tap.status_code == 200
    assert b'patient-support-quick-saved' in one_tap.data
    with app.app_context():
        from app import CaregiverSupportReview
        record = WellbeingCheck.query.filter_by(patient_id=patient_id).one()
        assert record.note == "Please check my morning medicine"
        assert CaregiverSupportReview.query.filter_by(checkin_id=checkin_id).count() == 0
    logout(client)
    login(client, "quick-support-priya@example.org")
    assert b"Please check my morning medicine" in client.get("/dashboard").data
    assert b'caregiver-support-item' in client.get("/dashboard").data
    logout(client)
    register(client, "Other Patient", "quick-support-other@example.org", "patient")
    assert b"Please check my morning medicine" not in client.get("/dashboard").data
    logout(client)
    register(client, "Unrelated Caregiver", "quick-support-unrelated@example.org", "caregiver")
    assert b"Please check my morning medicine" not in client.get("/dashboard").data


@pytest.mark.parametrize("lang,text", [
    ("en","I need support"),("hi","मुझे मदद चाहिए"),("kn","ನನಗೆ ಸಹಾಯ ಬೇಕು")
])
def test_quick_support_button_is_translated_for_patient(client,lang,text):
    register(client,"Patient Leela",f"quick-language-{lang}@example.org","patient")
    updated=client.post("/settings",data={
        "csrf_token":token(client,"/settings"),"language":lang
    },follow_redirects=True)
    assert updated.status_code==200
    assert text in client.get("/dashboard").get_data(as_text=True)


def test_auth_v3_professional_page_preserves_email_password_and_roles(client):
    login_page = client.get("/login")
    register_page = client.get("/register")
    assert login_page.status_code == 200 and register_page.status_code == 200
    assert b"auth-v2" in login_page.data
    assert b'auth-email-form' in login_page.data
    assert b"Google sign-in" in login_page.data
    assert b"Phone OTP" in login_page.data
    assert b"auth-phone-not-ready" in login_page.data
    assert b'href="/auth/google"' not in login_page.data
    assert b'auth-role-selector' in register_page.data
    assert b'value="caregiver"' in register_page.data
    assert b"auth-ui.js" in register_page.data
    # Users cannot accidentally enter a fake Google flow without credentials.
    assert client.get("/auth/google").status_code == 302
    assert client.post("/auth/phone-session", json={
        "id_token":"fake" * 70
    }, headers={"X-CSRF-Token": token(client,"/login")}).status_code == 503
    register(client, "Patient Sana", "auth-legacy@example.org", "patient")
    security = client.get("/account/security")
    assert security.status_code == 200
    assert b"Account security" in security.data
    assert b"auth-account-link" in client.get("/dashboard").data
    logout(client)
    login(client, "auth-legacy@example.org")
    assert b"Hello, Patient" in client.get("/dashboard").data


def test_phone_otp_server_requires_verified_identity_before_account_creation(client, monkeypatch):
    import app as authapp
    assert client.get("/auth/complete").status_code == 302
    assert client.post("/auth/complete", data={
        "csrf_token": token(client, "/login"), "role":"caregiver", "name":"Attacker"
    }).status_code == 302
    client.get("/login")
    csrf = token(client, "/login")
    monkeypatch.setattr(authapp, "firebase_phone_ready", lambda: True)
    monkeypatch.setattr(authapp, "firebase_public_config", lambda: {"apiKey":"test", "authDomain":"test.firebaseapp.com", "projectId":"test", "appId":"test"})
    monkeypatch.setattr(authapp, "verify_firebase_phone_id_token",
        lambda token: ("phone-provider-uid-123", "+919876543210")
        if token == "verified-firebase-id-token-"+"x"*90
        else (_ for _ in ()).throw(ValueError("bad token")))
    rejected = client.post("/auth/phone-session", json={
        "id_token":"invalid-"+"x"*90,
        "uid":"phone-provider-uid-123","phone":"+919876543210",
        "role":"caregiver"
    }, headers={"X-CSRF-Token":csrf})
    assert rejected.status_code == 401
    ok = client.post("/auth/phone-session", json={
        "id_token":"verified-firebase-id-token-"+"x"*90,
        "uid":"spoofed-uid","role":"caregiver"
    }, headers={"X-CSRF-Token":csrf})
    assert ok.status_code == 200 and ok.json["next_url"] == "/auth/complete"
    from app import ExternalIdentity, PendingIdentity
    with app.app_context():
        assert User.query.count() == 0
        assert ExternalIdentity.query.count() == 0
        assert PendingIdentity.query.count() == 1
    # Must still choose patient or caregiver; no role can be forced in token JSON.
    page = client.get("/auth/complete")
    assert b"auth-onboard" in page.data and b"phone number" in page.data
    created = client.post("/auth/complete", data={
        "csrf_token":csrf, "name":"Helper Sana", "role":"caregiver"
    }, follow_redirects=True)
    assert created.status_code == 200
    assert b"caregiver-v2" in created.data
    with app.app_context():
        user = User.query.one()
        assert user.role == "caregiver"
        assert user.email.endswith("@internal.mindcare.invalid")
        identity = ExternalIdentity.query.one()
        assert identity.subject == "phone-provider-uid-123"
        assert identity.label == "+919876543210"
        assert identity.user_id == user.id
        assert PendingIdentity.query.count() == 0
    logout(client)
    again = client.post("/auth/phone-session", json={
        "id_token":"verified-firebase-id-token-"+"x"*90
    }, headers={"X-CSRF-Token":token(client,"/login")})
    assert again.status_code == 200
    assert again.json["next_url"] == "/dashboard"
    with app.app_context():
        assert User.query.count() == 1


def test_google_verified_profile_uses_subject_and_does_not_autolink_email(client,monkeypatch):
    import app as authapp
    from types import SimpleNamespace
    register(client, "Patient Sana", "google-safe@example.org", "patient")
    with app.app_context():
        old_id = User.query.one().id
    logout(client)
    monkeypatch.setattr(authapp,"GOOGLE_OAUTH_READY",True)
    class FakeGoogle:
        def __init__(self, data):
            self.data=data
        def authorize_access_token(self):
            return {"userinfo":self.data}
    google = FakeGoogle({
        "sub":"google-sub-verified-1",
        "email":"google-safe@example.org",
        "email_verified": True,"name":"Sana"
    })
    monkeypatch.setattr(authapp.oauth,"google",google,raising=False)
    callback=client.get("/auth/google/callback")
    assert callback.status_code == 302 and callback.location.endswith("/login")
    with app.app_context():
        from app import ExternalIdentity
        assert ExternalIdentity.query.count() == 0
        assert User.query.count() == 1 and User.query.one().id == old_id
    login(client,"google-safe@example.org")
    # Authorized user initiated a Google-link flow; OAuth state is verified by Authlib.
    with client.session_transaction() as sess:
        sess["google_link_user"] = old_id
    linked=client.get("/auth/google/callback")
    assert linked.status_code == 302 and linked.location.endswith("/account/security")
    with app.app_context():
        from app import ExternalIdentity
        identity=ExternalIdentity.query.one()
        assert identity.user_id == old_id and identity.subject == "google-sub-verified-1"
    logout(client)
    logged_in=client.get("/auth/google/callback")
    assert logged_in.status_code == 302 and logged_in.location.endswith("/dashboard")
    with app.app_context():
        assert User.query.count() == 1
    logout(client)
    google.data={"sub":"google-sub-verified-other","email":"new-google@example.org",
                 "email_verified":False,"name":"Not Verified"}
    assert client.get("/auth/google/callback").location.endswith("/login")
    with app.app_context():
        assert User.query.count() == 1


def test_account_link_and_new_google_role_selection_never_override_existing_user(client,monkeypatch):
    import app as authapp
    from app import ExternalIdentity
    from types import SimpleNamespace
    monkeypatch.setattr(authapp,"GOOGLE_OAUTH_READY",True)
    google = SimpleNamespace(authorize_access_token=lambda:{"userinfo":{
        "sub":"brand-new-google-stable-subject",
        "email":"new-oauth@example.org",
        "email_verified":True,"name":"Patient Leela"}})
    monkeypatch.setattr(authapp.oauth,"google",google,raising=False)
    started=client.get("/auth/google/callback")
    assert started.location.endswith("/auth/complete")
    setup=client.get("/auth/complete")
    assert b"Patient Leela" in setup.data
    invalid=client.post("/auth/complete",data={
        "csrf_token":token(client,"/auth/complete"),
        "name":"S","role":"admin"
    })
    assert invalid.status_code == 200
    created=client.post("/auth/complete",data={
        "csrf_token":token(client,"/auth/complete"),
        "name":"Patient Leela","role":"patient"
    },follow_redirects=True)
    assert created.status_code==200
    assert b"patient-mode-shortcut" in created.data
    with app.app_context():
        assert ExternalIdentity.query.one().provider=="google"
        assert User.query.one().invite_code
    logout(client)
    assert client.get("/auth/complete").location.endswith("/login")


# Milo is an optional, nonmedical visual guide only, not a backend agent.
@pytest.mark.parametrize("path", ["/dashboard","/games","/reminders","/family","/help","/settings"])
def test_milo_is_available_only_on_patient_pages_without_changing_care_data(client, path):
    register(client, "Patient Milo", "milo-patient@example.org", "patient")
    response = client.get(path)
    assert response.status_code == 200
    assert b'id="milo-roamer"' in response.data
    assert b'id="milo-character"' in response.data
    assert b'id="milo-nav-toggle"' in response.data
    assert b'id="milo-panel"' in response.data
    assert b'milo.js' in response.data
    assert b"milo-motion-toggle" in response.data
    assert b"milo-hide" in response.data
    assert b"need_help" not in response.data or b"quick_support" in response.data or path != "/dashboard"
    assert client.get("/static/milo.js").status_code == 200
    assert client.get("/static/styles.css").status_code == 200
    with app.app_context():
        assert WellbeingCheck.query.count() == 0
    logout(client)
    register(client, "Caregiver Maya", "milo-caregiver@example.org", "caregiver")
    assert b'id="milo-roamer"' not in client.get("/dashboard").data
    assert b'milo.js' not in client.get("/dashboard").data
    logout(client)


@pytest.mark.parametrize("lang,translated",[
    ("en", "Hi, I&#39;m Milo!"), ("hi","नमस्ते, मैं मिलो हूँ!"),
    ("kn","ನಮಸ್ಕಾರ, ನಾನು ಮಿಲೋ!")
])
def test_milo_patient_guidance_uses_patient_language(client,lang,translated):
    register(client, "Patient Milo",f"milo-{lang}@example.org","patient")
    response = client.post("/settings",data={
        "csrf_token":token(client,"/settings"),"language":lang,
    },follow_redirects=True)
    assert response.status_code == 200
    html = client.get("/dashboard").get_data(as_text=True)
    assert translated in html
    assert 'data-milo-language="'+lang+'"' in html


def test_public_landing_world_has_original_art_accessible_sections_and_real_entry_links(client):
    response = client.get("/")
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "mc-world-hero" in html
    assert "mc-world-nav" in html
    assert "MINDCARE" in html
    assert "landing-world.css" in html and "landing-world.js" in html
    assert "mindcare-world.svg" in html
    for anchor in ('id="overview"', 'id="capabilities"', 'id="discover"', 'id="access"'):
        assert anchor in html
    for selector in ('role="tablist"', 'role="tabpanel"', 'data-mc-slide="0"',
                     'data-mc-slide="1"', 'mc-gallery-row-offset', 'mc-world-footer'):
        assert selector in html
    assert html.count('class="mc-gallery-card ') == 6
    assert 'href="/register"' in html
    assert 'href="/login"' in html
    assert 'screen images simulated' not in html.lower()
    assert "simulated" in html.lower()
    assert "non-diagnostic" in html.lower()
    # Public landing supplies its own header, sticky nav and footer, with no duplicate.
    assert 'class="site-header"' not in html
    assert 'class="site-footer"' not in html
    assert 'id="milo-roamer"' not in html
    assert client.get("/static/mindcare-world.svg").status_code == 200
    assert client.get("/static/landing-world.css").status_code == 200
    assert client.get("/static/landing-world.js").status_code == 200


def test_dark_landing_does_not_replace_private_patient_caregiver_or_auth_ui(client):
    register(client, "Patient Tia", "world-patient@example.org", "patient")
    patient = client.get("/dashboard")
    assert patient.status_code == 200
    assert b"patient-mode-shortcut" in patient.data
    assert b'id="milo-roamer"' in patient.data
    assert b'data-quick-support-button' in patient.data
    assert b'landing-world.js' not in patient.data
    assert b'class="site-header"' in patient.data
    assert client.get("/").location.endswith("/dashboard")
    logout(client)
    login_form = client.get("/login")
    assert login_form.status_code == 200
    assert b"auth-v2" in login_form.data
    assert b'class="site-header"' in login_form.data
    logout_response = client.get("/")
    assert logout_response.status_code == 200
    register(client, "Caregiver Ritu", "world-caregiver@example.org", "caregiver")
    caregiver = client.get("/dashboard")
    assert caregiver.status_code == 200
    assert b"caregiver-v2" in caregiver.data
    assert b"landing-world.css" not in caregiver.data
    assert b'id="milo-roamer"' not in caregiver.data


@pytest.mark.parametrize("role,main_marker",[
    ("patient",'class="welcome-banner"'),
    ("caregiver",'class="caregiver-v2"')
])
def test_real_logged_in_application_receives_new_visual_design_without_changing_roles(client,role,main_marker):
    register(client,f"World {role}",f"world-{role}@example.org",role)
    response=client.get("/dashboard")
    assert response.status_code == 200
    html=response.get_data(as_text=True)
    assert "mc-app-shell" in html
    assert "app-world.css" in html
    assert "mindcare-world.svg" in html
    assert 'class="mc-app-breadcrumb"' in html
    assert main_marker in html
    assert 'class="site-header"' in html
    assert 'class="site-footer"' in html
    assert "auth-world.css" not in html
    assert "landing-world.css" not in html
    if role == "patient":
        assert 'data-quick-support-button' in html
        assert 'id="milo-roamer"' in html
        for path in ("/games","/reminders","/family","/help","/settings"):
            page=client.get(path)
            assert page.status_code == 200 and b"app-world.css" in page.data
    else:
        assert 'id="milo-roamer"' not in html
        assert "Support check-ins" in html
    logout(client)


def test_public_and_auth_designs_coexist_without_leaking_private_navigation(client):
    home=client.get("/")
    assert home.status_code == 200 and b"landing-world.css" in home.data
    assert b"app-world.css" not in home.data
    for route in ("/login","/register"):
        response=client.get(route)
        assert response.status_code == 200
        assert b"auth-world.css" in response.data
        assert b"app-world.css" not in response.data
        assert b"mc-app-breadcrumb" not in response.data
    assert client.get("/static/app-world.css").status_code == 200
    assert client.get("/static/auth-world.css").status_code == 200


def test_patient_simple_view_preserves_support_emergency_and_dark_ui(client):
    register(client, "World Patient", "world-simple@example.org", "patient")
    csrf = token(client,"/dashboard")
    toggled=client.post("/patient/view-mode",data={
        "csrf_token":csrf,"simplified":"1"
    },follow_redirects=True)
    assert toggled.status_code == 200
    assert b'simple-dashboard' in toggled.data
    assert b'mc-app-hero-art' in toggled.data
    assert b'app-world.css' in toggled.data
    assert b'data-quick-support-button' in toggled.data
    assert b'href="tel:112"' in toggled.data


# v1.0.0 security hardening: safe, disposable SQLite auth-throttle regressions.
def test_failed_login_is_rate_limited_with_retry_after_and_no_plain_identifiers(client):
    from app import AuthAttempt, LOGIN_LIMIT_PER_IP_ACCOUNT
    register(client,"Patient Security","security-login@example.org","patient")
    logout(client)
    for _ in range(LOGIN_LIMIT_PER_IP_ACCOUNT):
        response = client.post("/login",data={
            "csrf_token":token(client,"/login"),
            "email":"security-login@example.org","password":"incorrect password"
        })
        assert response.status_code == 200
        assert b"Email or password was not recognised." in response.data
    limited = client.post("/login",data={
        "csrf_token":token(client,"/login"),
        "email":"security-login@example.org","password":"incorrect password"
    })
    assert limited.status_code == 429
    assert 1 <= int(limited.headers["Retry-After"]) <= 900
    assert "no-store" in limited.headers.get("Cache-Control","")
    with app.app_context():
        rows = AuthAttempt.query.all()
        # 3 failed-login buckets + 1 signup-request bucket from setup.
        assert len(rows) == 4
        assert all(len(row.bucket_hash) == 64 for row in rows)
        assert all("@" not in row.bucket_hash and "." not in row.bucket_hash for row in rows)


def test_login_limit_is_shared_per_account_and_wrong_client_cannot_reset_it(client):
    from app import AuthAttempt, LOGIN_LIMIT_PER_ACCOUNT
    register(client,"Patient Security","security-shared@example.org","patient")
    logout(client)
    for index in range(LOGIN_LIMIT_PER_ACCOUNT):
        ip = f"198.51.100.{index+1}"
        response = client.post("/login",environ_overrides={"REMOTE_ADDR":ip},
            data={"csrf_token":token(client,"/login"),
                  "email":"security-shared@example.org","password":"wrong"})
        assert response.status_code == 200
    response = client.post("/login",environ_overrides={"REMOTE_ADDR":"203.0.113.30"},
        data={"csrf_token":token(client,"/login"),
              "email":"security-shared@example.org","password":"wrong"})
    assert response.status_code == 429
    # A forgotten-password/provider setup can be a future account-recovery
    # escape hatch. Never permanently lock the user or modify their password.
    with app.app_context():
        assert AuthAttempt.query.count() > 0
        assert User.query.filter_by(email="security-shared@example.org").one().password_hash


def test_valid_login_after_wrong_attempt_restores_session_and_does_not_erase_ip_limit(client):
    from app import AuthAttempt, _login_buckets
    register(client,"Patient Security","security-good@example.org","patient")
    logout(client)
    csrf=token(client,"/login")
    bad=client.post("/login",data={"csrf_token":csrf,"email":"security-good@example.org",
                                   "password":"invalid"})
    assert bad.status_code == 200
    with app.test_request_context("/login",environ_overrides={"REMOTE_ADDR":"127.0.0.1"}):
        buckets=_login_buckets("security-good@example.org")
    good=client.post("/login",data={"csrf_token":csrf,"email":"security-good@example.org",
                                    "password":"very-long-demo-password"},follow_redirects=True)
    assert good.status_code == 200
    assert b"Hello, Patient" in good.data
    with app.app_context():
        assert db.session.get(AuthAttempt,buckets[0][0]) is None
        assert db.session.get(AuthAttempt,buckets[2][0]) is None
        assert db.session.get(AuthAttempt,buckets[1][0]).attempts >= 1


def test_registration_throttle_expires_and_does_not_create_users(client):
    from app import AuthAttempt, REGISTER_LIMIT_PER_IP, REGISTER_WINDOW_SECONDS
    for _ in range(REGISTER_LIMIT_PER_IP):
        response=client.post("/register",data={
            "csrf_token":token(client,"/register"),
            "name":"X","email":"invalid","password":"none","role":"patient"})
        assert response.status_code == 200
    limited=client.post("/register",data={
        "csrf_token":token(client,"/register"),"name":"Valid User",
        "email":"security-signup@example.org","password":"very-long-demo-password",
        "role":"patient"})
    assert limited.status_code == 429
    with app.app_context():
        assert User.query.count() == 0
        for row in AuthAttempt.query.all():
            row.last_failure_epoch -= REGISTER_WINDOW_SECONDS + 5
        db.session.commit()
    success=register(client,"Valid User","security-signup@example.org","patient")
    assert success.status_code == 200
    with app.app_context():
        assert User.query.filter_by(email="security-signup@example.org").count() == 1


def test_local_ignored_spoofed_forwarded_ip_and_https_cache_headers(client):
    from app import AuthAttempt, _auth_bucket
    client.post("/login",headers={"X-Forwarded-For":"192.0.2.66"},
        data={"csrf_token":token(client,"/login"),
              "email":"missing@example.org","password":"wrong"})
    with app.app_context():
        assert db.session.get(AuthAttempt,_auth_bucket("login-ip","127.0.0.1")) is not None
        assert db.session.get(AuthAttempt,_auth_bucket("login-ip","192.0.2.66")) is None
    normal=client.get("/login")
    assert normal.headers["Cache-Control"] == "no-store"
    secure=client.get("/login",base_url="https://mindcare.example")
    assert secure.headers["Strict-Transport-Security"] == "max-age=15552000"
    assert "Strict-Transport-Security" not in normal.headers


# Auth recovery: synthetic accounts and mocked transport (never send real mail).
def test_recovery_request_is_generic_and_does_not_enumerate_accounts(client, monkeypatch):
    import app as mindcare
    monkeypatch.setattr(mindcare, "_recovery_mail_ready", lambda: True)
    sent = []
    monkeypatch.setattr(mindcare, "_send_recovery_mail",
                        lambda email, code: sent.append((email, code)) or True)
    register(client, "Recovery Patient", "recover-test@example.org", "patient")
    logout(client)
    def request_reset(email):
        return client.post("/forgot-password", data={
            "csrf_token": token(client, "/forgot-password"), "email": email
        }, follow_redirects=True)
    missing = request_reset("missing-test@example.org")
    real = request_reset("recover-test@example.org")
    assert missing.status_code == real.status_code == 200
    assert b"If this address belongs to an email/password account" in real.data
    assert b"If this address belongs to an email/password account" in missing.data
    assert len(sent) == 1 and sent[0][0] == "recover-test@example.org"
    assert len(sent[0][1]) == 43
    with app.app_context():
        assert mindcare.PasswordRecovery.query.count() == 1
        assert sent[0][1] not in mindcare.PasswordRecovery.query.first().code_hash


def test_recovery_reset_is_single_use_and_revokes_existing_sessions(client, monkeypatch):
    import app as mindcare
    monkeypatch.setattr(mindcare, "_recovery_mail_ready", lambda: True)
    sent = []
    monkeypatch.setattr(mindcare, "_send_recovery_mail",
                        lambda email, code: sent.append(code) or True)
    register(client, "Recovery Patient", "recover-session@example.org", "patient")
    # Existing session is authenticated before recovery.
    other_session = app.test_client()
    existing = login(other_session, "recover-session@example.org")
    assert existing.status_code == 200
    logout(client)
    client.post("/forgot-password", data={
        "csrf_token": token(client, "/forgot-password"),
        "email": "recover-session@example.org",
    })
    code = sent[0]
    assert client.post("/reset-password", data={
        "csrf_token": token(client, "/reset-password"),
        "email": "recover-session@example.org",
        "code": code, "password": "new-unique-recovery-password"
    }, follow_redirects=True).status_code == 200
    # Old credential cannot authenticate and previously issued session is invalid.
    assert other_session.get("/dashboard").status_code == 302
    assert b"Email or password was not recognised." in login(client, "recover-session@example.org").data
    # A replay must fail without changing the new password.
    replay = client.post("/reset-password", data={
        "csrf_token": token(client, "/reset-password"),
        "email": "recover-session@example.org",
        "code": code, "password": "replay-password-should-not-work"
    }, follow_redirects=True)
    assert b"Invalid or expired recovery details" in replay.data
    valid = client.post("/login", data={
        "csrf_token": token(client, "/login"),
        "email": "recover-session@example.org",
        "password": "new-unique-recovery-password"
    }, follow_redirects=True)
    assert valid.status_code == 200 and b"Hello, Recovery" in valid.data


def test_recovery_expired_codes_are_rejected(client, monkeypatch):
    import app as mindcare
    from datetime import timedelta
    monkeypatch.setattr(mindcare, "_recovery_mail_ready", lambda: True)
    sent = []
    monkeypatch.setattr(mindcare, "_send_recovery_mail",
                        lambda email, code: sent.append(code) or True)
    register(client, "Recovery Expired", "recovery-expired@example.org", "patient")
    logout(client)
    client.post("/forgot-password", data={
        "csrf_token": token(client, "/forgot-password"),
        "email": "recovery-expired@example.org"
    })
    with app.app_context():
        row = mindcare.PasswordRecovery.query.one()
        row.expires_at = mindcare.now_utc() - timedelta(seconds=5)
        db.session.commit()
    response = client.post("/reset-password", data={
        "csrf_token": token(client, "/reset-password"),
        "email": "recovery-expired@example.org",
        "code": sent[0], "password": "new-secure-password-123"
    }, follow_redirects=True)
    assert b"Invalid or expired recovery details" in response.data
    assert login(client, "recovery-expired@example.org").status_code == 200


def test_recovery_is_unavailable_without_mail_configuration(client, monkeypatch):
    import app as mindcare
    monkeypatch.setattr(mindcare, "_recovery_mail_ready", lambda: False)
    register(client, "Recovery Off", "recovery-off@example.org", "patient")
    logout(client)
    response = client.post("/forgot-password", data={
        "csrf_token": token(client, "/forgot-password"),
        "email": "recovery-off@example.org"
    }, follow_redirects=True)
    assert response.status_code == 200
    with app.app_context():
        assert mindcare.PasswordRecovery.query.count() == 0
