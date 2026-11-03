"""Source rules over the app's own package (``engine/appsource.py``): password hashing and literal secrets."""

from __future__ import annotations

from sharpit.engine.collectors.security import Inputs, SecurityRule, Violation, rule

_PASSLIB = "https://passlib.readthedocs.io/en/stable/narr/context-tutorial.html"


def _none(_inputs: Inputs) -> list[Violation]:
    return []


RULES: tuple[SecurityRule, ...] = (
    SecurityRule(
        rule(
            "SEC-AUTH-001",
            "Password encoder must not store credentials in plain text",
            "Authentication",
            "CRITICAL",
            "A passlib CryptContext lists a plaintext scheme: passwords would be stored as typed.",
            "Hash passwords with argon2 or bcrypt and drop the plaintext scheme.",
            _PASSLIB,
        ),
        _none,
        needs_source=True,
    ),
    SecurityRule(
        rule(
            "SEC-AUTH-002",
            "Password encoder should not use a weak or legacy algorithm",
            "Authentication",
            "HIGH",
            "A passlib CryptContext hashes new passwords with a legacy algorithm (MD5, SHA-1, DES based or unsalted).",
            "Make argon2 or bcrypt the default scheme and mark the legacy ones deprecated.",
            _PASSLIB,
        ),
        _none,
        needs_source=True,
    ),
    SecurityRule(
        rule(
            "SEC-AUTH-006",
            "BCrypt password encoder should use an adequate work factor",
            "Authentication",
            "LOW",
            "bcrypt runs with fewer than 10 rounds, which makes offline guessing cheap.",
            "Use at least 12 bcrypt rounds (passlib's default) or argon2.",
            _PASSLIB,
        ),
        _none,
        needs_source=True,
    ),
    SecurityRule(
        rule(
            "SEC-SRC-001",
            "Source code should not hold literal secret values",
            "Configuration",
            "HIGH",
            "The app source holds a literal the secret detectors flag (a token, key or URL credential) or assigns a"
            " literal to a secret-like name. Only the location is reported.",
            "Move the secret to the environment or a secret store and rotate it.",
            "https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html",
        ),
        _none,
        needs_source=True,
    ),
)
