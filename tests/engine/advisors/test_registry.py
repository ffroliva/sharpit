"""The advisor registry (0.3.0 spec §5.4)."""

import subprocess
import sys
from pathlib import Path

import pytest

from sharpit.engine.advisors.dismissals import BadRequest, DismissalStore, owning_panel
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
    assert {k: v.panel for k, v in by_id.items()} == {
        "rest-api": "rest-api",
        "vulnerabilities": "vulnerabilities",
        "test-runtime": None,
    }


@pytest.mark.parametrize(
    ("advisor", "rule"),
    [("rest-api", "RAPI-MAP-001"), ("test-runtime", "sharpit.n-plus-one")],
)
def test_registry_owns_fingerprints_by_prefix(advisor: str, rule: str):
    assert _owner(_FP.format(advisor=advisor, rule=rule)) == advisor


def test_test_runtime_prefix_wins_over_vulnerability_shape(tmp_path: Path):
    fingerprint = "test-runtime:sharpit.x::pypi:y"
    assert _owner(fingerprint) != "vulnerabilities"
    assert owning_panel(fingerprint) is None
    with pytest.raises(BadRequest):
        DismissalStore(tmp_path).add(fingerprint)  # refused, not filed under the vulnerabilities panel


def test_fingerprint_with_unknown_rule_is_refused():
    assert advisor_for("rest-api:RAPI-NOPE:0123456789abcdef") is None


@pytest.mark.parametrize("digest", ["zz", "0123456789abcde", "0123456789abcdef0", "0123456789ABCDEF"])
def test_fingerprint_needs_16_hex(digest: str):
    assert advisor_for(f"rest-api:RAPI-MAP-001:{digest}") is None


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


def test_vulnerability_fingerprint_is_refused():
    assert advisor_for("vulnerabilities:GHSA-1::pypi:jinja2:0123456789abcdef") is None
