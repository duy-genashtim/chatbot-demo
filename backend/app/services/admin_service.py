"""Admin allowlist service — CRUD operations on the admin_users table.

All email comparisons are case-insensitive; values stored lowercase.
seed_default_admin() is idempotent: inserts DEFAULT_ADMIN_EMAIL only when
the table is empty (R3 from phase-02 risk assessment).
"""

from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.admin_user import AdminUser

logger = logging.getLogger(__name__)


class AdminService:
    """Wraps admin_users table operations for a single DB session."""

    def __init__(self, db: Session) -> None:
        self._db = db

    # ------------------------------------------------------------------ #
    # Queries
    # ------------------------------------------------------------------ #

    def is_admin(self, email: str) -> bool:
        """Return True if email is in the admin allowlist (case-insensitive)."""
        normalised = email.lower().strip()
        return (
            self._db.query(AdminUser)
            .filter(AdminUser.email == normalised)
            .first()
            is not None
        )

    def list_admins(self) -> list[AdminUser]:
        """Return all admin rows ordered by id."""
        return self._db.query(AdminUser).order_by(AdminUser.id).all()

    def count_admins(self) -> int:
        """Return total number of admin rows."""
        return self._db.query(AdminUser).count()

    # ------------------------------------------------------------------ #
    # Mutations
    # ------------------------------------------------------------------ #

    def add_admin(self, email: str) -> AdminUser:
        """Insert an admin row; raises ValueError if already present."""
        normalised = email.lower().strip()
        if self.is_admin(normalised):
            raise ValueError(f"Email already in admin list: {normalised}")
        row = AdminUser(email=normalised)
        self._db.add(row)
        self._db.commit()
        self._db.refresh(row)
        logger.info("Admin added: %s", normalised)
        return row

    def remove_admin(self, email: str) -> None:
        """Delete an admin row; raises ValueError if not found or last admin."""
        normalised = email.lower().strip()
        row = (
            self._db.query(AdminUser)
            .filter(AdminUser.email == normalised)
            .first()
        )
        if row is None:
            raise ValueError(f"Email not in admin list: {normalised}")
        if self.count_admins() <= 1:
            raise ValueError("Cannot remove the last admin.")
        self._db.delete(row)
        self._db.commit()
        logger.info("Admin removed: %s", normalised)

    # ------------------------------------------------------------------ #
    # Seed
    # ------------------------------------------------------------------ #

    def seed_default_admin(self) -> None:
        """Insert DEFAULT_ADMIN_EMAIL if the admin_users table is empty.

        Idempotent — safe to call on every startup (R3 mitigation).
        """
        if self.count_admins() > 0:
            return

        default_email = get_settings().DEFAULT_ADMIN_EMAIL
        if not default_email:
            logger.warning("DEFAULT_ADMIN_EMAIL not set — skipping admin seed.")
            return

        normalised = default_email.lower().strip()
        row = AdminUser(email=normalised)
        self._db.add(row)
        self._db.commit()
        logger.info("Default admin seeded: %s", normalised)
