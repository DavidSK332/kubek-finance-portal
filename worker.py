"""Run separately: python worker.py. Queue is durable in the same SQL DB."""
import argparse
import secrets
import time
from datetime import timedelta

from flask import current_app
from sqlalchemy import or_, update

from ai_analysis import analyze, fallback_analysis
from database import Inquiry, Job, Summary, audit, db, enqueue, utcnow
from email_service import DeliveryUncertain, MailConfigurationError, deliver
from pdf_service import build_report, report_text
from reporting import make_snapshot
from security import encrypt


def recover_expired():
    expired = db.session.execute(db.select(Job).where(Job.status == "running", Job.lease_until < utcnow())).scalars().all()
    for job in expired:
        # A crashed email worker may have sent the message before persisting success.
        job.status = "pending" if job.kind == "analyze" else "uncertain"
        job.last_error = "EXPIRED_LEASE"
        if job.summary_id:
            summary = db.session.get(Summary, job.summary_id)
            if summary:
                summary.delivery_status = "uncertain"
        job.lease_token = None
    db.session.commit()


def claim_job():
    recover_expired()
    for _ in range(5):
        now = utcnow()
        candidate = db.session.execute(db.select(Job.id).where(
            Job.status == "pending", Job.available_at <= now).order_by(Job.id).limit(1)).scalar_one_or_none()
        if candidate is None:
            return None
        token = secrets.token_hex(16)
        changed = db.session.execute(update(Job).where(Job.id == candidate, Job.status == "pending").values(
            status="running", lease_token=token, lease_until=now + timedelta(minutes=5), attempts=Job.attempts + 1))
        db.session.commit()
        if changed.rowcount:
            return db.session.get(Job, candidate)
    return None


def queue_notification(inquiry):
    key = f"notify:{inquiry.id}"
    if not db.session.execute(db.select(Job.id).where(Job.dedupe_key == key)).scalar_one_or_none():
        enqueue(inquiry.id, "notify_agent", key)


def process_one():
    job = claim_job()
    if not job:
        return False
    job_id = job.id
    try:
        inquiry = db.session.get(Inquiry, job.inquiry_id)
        if not inquiry:
            return True
        if job.kind == "analyze":
            result, status = analyze(inquiry.data)
            inquiry.analysis_encrypted = encrypt(result)
            inquiry.ai_status = status
            queue_notification(inquiry)
        elif job.kind == "notify_agent":
            snapshot = make_snapshot(inquiry, include_proposal=False)
            deliver(to=inquiry.agent.email, subject="Nový finančný profil klienta",
                    body=report_text(snapshot, internal=True), message_key=f"agent-{inquiry.id}",
                    pdf=build_report(snapshot, internal=True))
        elif job.kind == "send_summary":
            summary = db.session.get(Summary, job.summary_id)
            if not summary or summary.delivery_status == "accepted":
                job.status = "done"
                db.session.commit()
                return True
            snapshot = summary.snapshot
            reference = deliver(to=snapshot["data"]["email"], cc=snapshot["agent_email"],
                                subject="Váš finančný prehľad a navrhované riešenie",
                                body=report_text(snapshot), message_key=f"summary-{summary.id}",
                                pdf=build_report(snapshot))
            summary.delivery_status = "accepted"
            summary.provider_reference = reference[:200]
            summary.sent_at = utcnow()
            audit(inquiry.agent_id, "summary_provider_accepted", inquiry.id)
        else:
            raise ValueError("UNKNOWN_JOB_KIND")
        job.status = "done"
        job.last_error = None
        job.lease_token = None
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        job = db.session.get(Job, job_id)
        if not job:  # A record may have been deleted by its owner during processing.
            return True
        inquiry = db.session.get(Inquiry, job.inquiry_id)
        # Never persist exception messages: providers can echo personal data or secrets.
        job.last_error = type(exc).__name__
        job.lease_token = None
        if isinstance(exc, DeliveryUncertain):
            job.status = "uncertain"
        elif isinstance(exc, MailConfigurationError):
            job.status = "blocked"
        elif job.attempts < current_app.config["MAX_JOB_ATTEMPTS"]:
            job.status = "pending"
            job.available_at = utcnow() + timedelta(seconds=30 * 2 ** (job.attempts - 1))
        else:
            job.status = "failed"
            if job.kind == "analyze" and inquiry:
                inquiry.ai_status = "failed"
                inquiry.analysis_encrypted = encrypt(fallback_analysis(inquiry.data, "AI analýza sa nepodarila; dostupné sú výpočty."))
                queue_notification(inquiry)
        if job.summary_id:
            summary = db.session.get(Summary, job.summary_id)
            if summary:
                summary.delivery_status = job.status
        db.session.commit()
        current_app.logger.warning("Job %s kind=%s status=%s error_type=%s", job.id, job.kind, job.status, type(exc).__name__)
    finally:
        db.session.remove()
    return True


def main():
    from app import create_app
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true", help="Process the available queue and exit.")
    args = parser.parse_args()
    app = create_app()
    with app.app_context():
        while True:
            processed = process_one()
            if not processed:
                if args.once:
                    break
                time.sleep(2)


if __name__ == "__main__":
    main()
