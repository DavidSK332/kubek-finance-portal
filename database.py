"""No plaintext client data; public links contain no client identifiers."""
import secrets
from datetime import datetime, timezone

from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import event
from sqlalchemy.engine import Engine
from werkzeug.security import generate_password_hash

from security import decrypt, encrypt, token_digest

db = SQLAlchemy()


def utcnow():
    # UTC naive values work consistently with SQLite and PostgreSQL DateTime.
    return datetime.now(timezone.utc).replace(tzinfo=None)


@event.listens_for(Engine, "connect")
def sqlite_constraints(connection, _record):
    if connection.__class__.__module__.startswith("sqlite3"):
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA busy_timeout=5000")
        connection.execute("PRAGMA journal_mode=WAL")


class Agent(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(254), unique=True, nullable=False)
    name = db.Column(db.String(160), nullable=False)
    password_hash = db.Column(db.Text, nullable=False)
    invite_digest = db.Column(db.String(64), unique=True, nullable=False)
    invite_encrypted = db.Column(db.Text, nullable=False)
    active = db.Column(db.Boolean, nullable=False, default=True)
    session_version = db.Column(db.Integer, nullable=False, default=1)
    failed_logins = db.Column(db.Integer, nullable=False, default=0)
    locked_until = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)

    @property
    def invite_token(self):
        return decrypt(self.invite_encrypted)["token"]

    def rotate_link(self):
        token = secrets.token_urlsafe(32)
        self.invite_digest = token_digest(token)
        self.invite_encrypted = encrypt({"token": token})

    @classmethod
    def create(cls, email, name, password):
        agent = cls(email=email.lower(), name=name,
                    password_hash=generate_password_hash(password, method="scrypt"))
        agent.rotate_link()
        return agent


class Inquiry(db.Model):
    id = db.Column(db.String(32), primary_key=True, default=lambda: secrets.token_hex(16))
    agent_id = db.Column(db.Integer, db.ForeignKey("agent.id"), nullable=False, index=True)
    submission_key = db.Column(db.String(64), nullable=False, unique=True)
    data_encrypted = db.Column(db.Text, nullable=False)
    analysis_encrypted = db.Column(db.Text)
    ai_status = db.Column(db.String(24), nullable=False, default="pending")
    status = db.Column(db.String(24), nullable=False, default="new", index=True)
    proposal_encrypted = db.Column(db.Text)
    proposal_revision = db.Column(db.Integer, nullable=False, default=0)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow, index=True)
    agent = db.relationship(Agent)

    @property
    def data(self):
        return decrypt(self.data_encrypted)

    @property
    def analysis(self):
        return decrypt(self.analysis_encrypted)

    @property
    def proposal(self):
        return decrypt(self.proposal_encrypted)


class Summary(db.Model):
    id = db.Column(db.String(32), primary_key=True, default=lambda: secrets.token_hex(16))
    inquiry_id = db.Column(db.String(32), db.ForeignKey("inquiry.id", ondelete="CASCADE"), nullable=False, index=True)
    revision = db.Column(db.Integer, nullable=False)
    snapshot_encrypted = db.Column(db.Text, nullable=False)
    delivery_status = db.Column(db.String(24), nullable=False, default="pending")
    provider_reference = db.Column(db.String(200))
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    sent_at = db.Column(db.DateTime)
    __table_args__ = (db.UniqueConstraint("inquiry_id", "revision"),)

    @property
    def snapshot(self):
        return decrypt(self.snapshot_encrypted)


class Job(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    inquiry_id = db.Column(db.String(32), db.ForeignKey("inquiry.id", ondelete="CASCADE"), nullable=False, index=True)
    summary_id = db.Column(db.String(32), db.ForeignKey("summary.id", ondelete="CASCADE"))
    kind = db.Column(db.String(30), nullable=False)
    dedupe_key = db.Column(db.String(150), nullable=False, unique=True)
    status = db.Column(db.String(24), nullable=False, default="pending", index=True)
    attempts = db.Column(db.Integer, nullable=False, default=0)
    available_at = db.Column(db.DateTime, nullable=False, default=utcnow, index=True)
    lease_until = db.Column(db.DateTime)
    lease_token = db.Column(db.String(64))
    last_error = db.Column(db.String(120))
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)


class AuditEvent(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    agent_id = db.Column(db.Integer, db.ForeignKey("agent.id"), nullable=False)
    inquiry_id = db.Column(db.String(32), db.ForeignKey("inquiry.id", ondelete="CASCADE"), index=True)
    action = db.Column(db.String(80), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)


def audit(agent_id, action, inquiry_id=None):
    db.session.add(AuditEvent(agent_id=agent_id, action=action, inquiry_id=inquiry_id))


def enqueue(inquiry_id, kind, key, summary_id=None):
    job = Job(inquiry_id=inquiry_id, kind=kind, dedupe_key=key, summary_id=summary_id)
    db.session.add(job)
    return job
