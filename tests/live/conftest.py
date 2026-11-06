"""The live profile: real database servers, reached by URL or by a container (collected only with ``--live``).

BootUI's ``mysql-live`` profile with ``-Dbootui.mysql.image``. Per server key, in order:

1. ``SHARPIT_LIVE_<KEY>_URL`` (a SQLAlchemy URL) names a server that is already running: the portable servers on a
   workstation where Docker does not answer (spec facts F1). Nothing is started.
2. Docker answers: Testcontainers starts ``SHARPIT_LIVE_IMAGE_<KEY>`` (default below) and stops it at session end. CI's
   Linux ``live`` job does this; GitHub's Windows runners cannot run Linux containers (F2), so that job is Linux only.
3. Neither: the test skips with a notice. ``scripts/ci/check_live_tests.py`` is what fails CI for a skip.
"""

import os
import time
from collections.abc import Callable, Iterator
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass
from pathlib import Path

import pytest

HERE = Path(__file__).parent
PASSWORD = "sharpit"  # noqa: S105 - a throwaway container
DATABASE = "sharpit"
BOOT_SECONDS = 120.0

# key -> (family, default image, container port, driver, environment of the image). The defaults are the versions
# the spike ran (mysql 8.4.10, mysql 8.0.44, mariadb 12.3.3, postgres 18.2); each tag exists on Docker Hub.
SERVERS: dict[str, tuple[str, str, int, str, dict[str, str]]] = {
    "mysql84": (
        "mysql",
        "mysql:8.4.10",
        3306,
        "mysql+pymysql",
        {"MYSQL_ROOT_PASSWORD": PASSWORD, "MYSQL_DATABASE": DATABASE},
    ),
    "mysql80": (
        "mysql",
        "mysql:8.0.44",
        3306,
        "mysql+pymysql",
        {"MYSQL_ROOT_PASSWORD": PASSWORD, "MYSQL_DATABASE": DATABASE},
    ),
    "mariadb": (
        "mariadb",
        "mariadb:12.3.3",
        3306,
        "mysql+pymysql",
        {"MARIADB_ROOT_PASSWORD": PASSWORD, "MARIADB_DATABASE": DATABASE},
    ),
    "postgresql": (
        "postgresql",
        "postgres:18.2",
        5432,
        "postgresql+psycopg",
        {"POSTGRES_PASSWORD": PASSWORD, "POSTGRES_DB": DATABASE},
    ),
}


@dataclass(frozen=True)
class LiveServer:
    url: str
    family: str
    image: str
    key: str


@pytest.hookimpl(trylast=True)  # after pytest groups items by fixture param, which puts an unparametrized test first
def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    for item in items:
        if item.path.is_relative_to(HERE):
            item.add_marker(pytest.mark.live)
            item.add_marker(pytest.mark.needs_sqlalchemy)
    items.sort(key=lambda item: item.name.startswith("test_every_session_leg_ran"))  # it counts the rows that ran


@pytest.fixture(autouse=True)
def _no_sqlite3_patch_leak() -> None:  # pyright: ignore[reportUnusedFunction]
    """Overrides the suite's: that one detaches every context before each test, and an oracle leg outlives a row."""


def _wait_until_it_answers(url: str) -> None:
    from sqlalchemy import create_engine, text

    engine = create_engine(url)
    deadline = time.monotonic() + BOOT_SECONDS
    try:
        while True:
            try:
                with engine.connect() as connection:
                    connection.execute(text("SELECT 1"))
                return
            except Exception:  # noqa: BLE001 - the server is still starting; the last error is raised at the deadline
                if time.monotonic() > deadline:
                    raise
                time.sleep(1)
    finally:
        engine.dispose()


def _docker_answers() -> bool:
    try:
        import docker  # a testcontainers dependency, imported late so a default run never loads it

        docker.from_env(timeout=5).ping()
    except Exception:  # noqa: BLE001 - any failure to reach the daemon means no Docker here
        return False
    return True


@contextmanager
def _boot(key: str) -> Iterator[LiveServer]:
    """Start the server for ``key`` (or find it by URL) and stop it on exit. The one place a container is started."""
    if key == "sqlite":  # in process: no server to start, so it is not in ``SERVERS``
        yield LiveServer("sqlite://", key, "in-process", key)
        return
    family, default_image, port, driver, environment = SERVERS[key]
    image = os.environ.get(f"SHARPIT_LIVE_IMAGE_{key.upper()}") or default_image
    url = os.environ.get(f"SHARPIT_LIVE_{key.upper()}_URL")
    if url:
        _wait_until_it_answers(url)
        yield LiveServer(url, family, image, key)
        return
    if not _docker_answers():
        pytest.skip(f"live: no SHARPIT_LIVE_{key.upper()}_URL and Docker does not answer; {key} was not tested")
    from testcontainers.core.container import DockerContainer

    container = DockerContainer(image).with_exposed_ports(port)
    for name, value in environment.items():
        container = container.with_env(name, value)
    with container:
        host, mapped = container.get_container_host_ip(), container.get_exposed_port(port)
        user = "postgres" if family == "postgresql" else "root"
        url = f"{driver}://{user}:{PASSWORD}@{host}:{mapped}/{DATABASE}"
        _wait_until_it_answers(url)
        yield LiveServer(url, family, image, key)


@pytest.fixture(scope="session")
def live_servers() -> Iterator[Callable[[str], LiveServer]]:
    """``live_servers(key)``: the one server of a session for ``key``, started on first ask and stopped at the end.

    A test that mixes direct and indirect ``parametrize`` arguments cannot use ``server``: pytest gives such a parameter
    function scope and starts a container per row (field log F16). It takes ``key`` directly and asks here instead.
    """
    with ExitStack() as stack:
        started: dict[str, LiveServer] = {}

        def get(key: str) -> LiveServer:
            if key not in started:
                started[key] = stack.enter_context(_boot(key))
            return started[key]

        yield get


@pytest.fixture(scope="session")
def server(request: pytest.FixtureRequest, live_servers: Callable[[str], LiveServer]) -> LiveServer:
    """The live server for ``request.param`` (a key of ``SERVERS``), via ``parametrize(..., indirect=True)``."""
    return live_servers(request.param)
