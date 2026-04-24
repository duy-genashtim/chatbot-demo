"""SQLAlchemy models package — import all models here so Base.metadata is populated."""

from app.models.app_setting import AppSetting  # noqa: F401
from app.models.admin_user import AdminUser  # noqa: F401
from app.models.chat_turn import ChatTurn  # noqa: F401
from app.models.document import Document  # noqa: F401
from app.models.audit_log import AuditLog  # noqa: F401
