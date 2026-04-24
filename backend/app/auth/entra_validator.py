"""Microsoft Entra ID JWT validator using fastapi-azure-auth 5.x.

Provides a configured SingleTenantAzureAuthorizationCodeBearer instance
that validates access/id tokens issued by the tenant in AZURE_TENANT_ID.

Clock skew tolerance: 5-minute leeway applied via JWT decode options (R2).
Email claim fallback handled in dependencies.py (R1).
"""

from __future__ import annotations

import logging

from fastapi_azure_auth import SingleTenantAzureAuthorizationCodeBearer

from app.core.config import get_settings

logger = logging.getLogger(__name__)


def build_azure_scheme() -> SingleTenantAzureAuthorizationCodeBearer:
    """Build the auth scheme from current settings.

    Called once at module import time. AZURE_TENANT_ID / AZURE_CLIENT_ID
    may be empty in dev (no Entra app registered yet) — scheme loads
    regardless; token validation will fail at request time until real
    values are provided via environment variables.
    """
    settings = get_settings()

    # Dev-only bypass: when FAKE_AUTH_EMAIL is set in a non-prod env,
    # turn off auto_error so get_current_user can short-circuit without
    # a real Bearer token. Prod always enforces strict validation.
    dev_bypass = settings.ENVIRONMENT != "prod" and bool(settings.FAKE_AUTH_EMAIL)

    return SingleTenantAzureAuthorizationCodeBearer(
        app_client_id=settings.AZURE_CLIENT_ID,
        tenant_id=settings.AZURE_TENANT_ID,
        auto_error=not dev_bypass,
        scopes={
            f"api://{settings.AZURE_CLIENT_ID}/user_impersonation": "user_impersonation",
        },
        # 5-minute leeway covers clock skew between services (R2)
        leeway=300,
    )


# Module-level singleton — imported by dependencies.py
azure_scheme = build_azure_scheme()
