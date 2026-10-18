import copy

import pytest
from cryptography.fernet import Fernet

from app import create_app
from database import Agent, Inquiry, db
from schemas import ClientData
from security import encrypt


@pytest.fixture
def sample_data():
    return ClientData.model_validate({
        "first_name": "Mária", "last_name": "Ukážková", "email": "klient@example.org",
        "phone": "+421 900 000 000", "age": 34, "children": 1, "adults": 2,
        "income_employment": "3000", "income_business": "0", "income_company": "0", "income_other": "0",
        "expenses": "1200", "savings": "6000", "requested_loan": "90000", "requested_years": 25,
        "monthly_investment": "100", "goals": ["refinance", "life"],
        "notes": "Fiktívna ukážka. Toto NIE SÚ údaje skutočného klienta.",
        "privacy_acknowledged": True, "ai_consent": False,
        "debts": [{"id": "debt-1", "kind": "mortgage", "lender": "Pôvodná banka", "balance": "85000",
                   "payment": "480", "rate": "4.9", "limit": "0"},
                  {"id": "debt-2", "kind": "consumer", "lender": "Iný poskytovateľ", "balance": "5000",
                   "payment": "150", "rate": "9", "limit": "0"}],
    }).model_dump(mode="json")


@pytest.fixture
def proposal_data():
    return {"lender": "Modelová banka - fiktívna ponuka", "kind": "refinance", "principal": "90000",
            "annual_rate": "3.6", "years": 25, "upfront_fees": "300", "monthly_costs": "20",
            "replace_ids": ["debt-1", "debt-2"], "living_minimum": None, "assessed_payments": None,
            "client_summary": "Navrhujeme zlúčiť uvedené dva úvery do jedného modelového riešenia. "
                              "Pred podaním žiadosti preveríme náklady, registre a podmienky banky.",
            "documents": ["Potvrdenie o čistom príjme podľa banky.",
                          "Vyčíslenia zostatkov a predčasného splatenia oboch úverov.",
                          "Podklady k nehnuteľnosti podľa požiadaviek banky."]}


@pytest.fixture
def app(tmp_path):
    application = create_app({
        "TESTING": True, "WTF_CSRF_ENABLED": False, "RATELIMIT_ENABLED": False,
        "SECRET_KEY": "test-session-key-with-more-than-32-characters",
        "ENCRYPTION_KEY": Fernet.generate_key().decode(),
        "SQLALCHEMY_DATABASE_URI": f"sqlite:///{tmp_path / 'portal.db'}",
        "PRODUCTION": False, "TRUSTED_HOSTS": None, "SESSION_COOKIE_SECURE": False,
        "OPENAI_API_KEY": "", "EMAIL_BACKEND": "disabled", "TRUST_PROXY": False,
    })
    with application.app_context():
        db.create_all()
        for email, name in (("agent1@example.org", "Agent Jeden"), ("agent2@example.org", "Agent Dva")):
            db.session.add(Agent.create(email, name, "Secure-test-password-123"))
        db.session.commit()
    yield application
    with application.app_context():
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def inquiry_id(app, sample_data):
    with app.app_context():
        data = copy.deepcopy(sample_data)
        data.update(privacy_version="2026-10-18-v1", submitted_at="2026-10-18T09:30:00Z")
        inquiry = Inquiry(agent_id=1, submission_key="test-submission-unique", data_encrypted=encrypt(data))
        db.session.add(inquiry)
        db.session.commit()
        return inquiry.id


def login(client, agent_id=1):
    return client.post("/login", data={"email": f"agent{agent_id}@example.org", "password": "Secure-test-password-123"})


def proposal_form(proposal_data, revision=0):
    result = {**proposal_data, "documents": "\n".join(proposal_data["documents"]), "revision": str(revision)}
    for key in ("living_minimum", "assessed_payments"):
        result[key] = "" if result[key] is None else str(result[key])
    return result
