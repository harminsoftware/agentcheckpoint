"""Enterprise features module — gated by license key.

The enterprise features are available in the PyPI package but require
a valid license key to use. Without a license key, calling any enterprise
feature raises LicenseError with a helpful message.
"""

from __future__ import annotations

import os
from typing import Optional


class LicenseError(Exception):
    """Raised when an enterprise feature is used without a valid license."""


class LicenseInfo:
    """License validation result."""

    def __init__(
        self,
        is_valid: bool = False,
        org: str = "",
        seats: int = 0,
        features: list[str] | None = None,
        expires_at: str = "",
        error: str = "",
    ):
        self.is_valid = is_valid
        self.org = org
        self.seats = seats
        self.features = features or []
        self.expires_at = expires_at
        self.error = error


_license: Optional[LicenseInfo] = None


def require_enterprise(feature_name: str) -> LicenseInfo:
    """Call at the top of any enterprise feature. Raises if no valid license.

    Usage:
        def my_enterprise_feature():
            require_enterprise("SSO/SAML Authentication")
            # ... feature code ...
    """
    global _license
    if _license is None:
        key = os.environ.get("AGENTCHECKPOINT_LICENSE_KEY", "")
        if key:
            from agentcheckpoint.enterprise.license import validate_license
            _license = validate_license(key)
        else:
            _license = LicenseInfo(
                is_valid=False,
                error="No license key found. Set AGENTCHECKPOINT_LICENSE_KEY environment variable.",
            )

    if not _license.is_valid:
        raise LicenseError(
            f"'{feature_name}' requires an AgentCheckpoint Enterprise license.\n"
            f"  Error: {_license.error}\n"
            f"  Get a license at: https://agentcheckpoint.dev/enterprise\n"
            f"  Set: export AGENTCHECKPOINT_LICENSE_KEY=<your-key>"
        )

    return _license


def reset_license() -> None:
    """Reset cached license (useful for testing)."""
    global _license
    _license = None
