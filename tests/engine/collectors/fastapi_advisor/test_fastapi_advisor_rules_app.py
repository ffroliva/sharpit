"""Application rules (WAVE-B §7: FAPI-EVT-001, broad except, SPRING-WEB-004, SPRING-CONFIG-004) and secret safety."""

from __future__ import annotations

import json
from pathlib import Path

from fastapi import FastAPI
from sharpit.engine.advisors.dismissals import DismissalStore
from sharpit.engine.collectors.fastapi_advisor.report import FastapiAdvisor
from sharpit.engine.masking import Exposure, Masker
from sharpit.engine.singleflight import SingleFlight

from .support import messages, run_rules

APP = """
import logging

log = logging.getLogger(__name__)


class _App:
    def on_event(self, name):
        return lambda fn: fn


app = _App()


@app.on_event("startup")
def boot():
    pass


def swallow():
    try:
        return {"x": 1}
    except Exception:
        return None


def logged():
    try:
        return {"x": 1}
    except Exception:
        log.exception("failed")
        return None
"""


def test_on_event_instead_of_lifespan(tmp_path: Path) -> None:
    found = messages(run_rules(tmp_path, APP, {}), "FASTAPI-EVT-001")
    assert len(found) == 1
    assert "on_event" in found[0]


def test_broad_except_in_handler(tmp_path: Path) -> None:
    found = messages(run_rules(tmp_path, APP, {"GET /swallow": "swallow", "GET /logged": "logged"}), "FASTAPI-EXC-001")
    assert len(found) == 1
    assert "GET /swallow" in found[0]


def test_debug_mode_flagged(tmp_path: Path) -> None:
    on = messages(run_rules(tmp_path, "X = 1\n", {}, app=FastAPI(title="shop", debug=True)), "SPRING-WEB-004")
    off = messages(run_rules(tmp_path, "X = 1\n", {}, app=FastAPI(title="shop")), "SPRING-WEB-004")
    assert len(on) == 1
    assert off == []


def test_default_title_flagged(tmp_path: Path) -> None:
    default = messages(run_rules(tmp_path, "X = 1\n", {}, app=FastAPI()), "SPRING-CONFIG-004")
    named = messages(run_rules(tmp_path, "X = 1\n", {}, app=FastAPI(title="shop")), "SPRING-CONFIG-004")
    assert len(default) == 1
    assert named == []


SECRET = "s3cr3t-" + "sharpit-violation-value"
LEAKY = f"""
import time


class BaseModel:
    pass


class Settings(BaseModel):
    class Config:
        secret_key = "{SECRET}"


async def wait():
    token = "{SECRET}"
    time.sleep(1)
    return token


def fetch():
    try:
        return requests.get("https://example.invalid", headers={{"Authorization": "{SECRET}"}})
    except Exception:
        return "{SECRET}"
"""


def test_violation_never_contains_literal_secret(tmp_path: Path) -> None:
    evaluation = run_rules(tmp_path, LEAKY, {"GET /wait": "wait", "GET /fetch": "fetch"})
    advisor = FastapiAdvisor(
        lambda _request: evaluation,
        DismissalStore(tmp_path / "state"),
        Masker(Exposure.MASKED, True),
        SingleFlight(),
        max_retained=10000,
    )
    report = advisor.scan()
    flagged = {r["id"] for r in report["results"]}
    assert "FASTAPI-ASYNC-002" in flagged
    assert "FASTAPI-PYD-001" in flagged
    assert "FASTAPI-HTTP-001" in flagged
    assert "FASTAPI-EXC-001" in flagged
    scan_id = report["violationDetails"]["scanId"]
    pages = [advisor.violations(rule, scan_id, 0, 100) for rule in sorted(flagged)]
    assert SECRET not in json.dumps(report)
    assert SECRET not in json.dumps(pages)
