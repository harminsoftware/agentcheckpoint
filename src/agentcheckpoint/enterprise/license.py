"""License validation engine using Ed25519 signed JWT.

License keys are Ed25519-signed JWTs containing:
- org: Organization name
- seats: Number of licensed seats
- features: List of enabled enterprise features
- expires_at: ISO 8601 expiration date

Validation is fully offline — no network calls needed.
"""

from __future__ import annotations

import json
import base64
import logging
from datetime import datetime, timezone
from typing import Optional

from agentcheckpoint.enterprise import LicenseInfo

logger = logging.getLogger(__name__)

# Ed25519 public key for license validation (replace with real key in production)
# This is the PUBLIC key only — the private key is held by the license server
_PUBLIC_KEY_B64 = "MCowBQYDK2VwAyEAPlaceholderKeyForDevelopment000000000000="


def validate_license(key: str) -> LicenseInfo:
    """Validate a license key and return license info.

    The key is a base64url-encoded Ed25519-signed JWT.
    Validation is offline — only checks the cryptographic signature and expiry.
    """
    if not key or not key.strip():
        return LicenseInfo(is_valid=False, error="Empty license key")

    try:
        payload = _decode_and_verify(key)
    except Exception as e:
        logger.debug(f"License validation failed: {e}")
        return LicenseInfo(is_valid=False, error=f"Invalid license key: {e}")

    # Check expiration
    expires_at = payload.get("expires_at", "")
    if expires_at:
        try:
            expiry = datetime.fromisoformat(expires_at)
            if expiry < datetime.now(timezone.utc):
                return LicenseInfo(
                    is_valid=False,
                    org=payload.get("org", ""),
                    expires_at=expires_at,
                    error=f"License expired on {expires_at}",
                )
        except ValueError:
            pass

    return LicenseInfo(
        is_valid=True,
        org=payload.get("org", ""),
        seats=payload.get("seats", 0),
        features=payload.get("features", []),
        expires_at=expires_at,
    )


def _decode_and_verify(key: str) -> dict:
    """Decode and verify the license key signature.

    License format: base64url(header).base64url(payload).base64url(signature)
    """
    try:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
        from cryptography.hazmat.primitives.serialization import load_der_public_key
    except ImportError:
        raise ImportError(
            "cryptography is required for license validation. "
            "Install with: pip install agentcheckpoint[enterprise]"
        )

    parts = key.strip().split(".")
    if len(parts) != 3:
        raise ValueError("License key must have 3 parts (header.payload.signature)")

    header_b64, payload_b64, sig_b64 = parts

    # Decode payload
    payload_bytes = base64.urlsafe_b64decode(payload_b64 + "==")
    payload = json.loads(payload_bytes)

    # Verify signature
    try:
        public_key_bytes = base64.b64decode(_PUBLIC_KEY_B64)
        public_key = load_der_public_key(public_key_bytes)

        if not isinstance(public_key, Ed25519PublicKey):
            raise ValueError("Invalid public key type")

        signed_data = f"{header_b64}.{payload_b64}".encode("utf-8")
        sig = base64.urlsafe_b64decode(sig_b64 + "==")
        public_key.verify(sig, signed_data)
    except Exception as e:
        # In development mode, allow unverified keys with a warning
        if payload.get("dev_mode"):
            logger.warning("Using development license key — signature not verified")
        else:
            raise ValueError(f"Signature verification failed: {e}")

    return payload


def generate_dev_license(
    org: str = "dev",
    seats: int = 999,
    features: list[str] | None = None,
    days_valid: int = 365,
) -> str:
    """Generate a development-mode license key (NOT for production).

    This generates an unsigned key with dev_mode=true that bypasses
    signature verification. Only use for local development and testing.
    """
    from datetime import timedelta

    if features is None:
        features = ["sso", "audit", "rbac", "auto_resume", "telemetry"]

    expires_at = (datetime.now(timezone.utc) + timedelta(days=days_valid)).isoformat()

    header = base64.urlsafe_b64encode(json.dumps({"alg": "EdDSA", "typ": "JWT"}).encode()).rstrip(b"=").decode()
    payload = base64.urlsafe_b64encode(
        json.dumps({
            "org": org,
            "seats": seats,
            "features": features,
            "expires_at": expires_at,
            "dev_mode": True,
        }).encode()
    ).rstrip(b"=").decode()
    # Dummy signature for dev mode
    sig = base64.urlsafe_b64encode(b"dev_signature_placeholder").rstrip(b"=").decode()

    return f"{header}.{payload}.{sig}"
