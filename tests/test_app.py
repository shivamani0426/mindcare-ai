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
