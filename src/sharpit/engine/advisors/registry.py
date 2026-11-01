"""The advisor registry (0.3.0 spec §5.4): a static tuple, so ownership never depends on import order."""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass

from sharpit.engine.collectors.restapi.rules import RULE_IDS

# the vulnerability shape is exactly what dismissals.rule_id() builds from a PEP 503 name
_VULNERABILITY_KEY = r"[A-Za-z0-9._:-]+::pypi:[a-z0-9._-]+"
_VULNERABILITY = re.compile(_VULNERABILITY_KEY)
_DIGEST = r":[0-9a-f]{16}"


@dataclass(frozen=True)
class AdvisorSpec:
    id: str
    panel: str | None
    owns: Callable[[str], bool]
    offline: bool
    fingerprint: re.Pattern[str]  # the exact fingerprint shape ``<advisor>:<a rule id it owns>:<16 hex>``


def _fingerprint(advisor: str, rule: str) -> re.Pattern[str]:
    return re.compile(f"{re.escape(advisor)}:{rule}{_DIGEST}")


_RAPI_RULES = "|".join(sorted(map(re.escape, RULE_IDS)))

ADVISORS: tuple[AdvisorSpec, ...] = (
    AdvisorSpec(
        "rest-api",
        "rest-api",
        RULE_IDS.__contains__,
        offline=True,
        fingerprint=_fingerprint("rest-api", f"(?:{_RAPI_RULES})"),
    ),
    AdvisorSpec(
        "vulnerabilities",
        "vulnerabilities",
        lambda value: _VULNERABILITY.fullmatch(value) is not None,
        offline=False,
        fingerprint=_fingerprint("vulnerabilities", _VULNERABILITY_KEY),
    ),
    AdvisorSpec(
        "test-runtime",
        None,
        lambda value: value.startswith("sharpit."),
        offline=True,
        fingerprint=_fingerprint("test-runtime", r"sharpit\.[a-z0-9.-]+"),
    ),
)


def advisor_for(id: str) -> AdvisorSpec | None:  # noqa: A002 - the spec names this parameter `id`
    """The advisor that owns a rule id or finding fingerprint, else None.

    A fingerprint prefix decides first and is then validated whole, so ``test-runtime:...::pypi:...`` is never read as
    a vulnerability id; only a value no advisor prefixes is matched as a bare rule id."""
    for spec in ADVISORS:
        if id.startswith(f"{spec.id}:"):
            return spec if spec.fingerprint.fullmatch(id) else None
    return next((spec for spec in ADVISORS if spec.owns(id)), None)
