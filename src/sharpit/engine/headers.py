"""Response-header policy (port of BootUI ``BootUiSecurityHeaders``)."""

from __future__ import annotations

from typing import Literal

CSP = (
    "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline';"
    " img-src 'self' data:; font-src 'self' data:; connect-src 'self';"
    " object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'"
)
PERMISSIONS_POLICY = (
    "accelerometer=(), camera=(), geolocation=(), gyroscope=(), magnetometer=(), microphone=(), payment=(), usb=()"
)
NO_STORE = "no-store, must-revalidate"
IMMUTABLE = "public, max-age=31536000, immutable"
NO_CACHE = "no-cache"


def security_headers(kind: Literal["api", "shell", "asset"]) -> list[tuple[str, str]]:
    """Security headers plus the cache headers for the response class (``Pragma`` is absent for assets)."""
    headers = [
        ("Content-Security-Policy", CSP),
        ("X-Content-Type-Options", "nosniff"),
        ("X-Frame-Options", "DENY"),
        ("Referrer-Policy", "strict-origin-when-cross-origin"),
        ("Permissions-Policy", PERMISSIONS_POLICY),
        ("Cache-Control", {"api": NO_STORE, "shell": NO_CACHE, "asset": IMMUTABLE}[kind]),
    ]
    if kind != "asset":
        headers.append(("Pragma", "no-cache"))
    return headers
