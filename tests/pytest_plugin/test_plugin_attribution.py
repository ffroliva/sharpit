from __future__ import annotations

import json

import pytest


def test_async_tests_attributed(pytester: pytest.Pytester) -> None:
    pytester.makepyfile(
        """
        import sqlite3
        import pytest

        @pytest.mark.asyncio
        async def test_async_query():
            connection = sqlite3.connect(':memory:')
            for _ in range(5): connection.execute('SELECT 1')
        """
    )

    result = pytester.runpytest(
        "--sharpit", "--sharpit-no-advisors", "--sharpit-allow-unknown", "--sharpit-report=report.json", "-q"
    )

    assert result.ret == 1
    data = json.loads((pytester.path / "report.json").read_text())
    assert data["tests"][0]["phases"]["call"]["queries"] == 5
    assert "sharpit.n-plus-one" in data["tests"][0]["findings"][0]


def test_testclient_portal_attribution(pytester: pytest.Pytester) -> None:
    pytester.makepyfile(
        """
        import sqlite3
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        app = FastAPI()
        @app.get('/query')
        def query():
            sqlite3.connect(':memory:').execute('SELECT 1')
            return {'ok': True}
        client = TestClient(app)

        def test_portal_query():
            assert client.get('/query').status_code == 200
        """
    )

    result = pytester.runpytest(
        "--sharpit", "--sharpit-no-advisors", "--sharpit-allow-unknown", "--sharpit-report=report.json", "-q"
    )

    assert result.ret == 0
    data = json.loads((pytester.path / "report.json").read_text())
    assert data["tests"][0]["phases"]["call"]["queries"] == 1


def test_long_lived_async_runner_attributed(pytester: pytest.Pytester) -> None:
    pytester.makepyfile(
        """
        import sqlite3
        import pytest

        @pytest.fixture(scope='module')
        def anyio_backend(): return 'asyncio'

        @pytest.fixture(scope='module')
        async def shared_runner(anyio_backend):
            return True

        async def query_five_times():
            connection = sqlite3.connect(':memory:')
            for _ in range(5): connection.execute('SELECT 1')

        @pytest.mark.anyio
        async def test_first(shared_runner): await query_five_times()

        @pytest.mark.anyio
        async def test_second(shared_runner): await query_five_times()
        """
    )

    result = pytester.runpytest(
        "--sharpit", "--sharpit-no-advisors", "--sharpit-allow-unknown", "--sharpit-report=report.json", "-q"
    )

    assert result.ret == 1
    data = json.loads((pytester.path / "report.json").read_text())
    assert len(data["tests"]) == 2
    assert all(test["phases"]["call"]["queries"] == 5 for test in data["tests"])
    assert all(test["findings"] for test in data["tests"])


def test_lifespan_worker_unattributed(pytester: pytest.Pytester) -> None:
    pytester.makepyfile(
        """
        import asyncio
        import sqlite3
        import pytest
        from contextlib import asynccontextmanager
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        async def poll():
            while True:
                sqlite3.connect(':memory:').execute('SELECT 1')
                await asyncio.sleep(0.005)

        @asynccontextmanager
        async def lifespan(app):
            task = asyncio.create_task(poll())
            try: yield
            finally:
                task.cancel()
                try: await task
                except asyncio.CancelledError: pass

        app = FastAPI(lifespan=lifespan)
        @app.get('/')
        def home(): return {'ok': True}

        @pytest.fixture(scope='module')
        def client():
            with TestClient(app) as test_client:
                yield test_client

        def test_startup(client):
            assert client.get('/').status_code == 200

        def test_later_request(client):
            assert client.get('/').status_code == 200
        """
    )

    result = pytester.runpytest(
        "--sharpit",
        "--sharpit-no-advisors",
        "--sharpit-max-unattributed=100",
        "--sharpit-allow-unknown",
        "--sharpit-report=report.json",
        "-q",
    )

    assert result.ret == 0
    data = json.loads((pytester.path / "report.json").read_text())
    assert data["totals"]["unattributed"] > 0
    assert data["tests"][1]["phases"]["call"]["queries"] == 0
