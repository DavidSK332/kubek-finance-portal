from datetime import timezone
from zoneinfo import ZoneInfo

from flask import current_app

from database import utcnow
from finance import compare_proposal, financial_profile


def make_snapshot(inquiry, include_proposal=True):
    data = inquiry.data
    proposal = inquiry.proposal if include_proposal else None
    return {
        "data": data, "metrics": financial_profile(data), "analysis": inquiry.analysis,
        "proposal": proposal,
        "comparison": compare_proposal(data, proposal) if proposal else None,
        "revision": inquiry.proposal_revision,
        "organization": current_app.config["ORGANIZATION_NAME"],
        "agent_name": inquiry.agent.name, "agent_email": inquiry.agent.email,
        "created_label": utcnow().replace(tzinfo=timezone.utc).astimezone(ZoneInfo("Europe/Bratislava")).strftime("%d. %m. %Y %H:%M"),
    }
