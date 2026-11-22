"""Inputs for the FastAPI transport response corpus."""

from typing import Any

TRANSPORT_CASES: tuple[dict[str, Any], ...] = (
    {"id": "inactive_api", "path": "/sharpit/api/panels", "install": {"enabled": "OFF"}},
    {"id": "inactive_index", "path": "/sharpit/", "install": {"enabled": "OFF"}},
    {"id": "inactive_other", "path": "/sharpit/not-a-route", "install": {"enabled": "OFF"}},
    {"id": "disallowed_host", "path": "/sharpit/api/panels", "headers": [("Host", "evil.example")]},
    {
        "id": "cross_site_fetch",
        "path": "/sharpit/api/panels",
        "headers": [("Sec-Fetch-Site", "cross-site")],
    },
    {"id": "cross_site_origin", "path": "/sharpit/api/panels", "headers": [("Origin", "http://evil.example")]},
    {
        "id": "duplicate_host",
        "path": "/sharpit/api/panels",
        "headers": [("Host", "localhost"), ("Host", "localhost")],
    },
    {
        "id": "duplicate_origin",
        "path": "/sharpit/api/panels",
        "headers": [("Origin", "http://localhost"), ("Origin", "http://localhost")],
    },
    {
        "id": "duplicate_fetch_site",
        "path": "/sharpit/api/panels",
        "headers": [("Sec-Fetch-Site", "same-origin"), ("Sec-Fetch-Site", "cross-site")],
    },
    {
        "id": "forwarded_source",
        "path": "/sharpit/api/panels",
        "headers": [("X-Forwarded-For", "127.0.0.1")],
    },
    {
        "id": "token_missing",
        "path": "/sharpit/api/panels",
        "install": {"allow_non_localhost": True, "authentication_token": "corpus-token"},
        "peer": ("10.0.0.5", 50000),
    },
    {
        "id": "token_wrong",
        "path": "/sharpit/api/panels",
        "install": {"allow_non_localhost": True, "authentication_token": "corpus-token"},
        "headers": [("Authorization", "Bearer wrong-token")],
        "peer": ("10.0.0.5", 50000),
    },
    {
        "id": "panel_disabled",
        "path": "/sharpit/api/architecture",
        "install": {"panels": {"architecture": {"enabled": False}}},
    },
    {
        "id": "read_only_action",
        "method": "POST",
        "path": "/sharpit/api/architecture/scan",
        "install": {"read_only": True},
    },
    {"id": "security_headers", "path": "/sharpit/"},
    {"id": "index_active", "path": "/sharpit/"},
)
