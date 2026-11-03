"""The advisor registry (0.3.0 spec §5.4): a static tuple, so ownership never depends on import order."""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass

from sharpit.engine.collectors.restapi.rules import RULE_IDS
from sharpit.engine.panels04 import module_implemented

# the vulnerability shape is exactly what dismissals.rule_id() builds from a PEP 503 name
_VULNERABILITY_KEY = r"[A-Za-z0-9._:-]+::pypi:[a-z0-9._-]+"
_VULNERABILITY = re.compile(_VULNERABILITY_KEY)
_DIGEST = r":[0-9a-f]{16}"


@dataclass(frozen=True)
class AdvisorSpec:
    id: str
    panel: str | None
    owns: Callable[[str], bool]
    fingerprint: re.Pattern[str] | None  # ``<advisor>:<a rule id it owns>:<16 hex>``; None: no finding fingerprints
    assess: str | None = None  # module whose ``assess(model, masker, ...)`` the pytest plugin runs; None: none

    @property
    def implemented(self) -> bool:
        """A 0.4 advisor reads its panel flag at call time; the others are always implemented."""
        return module_implemented(self.id)


def _fingerprint(advisor: str, rule: str) -> re.Pattern[str]:
    return re.compile(f"{re.escape(advisor)}:{rule}{_DIGEST}")


_RAPI_RULES = "|".join(sorted(map(re.escape, RULE_IDS)))


def _prefixed(advisor: str, *prefixes: str) -> AdvisorSpec:
    """A 0.5.0 advisor: owns every ``<PREFIX>-...`` rule id; its flag gates it (``implemented``)."""
    rule = f"(?:{'|'.join(prefixes)})-[A-Z0-9][A-Z0-9-]*"
    pattern = re.compile(rule)
    return AdvisorSpec(
        advisor,
        advisor,
        lambda value: pattern.fullmatch(value) is not None,
        fingerprint=_fingerprint(advisor, rule),
        assess=f"sharpit.engine.collectors.{advisor.replace('-', '_')}.service",
    )


ADVISORS: tuple[AdvisorSpec, ...] = (
    AdvisorSpec(
        "rest-api",
        "rest-api",
        RULE_IDS.__contains__,
        fingerprint=_fingerprint("rest-api", f"(?:{_RAPI_RULES})"),
        assess="sharpit.engine.collectors.restapi.service",
    ),
    AdvisorSpec(
        "vulnerabilities",
        "vulnerabilities",
        lambda value: _VULNERABILITY.fullmatch(value) is not None,
        fingerprint=None,  # nothing builds vulnerability fingerprints; dismissals use the bare rule id
    ),
    AdvisorSpec(
        "test-runtime",
        None,
        lambda value: value.startswith("sharpit."),
        fingerprint=_fingerprint("test-runtime", r"sharpit\.[a-z0-9.-]+"),
    ),
    _prefixed("database-advisor", "DB"),
    _prefixed("security", "SEC"),
    _prefixed("architecture", "ARCH"),
    _prefixed("fastapi", "FASTAPI", "SPRING"),
)


def advisor_for(id: str) -> AdvisorSpec | None:  # noqa: A002 - the spec names this parameter `id`
    """The advisor that owns a rule id or finding fingerprint, else None.

    A fingerprint prefix decides first and is then validated whole, so ``test-runtime:...::pypi:...`` is never read as
    a vulnerability id; only a value no advisor prefixes is matched as a bare rule id."""
    for spec in ADVISORS:
        if spec.implemented and id.startswith(f"{spec.id}:"):
            return spec if spec.fingerprint and spec.fingerprint.fullmatch(id) else None
    return next((spec for spec in ADVISORS if spec.implemented and spec.owns(id)), None)
