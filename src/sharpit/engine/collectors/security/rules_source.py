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


def _first_int(*nodes: ast.expr | None) -> int | None:
    """The first integer literal; ``0`` counts (an ``or`` chain would skip it)."""
    return next((value for value in map(_int, nodes) if value is not None), None)


def _cheap_bcrypt(inputs: Inputs) -> list[Violation]:
    found: list[Violation] = []
    for at, node in _calls(inputs):
        if _called(node, "CryptContext"):
            rounds = _first_int(_keyword(node, "bcrypt__rounds"), _keyword(node, "bcrypt__default_rounds"))
        elif _called(node, "gensalt"):
            rounds = _first_int(_keyword(node, "rounds"), node.args[0] if node.args else None)
        else:
            continue
        if rounds is not None and rounds < _MIN_BCRYPT_ROUNDS:
            found.append(Violation(at, f"{at}: bcrypt runs with fewer than {_MIN_BCRYPT_ROUNDS} rounds."))
    return found


def _target_names(node: ast.AST) -> list[str]:
    targets: list[ast.expr] = []
    if isinstance(node, ast.Assign):
        targets = node.targets
    elif isinstance(node, ast.AnnAssign):
        targets = [node.target]
    names = [t.id if isinstance(t, ast.Name) else t.attr if isinstance(t, ast.Attribute) else "" for t in targets]
    return [n for n in names if n]


def _field_default(value: ast.expr | None) -> ast.expr | None:
    """``Field(default=...)`` / ``Field(...)``'s default; any other value as is."""
    if isinstance(value, ast.Call) and _called(value, "Field"):
        return _keyword(value, "default") or (value.args[0] if value.args else None)
    return value


def _named_values(node: ast.AST) -> Iterator[tuple[str, ast.expr | None]]:
    """(name, value) bindings: assignments, keyword arguments, string dict keys and parameter defaults."""
    if isinstance(node, ast.Assign | ast.AnnAssign):
        yield from ((name, _field_default(node.value)) for name in _target_names(node))
    elif isinstance(node, ast.keyword) and node.arg is not None:
        yield node.arg, node.value
    elif isinstance(node, ast.Dict):
        yield from (
            (key.value, value)
            for key, value in zip(node.keys, node.values, strict=True)
            if isinstance(key, ast.Constant) and isinstance(key.value, str)
        )
    elif isinstance(node, ast.arguments):
        positional = [*node.posonlyargs, *node.args]
        yield from zip((a.arg for a in positional[len(positional) - len(node.defaults) :]), node.defaults, strict=True)
        yield from zip((a.arg for a in node.kwonlyargs), node.kw_defaults, strict=True)


def _node_secrets(node: ast.AST, where: str) -> Iterator[Violation]:
    for name, value in _named_values(node):
        if not (isinstance(value, ast.Constant) and isinstance(value.value, str)):
            continue
        if len(value.value) >= _MIN_NAMED_SECRET and is_sensitive_key(name):
            at = f"{where}:{value.lineno}"
            yield Violation(at, f"{at} assigns a literal to the secret-like name {name}.")
    if isinstance(node, ast.Constant) and isinstance(node.value, str) and is_secret_value(node.value):
        at = f"{where}:{node.lineno}"
        yield Violation(at, f"{at} holds a literal the secret detectors flag.")


def _literal_secrets(inputs: Inputs) -> list[Violation]:
    found: dict[str, Violation] = {}  # one finding per location
    for module in source_modules(inputs):
        where = source_file(module)
        for node in ast.walk(module.tree):
            for violation in _node_secrets(node, where):
                found.setdefault(violation.target, violation)
    return sorted(found.values(), key=lambda v: (v.target.rpartition(":")[0], int(v.target.rpartition(":")[2])))


def _jwt_audience(inputs: Inputs) -> list[Violation]:
    found: list[Violation] = []
    for at, node in _calls(inputs):
        if not _called(node, "decode") or not isinstance(node.func, ast.Attribute):
            continue
        if not isinstance(node.func.value, ast.Name) or node.func.value.id != "jwt":
            continue
        options = _keyword(node, "options")
        disabled = isinstance(options, ast.Dict) and any(
            isinstance(key, ast.Constant)
            and key.value == "verify_aud"
            and isinstance(value, ast.Constant)
            and value.value is False
            for key, value in zip(options.keys, options.values, strict=True)
        )
        if disabled or _keyword(node, "audience") is None:
            message = (
                "jwt.decode disables audience validation with verify_aud=False."
                if disabled
                else "Without audience=, PyJWT rejects tokens with aud, so the risk is tokens without an aud claim."
            )
            found.append(Violation(at, f"{at}: {message}"))
    return found


RULES: tuple[SecurityRule, ...] = (
    SecurityRule(
        rule(
            "SEC-OAUTH-002",
            "Validate the JWT audience claim",
            "OAuth2 / JWT",
            "INFO",
            "Without audience=, PyJWT rejects tokens with aud, so the risk is tokens without an aud claim; "
            "verify_aud=False disables audience validation.",
            "Pass the expected audience to jwt.decode and leave verify_aud enabled.",
            "https://pyjwt.readthedocs.io/en/stable/api.html#jwt.decode",
        ),
        _jwt_audience,
        needs_source=True,
    ),
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
