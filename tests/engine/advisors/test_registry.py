"""The advisor registry (0.3.0 spec §5.4)."""

import subprocess
import sys

import pytest

from sharpit.engine.advisors.registry import ADVISORS, advisor_for
from sharpit.engine.collectors.restapi.rules import RULE_IDS

_FP = "{advisor}:{rule}:0123456789abcdef"


def _owner(rule: str) -> str | None:
    spec = advisor_for(rule)
    return spec.id if spec else None


def test_registry_owns_today_ids():
    assert {_owner(rule) for rule in RULE_IDS} == {"rest-api"}
    assert _owner("GHSA-aaaa::pypi:jinja2") == "vulnerabilities"
    assert _owner("SPRING-WEB-001") is None
    assert _owner("RAPI-NOPE") is None  # an unported RAPI- id has no owner


def test_registry_specs():
    by_id = {a.id: a for a in ADVISORS}
    assert {k: (v.panel, v.offline) for k, v in by_id.items()} == {
        "rest-api": ("rest-api", True),
        "vulnerabilities": ("vulnerabilities", False),
        "test-runtime": (None, True),
    }


@pytest.mark.parametrize("advisor", ["rest-api", "vulnerabilities", "test-runtime"])
def test_registry_owns_fingerprints_by_prefix(advisor: str):
    assert _owner(_FP.format(advisor=advisor, rule="X-1")) == advisor


def test_registry_owns_sharpit_rule_ids_for_test_runtime():
    assert _owner("sharpit.n-plus-one") == "test-runtime"


def test_registry_unknown_prefix_is_unowned():
    assert _owner(_FP.format(advisor="nope", rule="X-1")) is None


def test_registry_is_static():
    """No import-order dependence: a process that imports only ``dismissals`` gets the same owners."""
    code = (
        "from sharpit.engine.advisors.dismissals import owning_panel as o;"
        "print(o('RAPI-MAP-001'), o('V-1::pypi:w'), o('test-runtime:sharpit.x:0123456789abcdef'))"
    )
    out = subprocess.run(  # noqa: S603 - fixed interpreter and code
        [sys.executable, "-c", code], capture_output=True, text=True, check=True
    )
    assert out.stdout.split() == ["rest-api", "vulnerabilities", "None"]
