import hashlib
import json
from functools import wraps

from cryptography.fernet import Fernet
from flask import abort, current_app, g, redirect, session, url_for


def encrypt(value):
    raw = json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    return Fernet(current_app.config["ENCRYPTION_KEY"].encode()).encrypt(raw.encode()).decode()


def decrypt(value):
    if not value:
        return None
    raw = Fernet(current_app.config["ENCRYPTION_KEY"].encode()).decrypt(value.encode())
    return json.loads(raw)


def token_digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not g.get("agent"):
            return redirect(url_for("login"))
        return view(*args, **kwargs)
    return wrapped


def owned_inquiry(inquiry_id):
    from database import Inquiry, db
    inquiry = db.session.get(Inquiry, inquiry_id)
    if not inquiry or inquiry.agent_id != g.agent.id:
        abort(404)
    return inquiry


def establish_session(agent):
    session.clear()
    session["agent_id"] = agent.id
    session["session_version"] = agent.session_version
    session.permanent = True
