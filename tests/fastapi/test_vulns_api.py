"""Vulnerabilities and dismissed-rules endpoints (port of BootUI ``VulnerabilitiesController`` and
``DismissedRulesController`` wiring). The service is seeded through ``ctx.lazy`` with an OSV/EPSS opener that never
opens a socket."""

import io
import json
import threading
import urllib.request
from pathlib import Path
from typing import Any
from urllib.parse import quote

from fastapi.testclient import TestClient

from conftest import SideEffectGuard
from fastapi import FastAPI
from sharpit import install
from sharpit.engine.collectors.vulns.dismissals import FILE_NAME, DismissalStore
from sharpit.engine.collectors.vulns.epss import EpssClient
from sharpit.engine.collectors.vulns.inventory import Package
from sharpit.engine.collectors.vulns.osv import OsvClient
from sharpit.engine.collectors.vulns.service import OPERATION, VulnerabilityService

LOCAL = ("127.0.0.1", 50000)
PKG = Package("widget", "1.0.0", None)
RULE = "V-1::pypi:widget"
ADVISORY = {
    "id": "V-1",
    "database_specific": {"severity": "HIGH"},
    "affected": [{"package": {"ecosystem": "PyPI", "name": "widget"}, "versions": ["1.0.0"]}],
}


class _Response(io.BytesIO):
    status = 200


class Opener:
    """OSV querybatch -> V-1 for every package, V-1 detail, no EPSS data; optionally blocks until ``release``."""

    def __init__(self) -> None:
        self.release: threading.Event | None = None
        self.calls = 0

    def open(self, request: urllib.request.Request, data: Any = None, timeout: float | None = None) -> _Response:
        self.calls += 1
        if request.full_url.endswith("/v1/querybatch"):
            if self.release is not None:
                self.release.wait(2.0)
            count = len(json.loads(request.data)["queries"])  # type: ignore[arg-type]
            return _Response(json.dumps({"results": [{"vulns": [{"id": "V-1"}]}] * count}).encode())
        if request.full_url.endswith("/v1/vulns/V-1"):
            return _Response(json.dumps(ADVISORY).encode())
        return _Response(b'{"data": []}')


def _client(state_dir: Path, opener: Opener | None = None, **options: Any) -> TestClient:
    app = FastAPI()
    handle = install(app, **{"enabled": "ON", "show_banner": False, "state_dir": str(state_dir), **options})
    ctx = handle.context
    fake = opener or Opener()
    service = VulnerabilityService(
        ctx.settings,
        OsvClient("http://osv.test", 2.0, fake),
        EpssClient("http://epss.test", 2.0, fake),
        lambda: [PKG],
        DismissalStore(state_dir),
        ctx.single_flight,
    )
    assert ctx.lazy("vulnerabilities", lambda: service) is service
    return TestClient(app, base_url="http://localhost", client=LOCAL, follow_redirects=False)


def test_get_report_not_scanned_without_network(no_side_effects: SideEffectGuard, tmp_state_dir: Path):
    no_side_effects.unblock_network()  # the Windows Proactor loop TestClient starts connects a self-pipe socketpair
    opener = Opener()
    resp = _client(tmp_state_dir, opener).get("/sharpit/api/vulnerabilities")
    assert resp.status_code == 200
    assert resp.headers["cache-control"] == "no-store, must-revalidate"
    assert resp.json()["scan"]["status"] == "NOT_SCANNED"
    assert opener.calls == 0


def test_scan_then_get_returns_cached(tmp_state_dir: Path):
    client = _client(tmp_state_dir)
    scanned = client.post("/sharpit/api/vulnerabilities/scan")
    assert scanned.status_code == 200
    assert scanned.json()["scan"]["status"] == "SCANNED"
    assert client.get("/sharpit/api/vulnerabilities").json() == scanned.json()


def test_concurrent_scan_409(tmp_state_dir: Path):
    opener = Opener()
    opener.release = threading.Event()
    client = _client(tmp_state_dir, opener)
    first = threading.Thread(target=client.post, args=("/sharpit/api/vulnerabilities/scan",))
    first.start()
    try:
        for _ in range(200):  # wait until the first scan holds the single-flight lock
            if opener.calls:
                break
            threading.Event().wait(0.01)
        busy = client.post("/sharpit/api/vulnerabilities/scan")
    finally:
        opener.release.set()
        first.join(5.0)
    assert not first.is_alive()
    assert busy.status_code == 409
    assert busy.json() == {
        "error": "sharpit action already in progress",
        "operation": OPERATION,
        "activeOperation": OPERATION,
        "message": f"Operation '{OPERATION}' cannot start while '{OPERATION}' is in progress.",
    }
    assert client.post("/sharpit/api/vulnerabilities/scan").status_code == 200  # lock released


def test_dismiss_and_restore_through_the_api(tmp_state_dir: Path):
    client = _client(tmp_state_dir)
    client.post("/sharpit/api/vulnerabilities/scan")
    assert client.get("/sharpit/api/dismissed-rules").json() == {"dismissed": []}
    assert not (tmp_state_dir / FILE_NAME).exists()

    added = client.post(f"/sharpit/api/dismissed-rules/{quote(RULE, safe='')}")
    assert (added.status_code, added.json()) == (200, {"dismissed": [RULE]})
    report = client.get("/sharpit/api/vulnerabilities").json()
    assert report["dependencies"][0]["vulnerabilities"][0]["dismissed"] is True
    assert report["vulnerable"] == 0

    restored = client.delete(f"/sharpit/api/dismissed-rules/{quote(RULE, safe='')}")
    assert (restored.status_code, restored.json()) == (200, {"dismissed": []})
    assert client.get("/sharpit/api/vulnerabilities").json()["vulnerable"] == 1


def test_dismiss_rejects_bad_ids_400(tmp_state_dir: Path):
    client = _client(tmp_state_dir)
    client.post(f"/sharpit/api/dismissed-rules/{quote(RULE, safe='')}")
    before = (tmp_state_dir / FILE_NAME).read_bytes()
    for bad in ['V-1"::pypi:widget', "V-1\\x::pypi:widget", "V-1::widget", "V-1::pypi:Widget"]:
        for method in ("POST", "DELETE"):
            resp = client.request(method, f"/sharpit/api/dismissed-rules/{quote(bad, safe='')}")
            assert resp.status_code == 400, (method, bad)
            assert "error" in resp.json()
    # a newline never matches Starlette's ``.*`` path regexes: 404 before any handler runs (store rejects it too)
    newline = quote("V-1\n::pypi:widget", safe="")
    assert client.post(f"/sharpit/api/dismissed-rules/{newline}").status_code == 404
    assert (tmp_state_dir / FILE_NAME).read_bytes() == before


def test_dismissals_global_read_only_403(tmp_state_dir: Path):
    client = _client(tmp_state_dir, read_only=True)
    assert client.get("/sharpit/api/dismissed-rules").status_code == 200
    for method in ("POST", "DELETE"):
        resp = client.request(method, f"/sharpit/api/dismissed-rules/{quote(RULE, safe='')}")
        assert resp.status_code == 403
        assert resp.json() == {
            "error": "sharpit panel access denied",
            "panel": "dismissed-rules",
            "reason": "sharpit is read-only via SHARPIT_READ_ONLY=true",
        }
    assert not (tmp_state_dir / FILE_NAME).exists()


def test_vulnerabilities_read_only_panel_blocks_scan(tmp_state_dir: Path):
    opener = Opener()
    client = _client(tmp_state_dir, opener, panels={"vulnerabilities": {"read_only": True}})
    assert client.get("/sharpit/api/vulnerabilities").status_code == 200
    resp = client.post("/sharpit/api/vulnerabilities/scan")
    assert resp.status_code == 403
    assert resp.json() == {
        "error": "sharpit panel access denied",
        "panel": "vulnerabilities",
        "reason": "Panel is read-only via SHARPIT_PANELS_VULNERABILITIES_READ_ONLY=true",
    }
    assert opener.calls == 0
    # the panel flag does not cover dismissed-rules (not a panel), only global read-only does
    assert client.post(f"/sharpit/api/dismissed-rules/{quote(RULE, safe='')}").status_code == 200


def test_default_service_never_networks_on_get(no_side_effects: SideEffectGuard, tmp_path: Path):
    no_side_effects.unblock_network()
    app = FastAPI()
    install(app, enabled="ON", show_banner=False, state_dir=str(tmp_path / "state"))
    client = TestClient(app, base_url="http://localhost", client=LOCAL)
    resp = client.get("/sharpit/api/vulnerabilities")
    assert resp.status_code == 200
    body = resp.json()
    assert body["scan"]["status"] == "NOT_SCANNED"
    assert body["total"] > 0 and body["dependencies"][0]["source"] == "importlib.metadata"
    assert client.get("/sharpit/api/dismissed-rules").json() == {"dismissed": []}
    assert not (tmp_path / "state").exists()
