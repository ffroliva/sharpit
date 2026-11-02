"""F-rest round 1: lane safety rows feed the shared sweeps, load like any test module and are validated."""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import BaseRoute, Route

import safety
from fastapi import FastAPI
from sharpit import install
from sharpit.engine import panels04
from sharpit.fastapi.routes import data as data_routes

EXEMPT = ("/api/auth/session", "/api/mcp", "/api/cli/", "/api/dismissed-rules/")
DATA_LANE = 'PANEL = "data"\nWRITE_ROWS = [("POST", "/sharpit/api/data/probe")]\n'


@pytest.fixture
def lane_pkg(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[str, Path]:
    """A throwaway package standing in for ``tests/safety`` (unique name: modules are cached in sys.modules)."""
    name = f"lanepkg_{uuid.uuid4().hex[:8]}"
    package = tmp_path / name
    package.mkdir()
    (package / "__init__.py").write_text("", encoding="utf-8")
    monkeypatch.syspath_prepend(str(tmp_path))
    return name, package


def _plant_data_post(monkeypatch: pytest.MonkeyPatch) -> None:
    def probe(request: Request) -> JSONResponse:
        return JSONResponse({"written": True})

    def build_routes(ctx: Any, host_app: Any) -> list[BaseRoute]:
        api = ctx.settings.api_path[len(ctx.settings.path) :]
        return [Route(f"{api}/data/probe", probe, methods=["POST"])]

    monkeypatch.setattr(data_routes, "build_routes", build_routes)
    monkeypatch.setitem(panels04.IMPLEMENTED, "data", True)


def _installed(**options: Any) -> FastAPI:
    app = FastAPI()
    install(app, enabled="ON", show_banner=False, **options)
    return app


def test_lane_write_row_reaches_the_read_only_sweep(
    lane_pkg: tuple[str, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    name, package = lane_pkg
    (package / "test_a_data_safety.py").write_text(DATA_LANE, encoding="utf-8")
    _plant_data_post(monkeypatch)

    cases = safety.write_cases([], safety.load(name), {})
    assert ("data", "POST", "/sharpit/api/data/probe", None) in cases

    # data is not action-capable, so read-only does not gate this POST: the sweep's 403 expectation catches it
    client = TestClient(_installed(read_only=True), base_url="http://localhost", client=("127.0.0.1", 50000))
    assert client.post("/sharpit/api/data/probe").status_code == 200


def test_lane_rows_cover_the_live_write_table(lane_pkg: tuple[str, Path], monkeypatch: pytest.MonkeyPatch) -> None:
    name, package = lane_pkg
    base = safety.live_write_routes(_installed(), EXEMPT)
    (package / "test_a_data_safety.py").write_text(DATA_LANE, encoding="utf-8")
    _plant_data_post(monkeypatch)

    uncovered = safety.live_write_routes(_installed(), EXEMPT) - base - safety.write_rows(safety.load(name))

    assert uncovered == set()


def test_lane_file_loads_as_a_package_module(lane_pkg: tuple[str, Path], monkeypatch: pytest.MonkeyPatch) -> None:
    name, package = lane_pkg
    (package / "_shared.py").write_text('ROWS = [("POST", "/sharpit/api/data/probe")]\n', encoding="utf-8")
    (package / "test_a_data_safety.py").write_text(
        "from dataclasses import dataclass\n\nfrom ._shared import ROWS\n\n\n"
        "@dataclass\nclass Case:\n    name: str\n\n\n"
        'PANEL = "data"\nWRITE_ROWS = ROWS\n',
        encoding="utf-8",
    )
    monkeypatch.setitem(panels04.IMPLEMENTED, "data", True)

    lanes = safety.load(name)

    assert lanes.unimportable == ()
    assert safety.write_rows(lanes) == {("POST", "/sharpit/api/data/probe")}


def test_lane_file_that_skips_or_fails_is_reported_not_raised(lane_pkg: tuple[str, Path]) -> None:
    name, package = lane_pkg
    (package / "test_a_skip_safety.py").write_text(
        'import pytest\n\npytest.importorskip("sharpit_no_such_module")\n', encoding="utf-8"
    )
    (package / "test_b_broken_safety.py").write_text("import sharpit_no_such_module_either\n", encoding="utf-8")

    try:
        lanes = safety.load(name)
        raised: str | None = None
    except BaseException as exc:  # noqa: BLE001 - a Skipped here would skip the shared route-table tests
        lanes, raised = safety.Lanes((), (), (), {}), repr(exc)

    assert raised is None
    assert [line.split(":")[0] for line in lanes.unimportable] == ["test_a_skip_safety.py", "test_b_broken_safety.py"]


def test_panel_is_optional_but_must_be_a_known_id(lane_pkg: tuple[str, Path], monkeypatch: pytest.MonkeyPatch) -> None:
    name, package = lane_pkg
    (package / "test_d1_safety.py").write_text('GET_ROWS = ["/sharpit/api/rest-api"]\n', encoding="utf-8")
    (package / "test_x_safety.py").write_text('PANEL = "nope"\nGET_ROWS = ["/sharpit/api/nope"]\n', encoding="utf-8")
    monkeypatch.setitem(panels04.IMPLEMENTED, "data", True)

    lanes = safety.load(name)

    assert lanes.implemented == ()
    assert [line.split(":")[0] for line in lanes.invalid] == ["test_x_safety.py"]


def test_row_shapes_are_validated_and_convertors_stripped(
    lane_pkg: tuple[str, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    name, package = lane_pkg
    (package / "test_a_good_safety.py").write_text(
        'PANEL = "data"\nGET_ROWS = ["/sharpit/api/data/{name:path}"]\nPATH_PARAMS = {"name": "orders"}\n',
        encoding="utf-8",
    )
    (package / "test_b_bad_safety.py").write_text(
        'PANEL = "transactions"\nGET_ROWS = "/sharpit/api/transactions"\nWRITE_ROWS = [("POST",)]\n', encoding="utf-8"
    )
    monkeypatch.setitem(panels04.IMPLEMENTED, "data", True)
    monkeypatch.setitem(panels04.IMPLEMENTED, "transactions", True)

    lanes = safety.load(name)

    assert [lane.gets for lane in lanes.implemented] == [("/sharpit/api/data/{name}",)]
    assert [line.split(":")[0] for line in lanes.invalid] == ["test_b_bad_safety.py", "test_b_bad_safety.py"]
    assert safety.get_rows(lanes, {**lanes.params}) == {"/sharpit/api/data/orders"}


def test_matrix_feeds_lane_rows_into_its_sweeps(lane_pkg: tuple[str, Path], monkeypatch: pytest.MonkeyPatch) -> None:
    # the real matrix wiring: dropping the lane rows from its table or its sweeps fails here
    import test_safety_matrix as matrix

    expected_writes = safety.write_cases(matrix.WRITES, matrix.LANES, matrix.PATH_PARAMS)
    assert expected_writes == matrix.ALL_WRITES
    name, package = lane_pkg
    (package / "test_a_data_safety.py").write_text(DATA_LANE, encoding="utf-8")
    _plant_data_post(monkeypatch)

    real = matrix.LANES  # lanes already implemented on this branch keep their rows
    planted = safety.load(name)
    monkeypatch.setattr(
        matrix,
        "LANES",
        safety.Lanes(
            real.implemented + planted.implemented,
            real.invalid + planted.invalid,
            real.unimportable + planted.unimportable,
            {**real.params, **planted.params},
        ),
    )
    matrix.test_write_route_table_is_complete()  # covered by the lane row

    monkeypatch.setattr(matrix, "LANES", real)  # the planted lane's rows dropped
    with pytest.raises(AssertionError, match="data/probe"):
        matrix.test_write_route_table_is_complete()  # the undocumented route is named


def test_lane_path_params_apply_only_to_that_lanes_rows(
    lane_pkg: tuple[str, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    name, package = lane_pkg
    (package / "test_a_data_safety.py").write_text(
        'PANEL = "data"\nGET_ROWS = ["/sharpit/api/data/{name}"]\nPATH_PARAMS = {"name": "x"}\n', encoding="utf-8"
    )
    monkeypatch.setitem(panels04.IMPLEMENTED, "data", True)
    lanes = safety.load(name)
    base_format = "/sharpit/api/database-connection-pools/pools/{name}/snapshot"
    base_samples = {"name": "nope"}

    base_path = base_format.format(**safety.sample_params(base_format, lanes, base_samples))
    lane_path = "/sharpit/api/data/{name}".format(
        **safety.sample_params("/sharpit/api/data/{name}", lanes, base_samples)
    )

    assert base_path == "/sharpit/api/database-connection-pools/pools/nope/snapshot"
    assert lane_path == "/sharpit/api/data/x"
