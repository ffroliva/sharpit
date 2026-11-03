"""Source rules over the app's own package (``engine/appsource.py``): password hashing and literal secrets."""

from __future__ import annotations

import ast
from collections.abc import Callable, Iterator

from sharpit.engine.collectors.security import Inputs, SecurityRule, Violation, rule, source_file, source_modules
from sharpit.engine.masking import is_secret_value, is_sensitive_key

_PASSLIB = "https://passlib.readthedocs.io/en/stable/narr/context-tutorial.html"


_PLAINTEXT = frozenset({"plaintext", "ldap_plaintext"})
_LEGACY = frozenset(
    {
        "md5_crypt", "apr_md5_crypt", "sun_md5_crypt", "des_crypt", "bsdi_crypt", "bigcrypt", "crypt16",
        "hex_md5", "hex_sha1", "hex_sha256", "hex_sha512", "ldap_md5", "ldap_sha1", "ldap_salted_md5",
        "ldap_salted_sha1", "ldap_hex_md5", "ldap_hex_sha1", "mysql323", "mysql41", "postgres_md5", "oracle10",
        "nthash", "lmhash", "msdcc", "msdcc2", "cisco_pix", "cisco_asa", "cisco_type7", "unix_disabled",
    }
)  # fmt: skip
_MIN_BCRYPT_ROUNDS = 10
_MIN_NAMED_SECRET = 8


def _called(node: ast.Call, name: str) -> bool:
    func = node.func
    return (isinstance(func, ast.Name) and func.id == name) or (isinstance(func, ast.Attribute) and func.attr == name)


def _keyword(node: ast.Call, name: str) -> ast.expr | None:
    return next((k.value for k in node.keywords if k.arg == name), None)


def _strings(node: ast.expr | None) -> list[str]:
    if not isinstance(node, ast.List | ast.Tuple):
        return []
    return [e.value for e in node.elts if isinstance(e, ast.Constant) and isinstance(e.value, str)]


def _int(node: ast.expr | None) -> int | None:
    if isinstance(node, ast.Constant) and type(node.value) is int:
        return node.value
    return None


def _calls(inputs: Inputs) -> Iterator[tuple[str, ast.Call]]:
    for module in source_modules(inputs):
        where = source_file(module)
        for node in ast.walk(module.tree):
            if isinstance(node, ast.Call):
                yield f"{where}:{node.lineno}", node


def _contexts(test: Callable[[ast.Call], bool], message: str) -> Callable[[Inputs], list[Violation]]:
    def check(inputs: Inputs) -> list[Violation]:
        found = [(at, node) for at, node in _calls(inputs) if _called(node, "CryptContext") and test(node)]
        return [Violation(at, f"{at}: {message}") for at, _ in found]

    return check


def _default_scheme(node: ast.Call) -> str | None:
    default = _keyword(node, "default")
    if isinstance(default, ast.Constant) and isinstance(default.value, str):
        return default.value
    schemes = _strings(_keyword(node, "schemes"))
    return schemes[0] if schemes else None


def _cheap_bcrypt(inputs: Inputs) -> list[Violation]:
    found: list[Violation] = []
    for at, node in _calls(inputs):
        if _called(node, "CryptContext"):
            rounds = _int(_keyword(node, "bcrypt__rounds")) or _int(_keyword(node, "bcrypt__default_rounds"))
        elif _called(node, "gensalt"):
            rounds = _int(_keyword(node, "rounds")) or (_int(node.args[0]) if node.args else None)
        else:
            continue
        if rounds is not None and rounds < _MIN_BCRYPT_ROUNDS:
            found.append(Violation(at, f"{at}: bcrypt runs with fewer than {_MIN_BCRYPT_ROUNDS} rounds."))
    return found


def _target_names(node: ast.AST) -> list[str]:
    targets = node.targets if isinstance(node, ast.Assign) else [node.target] if isinstance(node, ast.AnnAssign) else []
    names = [t.id if isinstance(t, ast.Name) else t.attr if isinstance(t, ast.Attribute) else "" for t in targets]
    return [n for n in names if n]


def _literal_secrets(inputs: Inputs) -> list[Violation]:
    found: dict[str, Violation] = {}  # one finding per location
    for module in source_modules(inputs):
        where = source_file(module)
        for node in ast.walk(module.tree):
            value = getattr(node, "value", None)
            if isinstance(node, ast.Assign | ast.AnnAssign) and isinstance(value, ast.Constant):
                literal = value.value
                for name in _target_names(node):
                    if isinstance(literal, str) and len(literal) >= _MIN_NAMED_SECRET and is_sensitive_key(name):
                        at = f"{where}:{value.lineno}"
                        found.setdefault(at, Violation(at, f"{at} assigns a literal to the secret-like name {name}."))
            elif isinstance(node, ast.Constant) and isinstance(node.value, str) and is_secret_value(node.value):
                at = f"{where}:{node.lineno}"
                found.setdefault(at, Violation(at, f"{at} holds a literal the secret detectors flag."))
    return sorted(found.values(), key=lambda v: (v.target.rpartition(":")[0], int(v.target.rpartition(":")[2])))


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
        _contexts(
            lambda n: bool(_PLAINTEXT.intersection(_strings(_keyword(n, "schemes")))),
            "a CryptContext lists a plaintext scheme.",
        ),
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
        _contexts(lambda n: _default_scheme(n) in _LEGACY, "a CryptContext hashes new passwords with a legacy scheme."),
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
        _cheap_bcrypt,
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
        _literal_secrets,
        needs_source=True,
    ),
)
