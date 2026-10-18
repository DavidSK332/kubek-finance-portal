import io
import secrets
from datetime import timedelta, timezone
from functools import partial
from pathlib import Path
from zoneinfo import ZoneInfo

import click
from cryptography.fernet import Fernet
from email_validator import EmailNotValidError, validate_email
from flask import Flask, abort, flash, g, redirect, render_template, request, send_file, session, url_for
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_wtf.csrf import CSRFError, CSRFProtect
from pydantic import ValidationError
from sqlalchemy import delete, update
from sqlalchemy.exc import IntegrityError
from werkzeug.exceptions import SecurityError
from werkzeug.middleware.proxy_fix import ProxyFix
from werkzeug.security import check_password_hash, generate_password_hash

from ai_analysis import fallback_analysis
from config import ROOT, settings
from database import Agent, AuditEvent, Inquiry, Job, Summary, audit, db, enqueue, utcnow
from finance import compare_proposal, document_checklist, financial_profile
from pdf_service import build_report, money, number
from reporting import make_snapshot
from schemas import ClientData, DEBT_TYPES, GOALS, Proposal
from security import encrypt, establish_session, login_required, owned_inquiry, token_digest

csrf = CSRFProtect()
limiter = Limiter(key_func=get_remote_address, default_limits=["300 per hour"])
STATUSES = {"new": "Nový dopyt", "contacted": "Kontaktovaný", "proposal": "Návrh", "closed": "Uzatvorený"}
JOB_LABELS = {"analyze": "Analýza", "notify_agent": "E-mail agentovi", "send_summary": "Sumarizácia klientovi"}
DELIVERY_LABELS = {"pending": "Čaká na spracovanie", "running": "Spracúva sa", "done": "Dokončené",
                   "failed": "Zlyhalo", "blocked": "Chýba konfigurácia e-mailu", "uncertain": "Overiť doručenie u poskytovateľa",
                   "accepted": "Prijaté e-mailovým poskytovateľom"}
AI_LABELS = {"pending": "Čaká na analýzu", "done": "AI analýza hotová", "skipped": "Bez AI podľa voľby klienta",
             "unavailable": "OpenAI nie je nastavené", "failed": "AI nedostupná - pravidlový profil"}


def normalized_money(value, default="0"):
    return (value or default).strip().replace(",", ".")


def form_debts(form):
    fields = ("kind", "lender", "balance", "payment", "rate", "limit")
    lists = {key: form.getlist("debt_" + key) for key in fields}
    count = len(lists["kind"])
    if count > 30 or any(len(values) != count for values in lists.values()):
        raise ValueError("Skontrolujte riadky záväzkov. Povolených je najviac 30.")
    return [{key: lists[key][i] for key in fields} for i in range(count)]


def parse_client(form):
    money_fields = ("income_employment", "income_business", "income_company", "income_other",
                    "expenses", "savings", "requested_loan", "monthly_investment")
    values = {key: form.get(key, "") for key in ("first_name", "last_name", "email", "phone", "age", "children", "adults", "requested_years", "notes")}
    values.update({key: normalized_money(form.get(key)) for key in money_fields})
    values["goals"] = form.getlist("goals")
    values["privacy_acknowledged"] = form.get("privacy_acknowledged") == "1"
    values["ai_consent"] = form.get("ai_consent") == "1"
    values["debts"] = []
    for index, debt in enumerate(form_debts(form)):
        values["debts"].append({**debt, "id": f"debt-{index + 1}",
                                 **{key: normalized_money(debt[key]) for key in ("balance", "payment", "rate", "limit")}})
    return ClientData.model_validate(values).model_dump(mode="json")


def parse_proposal(form):
    values = {key: form.get(key, "") for key in ("lender", "kind", "years", "client_summary")}
    values.update({key: normalized_money(form.get(key)) for key in ("principal", "annual_rate", "upfront_fees", "monthly_costs")})
    values.update({key: normalized_money(form.get(key)) if form.get(key, "").strip() else None
                   for key in ("living_minimum", "assessed_payments")})
    values["replace_ids"] = list(dict.fromkeys(form.getlist("replace_ids")))
    values["documents"] = [line.strip() for line in form.get("documents", "").splitlines() if line.strip()]
    return Proposal.model_validate(values).model_dump(mode="json")


def validation_errors(error):
    if not isinstance(error, ValidationError):
        return [str(error)]
    labels = {"first_name": "Meno", "last_name": "Priezvisko", "phone": "Telefón", "email": "E-mail",
              "age": "Vek", "children": "Počet detí", "adults": "Počet dospelých", "goals": "Ciele",
              "privacy_acknowledged": "Potvrdenie informácií o spracúvaní", "debts": "Záväzky",
              "expenses": "Mesačné výdavky", "client_summary": "Zhrnutie pre klienta", "documents": "Podklady",
              "lender": "Inštitúcia / riešenie", "principal": "Výška úveru", "annual_rate": "Úroková sadzba",
              "living_minimum": "Životné minimum", "assessed_payments": "Posudzované splátky"}
    return [f"{labels.get(str(e['loc'][0]), str(e['loc'][0])) if e['loc'] else 'Formulár'}: "
            f"{e['msg'] if e['type'] == 'value_error' else 'skontrolujte hodnotu, rozsah a formát.'}"
            for e in error.errors(include_url=False, include_input=False)][:12]


def create_app(test_config=None):
    app = Flask(__name__, instance_path=str(ROOT / "instance"))
    app.config.update(settings())
    if test_config:
        app.config.update(test_config)
    Path(app.instance_path).mkdir(parents=True, exist_ok=True)
    if len(app.config["SECRET_KEY"]) < 32:
        raise RuntimeError("Nastavte SECRET_KEY. Lokálne spustite python init_env.py.")
    try:
        encryption_key = app.config["ENCRYPTION_KEY"]
        if not isinstance(encryption_key, str) or not encryption_key:
            raise ValueError
        Fernet(encryption_key.encode("ascii"))
    except (ValueError, TypeError, UnicodeEncodeError):
        raise RuntimeError(
            "ENCRYPTION_KEY chýba alebo nie je platný kľúč Fernet. "
            "Nastavte pôvodnú hodnotu z .env (rovnakú pre web aj worker); "
            "pri existujúcich dátach kľúč nemeňte."
        ) from None
    if app.config["PRODUCTION"]:
        required = ("CONTROLLER_NAME", "PRIVACY_EMAIL")
        if not app.config["BASE_URL"].startswith("https://") or any(not app.config[k] for k in required):
            raise RuntimeError("Produkcia vyžaduje HTTPS BASE_URL a údaje prevádzkovateľa v .env.")
    if app.config["TRUST_PROXY"]:
        # Only enable behind exactly one trusted reverse proxy; block direct access.
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1)
    db.init_app(app)
    csrf.init_app(app)
    limiter.init_app(app)
    dummy_hash = generate_password_hash(secrets.token_urlsafe(24), method="scrypt")

    @app.before_request
    def load_agent():
        g.agent = None
        agent_id = session.get("agent_id")
        if agent_id:
            agent = db.session.get(Agent, agent_id)
            if agent and agent.active and session.get("session_version") == agent.session_version:
                g.agent = agent
            else:
                session.clear()

    @app.after_request
    def headers(response):
        response.headers.update({
            "X-Content-Type-Options": "nosniff", "X-Frame-Options": "DENY",
            "Referrer-Policy": "same-origin", "Cache-Control": "no-store",
            "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
            "Content-Security-Policy": "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; font-src 'self'; object-src 'none'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'",
        })
        if app.config["PRODUCTION"]:
            response.headers["Strict-Transport-Security"] = "max-age=31536000"
        return response

    app.jinja_env.filters["money"] = money
    app.jinja_env.filters["number"] = number
    app.jinja_env.filters["localtime"] = lambda value: value.replace(tzinfo=timezone.utc).astimezone(ZoneInfo("Europe/Bratislava")).strftime("%d. %m. %Y %H:%M")

    @app.context_processor
    def shared():
        return dict(organization=app.config["ORGANIZATION_NAME"], goals=GOALS, debt_types=DEBT_TYPES,
                    statuses=STATUSES, job_labels=JOB_LABELS, delivery_labels=DELIVERY_LABELS, ai_labels=AI_LABELS)

    @app.get("/")
    def index():
        return redirect(url_for("dashboard") if g.agent else url_for("login"))

    @app.route("/login", methods=["GET", "POST"])
    @limiter.limit("10 per minute")
    def login():
        if g.agent:
            return redirect(url_for("dashboard"))
        if request.method == "POST":
            email = request.form.get("email", "").strip().lower()[:254]
            password = request.form.get("password", "")[:1024]
            agent = db.session.execute(db.select(Agent).where(Agent.email == email)).scalar_one_or_none()
            valid = check_password_hash(agent.password_hash if agent else dummy_hash, password)
            locked = agent and agent.locked_until and agent.locked_until > utcnow()
            if agent and agent.active and valid and not locked:
                agent.failed_logins = 0
                agent.locked_until = None
                audit(agent.id, "login")
                db.session.commit()
                establish_session(agent)
                return redirect(url_for("dashboard"))
            if agent and not locked:
                agent.failed_logins += 1
                if agent.failed_logins >= 5:
                    agent.locked_until = utcnow() + timedelta(minutes=15)
                    agent.failed_logins = 0
                db.session.commit()
            flash("Prihlásenie sa nepodarilo. Skontrolujte údaje alebo skúste neskôr.", "error")
        return render_template("login.html")

    @app.post("/logout")
    def logout():
        session.clear()
        return redirect(url_for("login"))

    @app.route("/formular/<token>", methods=["GET", "POST"])
    @limiter.limit("20 per hour", methods=["POST"])
    def questionnaire(token):
        agent = db.session.execute(db.select(Agent).where(Agent.invite_digest == token_digest(token), Agent.active.is_(True))).scalar_one_or_none()
        if not agent:
            abort(404)
        key = f"submission_{agent.id}"
        if key not in session:
            session[key] = secrets.token_hex(32)
        errors, debts = [], []
        if request.method == "GET" and session.pop(f"submitted_{agent.id}", False):
            session[key] = secrets.token_hex(32)
        if request.method == "POST":
            if not secrets.compare_digest(request.form.get("submission_key", ""), session[key]):
                abort(400)
            previous = db.session.execute(db.select(Inquiry.id).where(Inquiry.submission_key == session[key])).scalar_one_or_none()
            if previous:
                return redirect(url_for("thanks"))
            if request.form.get("website"):
                abort(400)
            try:
                data = parse_client(request.form)
                data.update(submitted_at=utcnow().isoformat() + "Z", privacy_version=app.config["PRIVACY_VERSION"])
                inquiry = Inquiry(agent_id=agent.id, submission_key=session[key], data_encrypted=encrypt(data),
                                  analysis_encrypted=encrypt(fallback_analysis(data, "Analýza čaká na spracovanie.")))
                db.session.add(inquiry)
                db.session.flush()
                enqueue(inquiry.id, "analyze", f"analysis:{inquiry.id}")
                audit(agent.id, "questionnaire_received", inquiry.id)
                db.session.commit()
                session[f"submitted_{agent.id}"] = True
                return redirect(url_for("thanks"))
            except (ValidationError, ValueError) as exc:
                db.session.rollback()
                errors = validation_errors(exc)
                try:
                    debts = form_debts(request.form)
                except ValueError:
                    debts = []
            except IntegrityError:
                db.session.rollback()
                # Concurrent double-clicks are harmless only if this same key exists.
                if db.session.execute(db.select(Inquiry.id).where(Inquiry.submission_key == session[key])).scalar_one_or_none():
                    return redirect(url_for("thanks"))
                raise
        return render_template("questionnaire.html", agent=agent, token=token, submission_key=session[key],
                               values=request.form if request.method == "POST" else {}, debts=debts, errors=errors), 422 if errors else 200

    @app.get("/dakujeme")
    def thanks():
        return render_template("thanks.html")

    @app.get("/ochrana-udajov")
    def privacy():
        return render_template("privacy.html", cfg=app.config)

    @app.get("/dashboard")
    @login_required
    def dashboard():
        search, status = request.args.get("q", "").strip()[:100], request.args.get("status", "")
        items = db.session.execute(db.select(Inquiry).where(Inquiry.agent_id == g.agent.id).order_by(Inquiry.created_at.desc())).scalars().all()
        all_count = len(items)
        rows = []
        for inquiry in items:
            data = inquiry.data
            haystack = " ".join(str(data[k]) for k in ("first_name", "last_name", "email", "phone")).casefold()
            if search.casefold() not in haystack or (status in STATUSES and inquiry.status != status):
                continue
            rows.append(dict(inquiry=inquiry, data=data, metrics=financial_profile(data)))
        page = max(1, min(request.args.get("page", 1, type=int), max(1, (len(rows) + 19) // 20)))
        return render_template("dashboard.html", rows=rows[(page-1)*20:page*20], total=len(rows), all_count=all_count,
                               page=page, pages=max(1, (len(rows)+19)//20), q=search, status=status,
                               invite_url=app.config["BASE_URL"] + url_for("questionnaire", token=g.agent.invite_token))

    def detail_page(inquiry, errors=None, values=None):
        data = inquiry.data
        proposal = inquiry.proposal
        jobs = db.session.execute(db.select(Job).where(Job.inquiry_id == inquiry.id).order_by(Job.id.desc())).scalars().all()
        summaries = db.session.execute(db.select(Summary).where(Summary.inquiry_id == inquiry.id).order_by(Summary.created_at.desc())).scalars().all()
        return render_template("detail.html", inquiry=inquiry, data=data, metrics=financial_profile(data),
                               analysis=inquiry.analysis, proposal=proposal, comparison=compare_proposal(data, proposal) if proposal else None,
                               documents=document_checklist(data), jobs=jobs, summaries=summaries, errors=errors or [],
                               can_retry_unavailable_ai=inquiry.ai_status == "unavailable" and data.get("ai_consent") is True,
                               values=values if values is not None else proposal or {})

    @app.get("/klienti/<inquiry_id>")
    @login_required
    def detail(inquiry_id):
        inquiry = owned_inquiry(inquiry_id)
        audit(g.agent.id, "view_detail", inquiry.id)
        db.session.commit()
        return detail_page(inquiry)

    @app.post("/klienti/<inquiry_id>/stav")
    @login_required
    def set_status(inquiry_id):
        inquiry = owned_inquiry(inquiry_id)
        status = request.form.get("status")
        if status not in STATUSES:
            abort(400)
        inquiry.status = status
        audit(g.agent.id, "status_changed", inquiry.id)
        db.session.commit()
        return redirect(url_for("detail", inquiry_id=inquiry.id))

    @app.post("/klienti/<inquiry_id>/navrh")
    @login_required
    def save_proposal(inquiry_id):
        inquiry = owned_inquiry(inquiry_id)
        try:
            proposal = parse_proposal(request.form)
            compare_proposal(inquiry.data, proposal)
            revision = request.form.get("revision", type=int)
            changed = db.session.execute(update(Inquiry).where(Inquiry.id == inquiry.id, Inquiry.proposal_revision == revision).values(
                proposal_encrypted=encrypt(proposal), proposal_revision=Inquiry.proposal_revision + 1, status="proposal"))
            if changed.rowcount != 1:
                db.session.rollback()
                flash("Návrh sa medzičasom zmenil. Obnovte stránku a skontrolujte aktuálnu verziu.", "error")
                return redirect(url_for("detail", inquiry_id=inquiry.id))
            audit(g.agent.id, "proposal_saved", inquiry.id)
            db.session.commit()
            flash("Návrh je uložený a prepočítaný. Skontrolujte PDF pred odoslaním.", "success")
            return redirect(url_for("detail", inquiry_id=inquiry.id, _anchor="solution"))
        except (ValidationError, ValueError) as exc:
            db.session.rollback()
            values = request.form.to_dict()
            values["replace_ids"] = request.form.getlist("replace_ids")
            return detail_page(inquiry, validation_errors(exc), values), 422

    @app.get("/klienti/<inquiry_id>/report.pdf")
    @login_required
    def report_pdf(inquiry_id):
        inquiry = owned_inquiry(inquiry_id)
        internal = request.args.get("internal") == "1"
        if not internal and not inquiry.proposal:
            abort(400)
        audit(g.agent.id, "download_internal_pdf" if internal else "preview_client_pdf", inquiry.id)
        db.session.commit()
        return send_file(io.BytesIO(build_report(make_snapshot(inquiry), internal=internal)), mimetype="application/pdf",
                         as_attachment=False, download_name="financny-prehlad.pdf")

    @app.post("/klienti/<inquiry_id>/odoslat")
    @login_required
    def send_summary(inquiry_id):
        inquiry = owned_inquiry(inquiry_id)
        if not inquiry.proposal or request.form.get("reviewed") != "1":
            flash("Najskôr uložte návrh a potvrďte kontrolu reportu.", "error")
            return redirect(url_for("detail", inquiry_id=inquiry.id))
        revision = request.form.get("revision", type=int)
        if revision != inquiry.proposal_revision:
            abort(409)
        summary = Summary(inquiry_id=inquiry.id, revision=revision, snapshot_encrypted=encrypt(make_snapshot(inquiry)))
        try:
            db.session.add(summary)
            db.session.flush()
            enqueue(inquiry.id, "send_summary", f"summary:{summary.id}", summary.id)
            audit(g.agent.id, "summary_approved_and_queued", inquiry.id)
            db.session.commit()
            flash("Sumarizácia je vo fronte. Stav prijatia poskytovateľom uvidíte v histórii.", "success")
        except IntegrityError:
            db.session.rollback()
            flash("Táto verzia návrhu už má sumarizáciu vo fronte alebo v histórii.", "info")
        return redirect(url_for("detail", inquiry_id=inquiry.id, _anchor="delivery"))

    @app.get("/klienti/<inquiry_id>/sumarizacie/<summary_id>.pdf")
    @login_required
    def historical_report(inquiry_id, summary_id):
        owned_inquiry(inquiry_id)
        summary = db.session.get(Summary, summary_id)
        if not summary or summary.inquiry_id != inquiry_id:
            abort(404)
        return send_file(io.BytesIO(build_report(summary.snapshot)), mimetype="application/pdf", download_name="financny-prehlad.pdf")

    @app.post("/klienti/<inquiry_id>/ulohy/<int:job_id>/opakovat")
    @login_required
    def retry_job(inquiry_id, job_id):
        inquiry = owned_inquiry(inquiry_id)
        job = db.session.get(Job, job_id)
        if not job or job.inquiry_id != inquiry.id:
            abort(400)
        retry_unavailable_ai = (job.kind == "analyze" and job.status == "done"
                                and inquiry.ai_status == "unavailable" and inquiry.data.get("ai_consent") is True)
        if job.status not in ("failed", "blocked", "uncertain") and not retry_unavailable_ai:
            abort(400)
        if job.status == "uncertain" and request.form.get("duplicate_ack") != "1":
            flash("Najskôr overte stav u poskytovateľa; opakovanie môže vytvoriť duplicitný e-mail.", "error")
            return redirect(url_for("detail", inquiry_id=inquiry.id))
        job.status, job.attempts, job.available_at = "pending", 0, utcnow()
        job.last_error = None
        if job.summary_id:
            db.session.get(Summary, job.summary_id).delivery_status = "pending"
        if job.kind == "analyze":
            inquiry.ai_status = "pending"
        audit(g.agent.id, "job_retry_requested", inquiry.id)
        db.session.commit()
        return redirect(url_for("detail", inquiry_id=inquiry.id, _anchor="delivery"))

    @app.post("/nastavenia/novy-odkaz")
    @login_required
    def rotate_invite():
        g.agent.rotate_link()
        audit(g.agent.id, "invite_rotated")
        db.session.commit()
        flash("Nový odkaz je aktívny. Predchádzajúci odkaz už nefunguje.", "success")
        return redirect(url_for("dashboard"))

    @app.post("/klienti/<inquiry_id>/vymazat")
    @login_required
    def delete_inquiry(inquiry_id):
        inquiry = owned_inquiry(inquiry_id)
        if request.form.get("confirm_delete") != "1":
            abort(400)
        running = db.session.execute(db.select(Job.id).where(Job.inquiry_id == inquiry.id, Job.status == "running")).first()
        if running:
            flash("Dopyt práve spracúva worker. Vymazanie zopakujte po dokončení úlohy.", "error")
            return redirect(url_for("detail", inquiry_id=inquiry.id))
        # Child records cascade in the DB. Purged audit events contain no client data.
        db.session.delete(inquiry)
        audit(g.agent.id, "inquiry_deleted")
        db.session.commit()
        flash("Dopyt a súvisiace údaje boli vymazané z aplikácie.", "success")
        return redirect(url_for("dashboard"))

    @app.get("/healthz")
    @limiter.exempt
    def health():
        try:
            db.session.execute(db.select(Agent.id).limit(1))
            return {"status": "ok"}
        except Exception:
            db.session.rollback()
            return {"status": "unavailable"}, 503

    @app.errorhandler(CSRFError)
    def csrf_error(_error):
        return render_template("error.html", code=400, message="Formulár vypršal alebo chýba overenie. Obnovte stránku a odošlite ho znova."), 400

    for code, message in {400: "Neplatná požiadavka.", 404: "Stránka alebo odkaz neexistuje.",
                          409: "Údaje sa medzičasom zmenili. Obnovte stránku.",
                          413: "Odoslané údaje sú príliš veľké.", 429: "Príliš veľa požiadaviek. Skúste neskôr.",
                          500: "Požiadavku sa nepodarilo dokončiť. Skúste neskôr."}.items():
        def error_handler(error, error_code=code, error_message=message):
            # An untrusted Host has no URL adapter, so base.html cannot build links.
            if isinstance(error, SecurityError):
                return "Neplatná požiadavka.", 400, {"Content-Type": "text/plain; charset=utf-8"}
            if error_code == 500:
                db.session.rollback()
            return render_template("error.html", code=error_code, message=error_message), error_code
        app.register_error_handler(code, error_handler)

    register_cli(app)
    return app


def register_cli(app):
    @app.cli.command("init-db")
    def init_db():
        """Create schema on first install (not a migration tool)."""
        db.create_all()
        click.echo("Databáza je pripravená.")

    @app.cli.command("create-agent")
    @click.option("--email", prompt="E-mail agenta")
    @click.option("--name", prompt="Meno agenta")
    @click.password_option(confirmation_prompt=True)
    def create_agent(email, name, password):
        try:
            email = validate_email(email, check_deliverability=False).normalized.lower()
        except EmailNotValidError:
            raise click.ClickException("Neplatný e-mail.") from None
        if len(password) < 12 or len(password) > 256 or not name.strip() or len(name) > 160:
            raise click.ClickException("Heslo musí mať 12 až 256 znakov a meno 1 až 160 znakov.")
        agent = Agent.create(email, name.strip(), password)
        try:
            db.session.add(agent)
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            raise click.ClickException("Tento agent už existuje.") from None
        click.echo("Agent vytvorený. Odkaz na dotazník je po prihlásení v dashboarde.")

    @app.cli.command("reset-password")
    @click.option("--email", prompt="E-mail agenta")
    @click.password_option(confirmation_prompt=True)
    def reset_password(email, password):
        agent = db.session.execute(db.select(Agent).where(Agent.email == email.strip().lower())).scalar_one_or_none()
        if not agent or not 12 <= len(password) <= 256:
            raise click.ClickException("Agent neexistuje alebo heslo nemá 12 až 256 znakov.")
        agent.password_hash = generate_password_hash(password, method="scrypt")
        agent.session_version += 1
        agent.failed_logins = 0
        agent.locked_until = None
        db.session.commit()
        click.echo("Heslo zmenené. Staré relácie boli zneplatnené.")

    @app.cli.command("purge-expired")
    @click.option("--apply", is_flag=True, help="Without this flag, only count records.")
    def purge_expired(apply):
        cutoff = utcnow() - timedelta(days=app.config["RETENTION_DAYS"])
        running = db.select(Job.inquiry_id).where(Job.status == "running")
        query = db.select(Inquiry).where(Inquiry.created_at < cutoff, Inquiry.id.not_in(running))
        records = db.session.execute(query).scalars().all()
        click.echo(f"Staršie ako {app.config['RETENTION_DAYS']} dní: {len(records)} dopytov.")
        if apply:
            for inquiry in records:
                db.session.delete(inquiry)
            db.session.commit()
            click.echo("Vymazané z aplikácie. Kópie v e-mailoch a zálohách rieši prevádzkovateľ.")


if __name__ == "__main__":
    create_app().run(host="127.0.0.1", port=5000, debug=False)
