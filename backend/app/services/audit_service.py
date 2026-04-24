"""Audit log service — records admin actions to the audit_log table.

Usage:
    audit_service.log(db, actor_email="admin@example.com",
                      action="document.upload", target="doc-uuid-123",
                      meta={"filename": "policy.pdf", "domain": "external_policy"})
"""

from __future__ import annotations

import json
import logging
from typing import Any

from sqlalchemy.orm import Session

from app.models.audit_log import AuditLog

logger = logging.getLogger(__name__)


def log(
    db: Session,
    actor_email: str,
    action: str,
    target: str | None = None,
    meta: dict[str, Any] | None = None,
) -> AuditLog:
    """Insert one audit_log row and return it.

    Never raises — on DB error, logs the failure and returns a dummy object
    so callers don't need try/except around every admin action.
    """
    meta_str: str | None = None
    if meta is not None:
        try:
            meta_str = json.dumps(meta, default=str)
        except Exception:
            meta_str = str(meta)

    row = AuditLog(
        actor_email=actor_email,
        action=action,
        target=target,
        meta=meta_str,
    )
    try:
        db.add(row)
        db.commit()
        db.refresh(row)
        logger.debug("Audit: %s → %s [%s]", actor_email, action, target)
    except Exception as exc:
        logger.error("Failed to write audit log (%s/%s): %s", action, target, exc)
        db.rollback()
    return row
