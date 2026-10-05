import hashlib
import re

import pytest

import app as app_module
from database import Cycle, User, db


@pytest.fixture
def client():
    flask_app = app_module.create_app({"TESTING": True, "WTF_CSRF_ENABLED": False,
                                       "ADMIN_EMAIL": "admin@test.local",
                                       "ADMIN_PASSWORD": "admin-test-pass"})
    with flask_app.app_context():
        db.drop_all()
        db.create_all()
    with flask_app.test_client() as c:
        yield c


def _captcha(client):
    """Load the register page and return the captcha word the server expects."""
    client.get("/register")
    with client.session_transaction() as sess:
        return sess["captcha_word"]


def _register(client, email="user@test.local", password="secret123", captcha=None):
    word = captcha or _captcha(client)
    return client.post("/register", data={
        "name": "Test User", "email": email, "mobile": "9999999999", "gender": "Female",
        "password": password, "confirm_password": password,
        "captcha": word, "agree": "on",
    })


def test_dashboard_requires_login(client):
    response = client.get("/dashboard")
    assert response.status_code == 302
    assert "/login" in response.headers["Location"]


def test_register_then_login_flow(client):
    response = _register(client)
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/dashboard")

    client.get("/logout")
    response = client.post("/login", data={"login_input": "user@test.local", "password": "secret123"})
    assert response.headers["Location"].endswith("/dashboard")


def test_register_rejects_wrong_captcha(client):
    response = _register(client, captcha="not-the-word")
    assert response.status_code == 200  # re-rendered form, not a redirect
    assert b"Incorrect captcha" in response.data


def test_legacy_password_hash_logs_in_and_is_upgraded(client):
    with client.application.app_context():
        legacy = User(name="Old", email="old@test.local", mobile="9999999999", gender="Female",
                      password=hashlib.sha256(b"oldpass1").hexdigest())
        db.session.add(legacy)
        db.session.commit()

    response = client.post("/login", data={"login_input": "old@test.local", "password": "oldpass1"})
    assert response.headers["Location"].endswith("/dashboard")

    with client.application.app_context():
        stored = db.session.query(User).filter_by(email="old@test.local").one().password
        assert stored.startswith("scrypt:") or stored.startswith("pbkdf2:")


def test_admin_login_with_configured_credentials(client):
    response = client.post("/login", data={"login_input": "admin@test.local", "password": "admin-test-pass"})
    assert response.headers["Location"].endswith("/admin")
    assert client.get("/admin").status_code == 200


def test_admin_login_wrong_password_is_rejected(client):
    client.post("/login", data={"login_input": "admin@test.local", "password": "bad"})
    assert client.get("/admin").status_code == 302  # still redirected to login


def test_admin_login_disabled_when_not_configured():
    flask_app = app_module.create_app({"TESTING": True, "ADMIN_EMAIL": None, "ADMIN_PASSWORD": None})
    with flask_app.test_client() as c:
        c.post("/login", data={"login_input": "admin@cyclewise.com", "password": "Admin@2025"})
        assert c.get("/admin").status_code == 302


def test_calendar_adds_a_cycle_and_rejects_end_before_start(client):
    _register(client)
    client.post("/calendar", data={"start_date": "2026-02-01", "end_date": "2026-02-05"})
    client.post("/calendar", data={"start_date": "2026-03-01", "end_date": "2026-02-20"})  # invalid
    with client.application.app_context():
        cycles = Cycle.query.all()
        assert len(cycles) == 1
        assert str(cycles[0].start_date) == "2026-02-01"


def test_chat_send_returns_a_reply(client):
    _register(client)
    response = client.post("/chat/send", json={"messages": [
        {"role": "user", "content": "my periods are painful"}]})
    assert response.status_code == 200
    body = response.get_json()
    assert "reply" in body and body["severity"] == "mild"


def test_report_download_is_a_pdf(client):
    _register(client)
    response = client.post("/report", data={"start_date": "", "end_date": ""})
    assert response.status_code == 200
    assert response.mimetype == "application/pdf"
    assert response.data.startswith(b"%PDF")


def test_hospitals_filter_by_city_and_type(client):
    _register(client)
    response = client.get("/hospitals?city=Pune&type=Government")
    assert response.status_code == 200
    assert b"Sassoon General Hospital" in response.data
    assert b"Ruby Hall Clinic" not in response.data  # private, filtered out


def test_every_logged_in_page_renders(client):
    _register(client)
    client.post("/calendar", data={"start_date": "2026-02-01", "end_date": "2026-02-05"})
    client.post("/notes", data={"date": "2026-02-02", "content": "Felt tired", "mood_tag": "tired"})
    for path in ["/dashboard", "/calendar", "/notes", "/chat", "/report", "/hospitals"]:
        response = client.get(path)
        assert response.status_code == 200, path
