"""The data panel over HTTP and MCP: routes, guard, panel flag, no mapper configuration on a GET."""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from typing import Any

import httpx
import pytest

pytest.importorskip("sqlalchemy")
import sqlalchemy as sa  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy.orm import DeclarativeBase, mapped_column, relationship  # noqa: E402

from conftest import SideEffectGuard  # noqa: E402
from data_support import spy_on_configure  # noqa: E402
from fastapi import FastAPI  # noqa: E402
from golden import ROOT, assert_parity  # noqa: E402
from sharpit import install  # noqa: E402
from sharpit.engine.panels import PANELS, disabled_reason  # noqa: E402

pytestmark = pytest.mark.needs_sqlalchemy

LOCAL = ("127.0.0.1", 50000)
API = "/sharpit/api"
MCP = f"{API}/mcp"


def make_base() -> type[DeclarativeBase]:
    class Base(DeclarativeBase):
        pass

    owner = type(
        "Owner",
        (Base,),
        {
            "__module__": __name__,
            "__tablename__": "owners",
            "id": mapped_column(sa.Integer, primary_key=True),
            "pets": relationship("Pet"),
        },
    )
    pet = type(
        "Pet",
        (Base,),
        {
            "__module__": __name__,
            "__tablename__": "pets",
            "id": mapped_column(sa.Integer, primary_key=True),
            "owner_id": mapped_column(sa.ForeignKey("owners.id")),
        },
    )
    Base.held = [owner, pet]  # pyright: ignore[reportAttributeAccessIssue] - a registry holds classes weakly
    return Base


@pytest.fixture(scope="module")
def asgi_loop() -> Iterator[asyncio.AbstractEventLoop]:
    loop = asyncio.new_event_loop()  # made before the no_side_effects guard: a loop opens a self-pipe socket
    try:
        yield loop
    finally:
        loop.close()


@pytest.fixture
def base() -> type[DeclarativeBase]:
    return make_base()


def client_for(models: object, **options: Any) -> TestClient:
    app = FastAPI()
    install(app, enabled="ON", show_banner=False, config_scan=False, models=models, **options)
    return TestClient(app, base_url="http://localhost", client=LOCAL)


@pytest.fixture
def configure_spy(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    return spy_on_configure(monkeypatch)


def test_repositories_golden_parity(base: type[DeclarativeBase]) -> None:
    # ported: DataControllerTests.repositoriesReturnsSummaryForDiscoveredRepository
    response = client_for(base).get(f"{API}/data/repositories")

    assert response.status_code == 200
    folder = ROOT / "data"  # exactly what golden.assert_parity reads
    if not any(
        (folder / f).is_file()
        for f in ("repositories.captured.json", "captured.json", "repositories.provisional.json", "provisional.json")
    ):
        pytest.skip("golden fixture data/repositories.captured.json is G0a's; parity runs once it merges")
    assert_parity("data", "repositories", response.json())


def test_repositories_lists_the_models(base: type[DeclarativeBase]) -> None:
    response = client_for(base).get(f"{API}/data/repositories")

    assert response.status_code == 200
    assert response.json()["total"] == 2
    assert [row["beanName"] for row in response.json()["repositories"]] == ["Owner", "Pet"]


def test_detail_by_name(base: type[DeclarativeBase]) -> None:
    # ported: DataControllerTests.repositoryDetailLooksUpByFullyQualifiedInterfaceName
    response = client_for(base).get(f"{API}/data/repositories/{__name__}.Owner")

    assert response.status_code == 200
    assert response.json()["beanName"] == "Owner"


def test_detail_404_empty_body(base: type[DeclarativeBase]) -> None:
    # ported: DataControllerTests.repositoryDetailReturnsNotFoundForUnknownRepository
    response = client_for(base).get(f"{API}/data/repositories/Nope")

    assert response.status_code == 404
    assert response.content == b""


def test_get_never_configures_mappers(
    asgi_loop: asyncio.AbstractEventLoop,
    base: type[DeclarativeBase],
    configure_spy: list[str],
    no_side_effects: SideEffectGuard,
    request: pytest.FixtureRequest,
) -> None:
    # derived: spec §4 anti-goal, Review Focus 5: a GET never configures mappers or runs SQL
    statements: list[str] = []

    def record(*args: Any) -> None:
        statements.append(str(args[2]))

    sa.event.listen(sa.engine.Engine, "before_cursor_execute", record)
    request.addfinalizer(lambda: sa.event.remove(sa.engine.Engine, "before_cursor_execute", record))
    app = FastAPI()
    install(
        app,
        enabled="ON",
        show_banner=False,
        config_scan=False,
        models=base,
        state_dir=str(no_side_effects.state_dir),
    )

    async def fetch() -> list[httpx.Response]:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://localhost") as client:
            return [await client.get(f"{API}/data/repositories"), await client.get(f"{API}/data/repositories/Owner")]

    listing, detail = asgi_loop.run_until_complete(fetch())

    assert listing.status_code == 200
    assert detail.status_code == 200
    assert configure_spy == []
    assert statements == []
    assert listing.json()["total"] == 2
    assert listing.json()["repositories"][0]["relationships"] is None


def test_panel_disabled_403(base: type[DeclarativeBase]) -> None:
    # derived: spec §6.3, a disabled panel answers the guard's 403
    response = client_for(base, panels={"data": {"enabled": False}}).get(f"{API}/data/repositories")

    assert response.status_code == 403
    assert response.json() == {
        "error": "sharpit panel access denied",
        "panel": "data",
        "reason": disabled_reason("data"),
    }


def test_panel_listed_when_implemented(base: type[DeclarativeBase]) -> None:
    panels = client_for(base).get(f"{API}/panels").json()["panels"]

    row = next((p for p in panels if p["id"] == "data"), None)
    assert row is not None
    assert row["readOnly"] is False
    assert next(p for p in PANELS if p.id == "data").action_capable is False


def test_mcp_lists_read_tool_only(base: type[DeclarativeBase]) -> None:
    client = client_for(base, mcp_enabled="ON")

    listed = client.post(MCP, json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"}).json()["result"]["tools"]
    call = {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "get_data_repositories"}}
    reply = client.post(MCP, json=call).json()

    assert "get_data_repositories" in {t["name"] for t in listed}
    assert {t["name"]: t["action"] for t in client.get(f"{API}/mcp-server").json()["tools"]}.get(
        "get_data_repositories"
    ) is False
    assert "result" in reply
    assert reply["result"]["isError"] is False
    assert reply["result"]["structuredContent"]["total"] == 2
