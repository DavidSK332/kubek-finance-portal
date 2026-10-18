import re

import pytest

from conftest import login, proposal_form
from database import Agent, Inquiry, Job, Summary, db, enqueue
from security import encrypt


def public_form_data(sample_data, key):
    data = {key: str(value) for key, value in sample_data.items() if key not in ("debts", "goals", "ai_consent", "privacy_acknowledged")}
    data.update(submission_key=key, goals=sample_data["goals"], privacy_acknowledged="1")
    for field in ("kind", "lender", "balance", "payment", "rate", "limit"):
        data["debt_" + field] = [debt[field] for debt in sample_data["debts"]]
    return data


def test_public_form_saves_encrypted_and_double_click_only_once(app, client, sample_data):
    with app.app_context():
        token = db.session.get(Agent, 1).invite_token
    url = f"/formular/{token}"
    page = client.get(url)
    assert page.status_code == 200
    key = re.search(rb'name="submission_key" value="([^"]+)"', page.data).group(1).decode()
    submitted = public_form_data(sample_data, key)
    assert client.post(url, data=submitted).status_code == 302
    assert client.post(url, data=submitted).status_code == 302
    with app.app_context():
        inquiries = db.session.execute(db.select(Inquiry)).scalars().all()
        assert len(inquiries) == 1
        assert inquiries[0].data["first_name"] == "Mária"
        assert "Mária" not in inquiries[0].data_encrypted
        assert "klient@example.org" not in inquiries[0].data_encrypted
        assert db.session.execute(db.select(db.func.count(Job.id))).scalar() == 1


def test_missing_required_data_preserves_form_and_saves_nothing(app, client, sample_data):
    with app.app_context():
        token = db.session.get(Agent, 1).invite_token
    url = f"/formular/{token}"
    page = client.get(url)
    key = re.search(rb'name="submission_key" value="([^"]+)"', page.data).group(1).decode()
    submitted = public_form_data(sample_data, key)
    submitted["email"] = "not-an-email"
    response = client.post(url, data=submitted)
    assert response.status_code == 422
    assert "Mária" in response.data.decode()
    with app.app_context():
        assert db.session.execute(db.select(db.func.count(Inquiry.id))).scalar() == 0


def test_dashboard_requires_login(client):
    assert client.get("/dashboard").status_code == 302


def test_agents_cannot_access_others_records(client, inquiry_id):
    login(client, 2)
    assert client.get(f"/klienti/{inquiry_id}").status_code == 404
    assert client.get(f"/klienti/{inquiry_id}/report.pdf?internal=1").status_code == 404
    assert client.post(f"/klienti/{inquiry_id}/stav", data={"status": "closed"}).status_code == 404
    assert client.post(f"/klienti/{inquiry_id}/odoslat", data={"reviewed": "1", "revision": 0}).status_code == 404
    assert b"klient@example.org" not in client.get("/dashboard").data


def test_proposal_snapshot_is_immutable_and_double_send_is_deduped(app, client, inquiry_id, proposal_data):
    login(client)
    assert client.post(f"/klienti/{inquiry_id}/navrh", data=proposal_form(proposal_data)).status_code == 302
    assert client.get(f"/klienti/{inquiry_id}").status_code == 200
    assert client.get(f"/klienti/{inquiry_id}/report.pdf").data.startswith(b"%PDF")
    sent = {"revision": 1, "reviewed": "1"}
    assert client.post(f"/klienti/{inquiry_id}/odoslat", data=sent).status_code == 302
    assert client.post(f"/klienti/{inquiry_id}/odoslat", data=sent).status_code == 302
    proposal_data["annual_rate"] = "4.2"
    client.post(f"/klienti/{inquiry_id}/navrh", data=proposal_form(proposal_data, 1))
    with app.app_context():
        summaries = db.session.execute(db.select(Summary)).scalars().all()
        assert len(summaries) == 1
        assert summaries[0].snapshot["proposal"]["annual_rate"] == "3.6"
        assert db.session.get(Inquiry, inquiry_id).proposal["annual_rate"] == "4.2"
        assert db.session.execute(db.select(db.func.count(Job.id))).scalar() == 1


def test_stale_edit_and_stale_send_cannot_overwrite_or_queue(app, client, inquiry_id, proposal_data):
    login(client)
    client.post(f"/klienti/{inquiry_id}/navrh", data=proposal_form(proposal_data))
    stale = proposal_form(proposal_data)
    stale["lender"] = "Stale edit"
    client.post(f"/klienti/{inquiry_id}/navrh", data=stale)
    assert client.post(f"/klienti/{inquiry_id}/odoslat", data={"reviewed": "1", "revision": 0}).status_code == 409
    with app.app_context():
        assert db.session.get(Inquiry, inquiry_id).proposal["lender"] != "Stale edit"
        assert db.session.execute(db.select(db.func.count(Summary.id))).scalar() == 0


def test_search_escapes_html_and_client_notes(app, client, inquiry_id):
    login(client)
    response = client.get("/dashboard?q=<script>alert(1)</script>")
    assert response.status_code == 200
    assert b"<script>alert(1)</script>" not in response.data
    assert response.headers["Cache-Control"] == "no-store"
    assert "frame-ancestors 'none'" in response.headers["Content-Security-Policy"]


def test_actual_csrf_protects_login(app, client):
    app.config["WTF_CSRF_ENABLED"] = True
    assert client.post("/login", data={"email": "agent1@example.org", "password": "Secure-test-password-123"}).status_code == 400
    page = client.get("/login")
    token = re.search(rb'name="csrf_token" value="([^"]+)"', page.data).group(1).decode()
    assert client.post("/login", data={"email": "agent1@example.org", "password": "Secure-test-password-123", "csrf_token": token}).status_code == 302
    assert client.get("/dashboard").status_code == 200


def test_rotating_link_disables_old_url(app, client):
    login(client)
    with app.app_context():
        old = db.session.get(Agent, 1).invite_token
    client.post("/nastavenia/novy-odkaz")
    assert client.get(f"/formular/{old}").status_code == 404


def test_delete_cascades_jobs_and_reports(app, client, inquiry_id, proposal_data):
    login(client)
    client.post(f"/klienti/{inquiry_id}/navrh", data=proposal_form(proposal_data))
    client.post(f"/klienti/{inquiry_id}/odoslat", data={"reviewed": "1", "revision": 1})
    assert client.post(f"/klienti/{inquiry_id}/vymazat", data={"confirm_delete": "1"}).status_code == 302
    with app.app_context():
        assert db.session.get(Inquiry, inquiry_id) is None
        assert db.session.execute(db.select(db.func.count(Job.id))).scalar() == 0
        assert db.session.execute(db.select(db.func.count(Summary.id))).scalar() == 0


def test_failed_logins_lock_account_even_with_correct_password(app, client):
    for _ in range(5):
        client.post("/login", data={"email": "agent1@example.org", "password": "wrong"})
    response = login(client)
    assert response.status_code == 200
    with client.session_transaction() as session:
        assert "agent_id" not in session


def test_explicit_mail_retry_clears_previous_error(app, client, inquiry_id):
    with app.app_context():
        job = enqueue(inquiry_id, "notify_agent", "blocked-mail-retry")
        job.status, job.attempts, job.last_error = "blocked", 1, "MailConfigurationError"
        db.session.commit()
        job_id = job.id
    login(client)
    response = client.post(f"/klienti/{inquiry_id}/ulohy/{job_id}/opakovat", follow_redirects=True)
    assert response.status_code == 200
    assert b"MailConfigurationError" not in response.data
    with app.app_context():
        job = db.session.get(Job, job_id)
        assert job.status == "pending"
        assert job.attempts == 0
        assert job.last_error is None


def test_completed_unavailable_ai_can_retry_with_original_consent_ownership_and_csrf(app, client, inquiry_id):
    with app.app_context():
        inquiry = db.session.get(Inquiry, inquiry_id)
        data = inquiry.data
        data["ai_consent"] = True
        inquiry.data_encrypted = encrypt(data)
        inquiry.ai_status = "unavailable"
        job = enqueue(inquiry_id, "analyze", "unavailable-ai-retry")
        job.status, job.attempts = "done", 1
        db.session.commit()
        job_id = job.id
    endpoint = f"/klienti/{inquiry_id}/ulohy/{job_id}/opakovat"
    other_client = app.test_client()
    login(other_client, 2)
    assert other_client.post(endpoint).status_code == 404
    login(client)
    app.config["WTF_CSRF_ENABLED"] = True
    page = client.get(f"/klienti/{inquiry_id}")
    assert "Zopakovať AI analýzu" in page.get_data(as_text=True)
    assert client.post(endpoint).status_code == 400
    token = re.search(rb'name="csrf_token" value="([^"]+)"', page.data).group(1).decode()
    assert client.post(endpoint, data={"csrf_token": token}).status_code == 302
    with app.app_context():
        inquiry = db.session.get(Inquiry, inquiry_id)
        job = db.session.get(Job, job_id)
        assert inquiry.data["ai_consent"] is True
        assert inquiry.ai_status == "pending"
        assert job.status == "pending"
        assert job.attempts == 0
        assert db.session.execute(db.select(db.func.count(Job.id))).scalar() == 1


@pytest.mark.parametrize("kind,status,consent,ai_status", [
    ("analyze", "done", False, "unavailable"),
    ("notify_agent", "done", True, "unavailable"),
    ("send_summary", "done", True, "unavailable"),
    ("analyze", "done", True, "done"),
    ("analyze", "done", True, "skipped"),
    ("analyze", "running", True, "unavailable"),
    ("analyze", "pending", True, "unavailable"),
])
def test_ai_retry_does_not_requeue_completed_mail_or_bypass_consent_and_state(
        app, client, inquiry_id, kind, status, consent, ai_status):
    with app.app_context():
        inquiry = db.session.get(Inquiry, inquiry_id)
        data = inquiry.data
        data["ai_consent"] = consent
        inquiry.data_encrypted = encrypt(data)
        inquiry.ai_status = ai_status
        job = enqueue(inquiry_id, kind, "not-retryable")
        job.status = status
        db.session.commit()
        job_id = job.id
    login(client)
    page = client.get(f"/klienti/{inquiry_id}")
    assert "Zopakovať AI analýzu" not in page.get_data(as_text=True)
    assert client.post(f"/klienti/{inquiry_id}/ulohy/{job_id}/opakovat").status_code == 400
    with app.app_context():
        assert db.session.get(Job, job_id).status == status
        assert db.session.get(Inquiry, inquiry_id).ai_status == ai_status
