from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.time import utcnow
from app.models import ApprovalRequest, AuditEvent

DISCOUNT_AUTO_APPROVAL_LIMIT_INR = 10_000
DISCOUNT_RECOMMENDED_CEILING_INR = 20_000


def request_discount_approval(db: Session, lead_id: int, requested_discount_inr: int):
    if requested_discount_inr <= DISCOUNT_AUTO_APPROVAL_LIMIT_INR:
        db.add(
            AuditEvent(
                event_type="discount.within_policy",
                entity_type="lead",
                entity_id=str(lead_id),
                payload={"requested_discount_inr": requested_discount_inr},
            )
        )
        db.commit()
        return {"approval_required": False, "allowed_discount_inr": requested_discount_inr}

    existing = db.scalar(
        select(ApprovalRequest).where(
            ApprovalRequest.lead_id == lead_id,
            ApprovalRequest.action == "discount",
            ApprovalRequest.requested_value == str(requested_discount_inr),
            ApprovalRequest.status == "PENDING",
        )
    )
    if existing:
        return {
            "approval_required": True,
            "approval_id": existing.id,
            "status": existing.status,
            "recommendation": existing.recommendation,
            "created": False,
        }

    rec = min(DISCOUNT_RECOMMENDED_CEILING_INR, requested_discount_inr)
    req = ApprovalRequest(
        lead_id=lead_id,
        action="discount",
        requested_value=str(requested_discount_inr),
        recommendation=f"Human approval required. Suggested ceiling for demo: INR {rec:,}.",
    )
    db.add(req)
    db.flush()
    db.add(
        AuditEvent(
            event_type="approval.requested",
            entity_type="approval",
            entity_id=str(req.id),
            payload={"lead_id": lead_id, "requested_discount_inr": requested_discount_inr},
        )
    )
    db.commit()
    db.refresh(req)
    return {
        "approval_required": True,
        "approval_id": req.id,
        "status": req.status,
        "recommendation": req.recommendation,
        "created": True,
    }


def decide_approval(db: Session, approval_id: int, decision: str, approved_value_inr: int | None, note: str | None):
    req = db.scalar(select(ApprovalRequest).where(ApprovalRequest.id == approval_id))
    if not req:
        return None
    normalized = decision.strip().upper()
    if normalized not in {"APPROVED", "REJECTED", "MODIFIED"}:
        raise ValueError("decision must be APPROVED, REJECTED, or MODIFIED")
    if req.status != "PENDING":
        return req
    if normalized in {"APPROVED", "MODIFIED"} and approved_value_inr is None:
        approved_value_inr = int(req.requested_value) if normalized == "APPROVED" else None
    if normalized == "MODIFIED" and approved_value_inr is None:
        raise ValueError("approved_value_inr is required for MODIFIED decisions")
    if approved_value_inr is not None and approved_value_inr > int(req.requested_value):
        raise ValueError("approved_value_inr cannot exceed the requested discount")
    req.status = normalized
    req.decision_value = str(approved_value_inr) if approved_value_inr is not None else None
    req.decision_note = note
    req.decided_at = utcnow()
    db.add(
        AuditEvent(
            event_type="approval.decided",
            entity_type="approval",
            entity_id=str(req.id),
            payload={"decision": normalized, "approved_value_inr": approved_value_inr, "note": note},
        )
    )
    db.commit()
    db.refresh(req)
    return req
