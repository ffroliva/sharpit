"""The advisor scan core and the ``RuleResult`` contract (0.5.0 spec §4.3, §4.4, §5 post-scan parity)."""

import copy
import json
from pathlib import Path
from typing import Any

from golden import ROOT, assert_enum_values, assert_parity
from sharpit.engine.advisors.dismissals import DismissalStore
from sharpit.engine.collectors.restapi.service import RestApiService
from sharpit.engine.masking import Exposure, Masker
from sharpit.engine.singleflight import SingleFlight
from sharpit.engine.spi import ApiModel, ApiRouteInfo


class Pet:
    pass


def _rest_api_report(tmp_path: Path) -> dict[str, Any]:
    route = ApiRouteInfo(
        ("GET",), "/v1/get-pets", "app.pets:read_pets", summary="s", tags=("pets",), return_annotation=Pet
    )
    model = ApiModel((route,), ("app.errors:on_error",), ())
    service = RestApiService(
        lambda: model, DismissalStore(tmp_path), Masker(Exposure.MASKED, True), SingleFlight(), max_retained=10000
    )
    return service.scan()


def _enum_error(sharpit_id: str, payload: dict[str, Any]) -> str:
    try:
        assert_enum_values(sharpit_id, "captured", payload)
    except AssertionError as exc:
        return str(exc)
    return ""


def test_enum_values_checked_against_golden():
    golden = json.loads((ROOT / "rest-api" / "captured.json").read_text(encoding="utf-8"))
    assert _enum_error("rest-api", golden) == ""
    wrong = copy.deepcopy(golden)
    wrong["results"][0]["status"] = "FAILED"
    assert "results[].status" in _enum_error("rest-api", wrong)


def test_advisor_core_matches_rest_api_post_scan_golden(tmp_path: Path):
    report = _rest_api_report(tmp_path)
    assert report["results"][0]["status"] == "VIOLATION"
    assert "sampleLocations" in report["results"][0]
    assert_parity("rest-api", "captured", report)
    assert_enum_values("rest-api", "captured", report)
