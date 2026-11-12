"""Run with `pip install -r requirements.txt pytest` then `pytest -q`."""
import os
os.environ["DATABASE_URL"] = "sqlite://"
os.environ["SECRET_KEY"] = "test-secret-only-not-for-production"
os.environ["SECURE_COOKIES"] = "0"

import pytest
from app import app, db, User, CareLink, GameResult, difficulty_for


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
