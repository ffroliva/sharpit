import pytest
from sqlalchemy.engine import make_url
from tests.live.conftest import _worker_database_url

pytestmark = pytest.mark.needs_sqlalchemy


def test_worker_database_url_uses_one_database_per_xdist_worker() -> None:
    assert make_url(_worker_database_url("mysql+pymysql://root:pw@localhost/sharpit", "gw3")).database == "sharpit_gw3"


def test_worker_database_url_uses_default_database_without_xdist() -> None:
    url = "postgresql+psycopg://postgres:pw@localhost/sharpit"
    assert _worker_database_url(url, None) == url


def test_worker_database_url_supports_postgresql_url_forms() -> None:
    url = "postgresql://postgres:pw@localhost/sharpit?sslmode=disable"
    assert make_url(_worker_database_url(url, "gw3")).database == "sharpit_gw3"
