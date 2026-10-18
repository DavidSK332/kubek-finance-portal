import re

from conftest import login, proposal_form
from database import Agent, Inquiry, Job, Summary, db


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
