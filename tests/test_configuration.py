import pytest
from cryptography.fernet import Fernet

from app import create_app
from database import db


def configured_app(tmp_path, **overrides):
    values = {
        "TESTING": True,
        "SECRET_KEY": "test-session-key-with-more-than-32-characters",
        "ENCRYPTION_KEY": Fernet.generate_key().decode(),
        "SQLALCHEMY_DATABASE_URI": f"sqlite:///{tmp_path / 'config.db'}",
        "RATELIMIT_ENABLED": False,
        "PRODUCTION": False,
        "TRUST_PROXY": False,
        "TRUSTED_HOSTS": None,
    }
    values.update(overrides)
    return create_app(values)


@pytest.mark.parametrize("key", ["", None, "private-invalid-test-key", "neplatný-kľúč"])
def test_invalid_encryption_key_identifies_setting_without_disclosing_value(tmp_path, key):
    with pytest.raises(RuntimeError, match="ENCRYPTION_KEY") as error:
        configured_app(tmp_path, ENCRYPTION_KEY=key)
    assert "kľúč nemeňte" in str(error.value)
    if key:
        assert key not in str(error.value)
    assert error.value.__suppress_context__


def test_valid_production_settings_serve_https_login_and_database_health(tmp_path):
    app = configured_app(
        tmp_path,
        PRODUCTION=True,
        BASE_URL="https://portal.example.org",
        TRUSTED_HOSTS=["portal.example.org"],
        SESSION_COOKIE_SECURE=True,
        CONTROLLER_NAME="Testovací prevádzkovateľ",
        CONTROLLER_ADDRESS="Testovacia 1, Bratislava",
        PRIVACY_EMAIL="privacy@example.org",
    )
    with app.app_context():
        db.create_all()
    client = app.test_client()
    response = client.get("/login", base_url="https://portal.example.org")
    assert response.status_code == 200
    assert response.headers["Strict-Transport-Security"] == "max-age=31536000"
    assert client.get("/healthz", base_url="https://portal.example.org").json == {"status": "ok"}
    with app.app_context():
        db.session.remove()
        db.drop_all()
