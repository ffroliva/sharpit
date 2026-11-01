"""The advisor registry (0.3.0 spec §5.4): a static tuple, so ownership never depends on import order."""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass

from sharpit.engine.collectors.restapi.rules import RULE_IDS

# the vulnerability shape is exactly what dismissals.rule_id() builds from a PEP 503 name
_VULNERABILITY = re.compile(r"[A-Za-z0-9._:-]+::pypi:[a-z0-9._-]+")


@dataclass(frozen=True)
class AdvisorSpec:
    id: str
    panel: str | None
    owns: Callable[[str], bool]
    offline: bool


def _owns(advisor: str, exact: Callable[[str], bool]) -> Callable[[str], bool]:
    """Owns the advisor's fingerprints (``<advisor>:`` prefix) and the rule ids ``exact`` accepts."""
    prefix = f"{advisor}:"
    return lambda value: value.startswith(prefix) or exact(value)


ADVISORS: tuple[AdvisorSpec, ...] = (
    AdvisorSpec("rest-api", "rest-api", _owns("rest-api", RULE_IDS.__contains__), offline=True),
    AdvisorSpec(
        "vulnerabilities",
        "vulnerabilities",
        _owns("vulnerabilities", lambda value: _VULNERABILITY.fullmatch(value) is not None),
        offline=False,
    ),
    AdvisorSpec("test-runtime", None, _owns("test-runtime", lambda value: value.startswith("sharpit.")), offline=True),
)


def advisor_for(id: str) -> AdvisorSpec | None:  # noqa: A002 - the spec names this parameter `id`
    """The advisor that owns a rule id or finding fingerprint, else None."""
    return next((spec for spec in ADVISORS if spec.owns(id)), None)
