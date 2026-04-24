"""Admin user-allowlist management routes — list / add / remove.

Mounted under /api/admin (router-level require_admin applied in main.py).
"""

from __future__ import annotations

import logging
import re

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth.dependencies import User, require_admin
from app.core.db import get_db
from app.services import audit_service
from app.services.admin_service import AdminService

logger = logging.getLogger(__name__)

router = APIRouter(tags=["admin-admins"])

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class AddAdminBody(BaseModel):
    email: str


# ------------------------------------------------------------------ #
# GET /admins
# ------------------------------------------------------------------ #

@router.get("/admins")
def list_admins(
    db: Session = Depends(get_db),
    _user: User = Depends(require_admin),
):
    """Return all admin rows as [{email, created_at}]."""
    svc = AdminService(db)
    rows = svc.list_admins()
    return [
        {
            "email": r.email,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in rows
    ]


# ------------------------------------------------------------------ #
# POST /admins
# ------------------------------------------------------------------ #

@router.post("/admins", status_code=status.HTTP_201_CREATED)
def add_admin(
    body: AddAdminBody,
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
):
    """Add an email to the admin allowlist."""
    email = body.email.lower().strip()
    if not _EMAIL_RE.match(email):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Định dạng email không hợp lệ: {email!r}",
        )

    svc = AdminService(db)
    try:
        row = svc.add_admin(email)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    audit_service.log(
        db, actor_email=user.email, action="admin.add", target=email
    )
    return {
        "email": row.email,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


# ------------------------------------------------------------------ #
# DELETE /admins/{email}
# ------------------------------------------------------------------ #

@router.delete("/admins/{email}", status_code=status.HTTP_200_OK)
def remove_admin(
    email: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
):
    """Remove an email from the admin allowlist.

    Guardrails:
      (a) Cannot remove yourself.
      (b) Cannot remove the last admin.
    """
    normalised = email.lower().strip()

    if normalised == user.email.lower().strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Bạn không thể tự xóa chính mình khỏi danh sách quản trị.",
        )

    svc = AdminService(db)

    if svc.count_admins() <= 1:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Không thể xóa quản trị viên cuối cùng. Vui lòng thêm quản trị viên khác trước.",
        )

    try:
        svc.remove_admin(normalised)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))

    audit_service.log(
        db, actor_email=user.email, action="admin.remove", target=normalised
    )
    return {"removed": normalised}
