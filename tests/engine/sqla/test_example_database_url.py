from pathlib import Path

import pytest

pytestmark = pytest.mark.needs_sqlalchemy


def test_example_app_uses_database_url_for_async_engine(tmp_path: Path) -> None:
    from examples.fastapi_sqla.app import create_app
    from sqlalchemy.engine import make_url

    database_url = f"sqlite:///{(tmp_path / 'custom.db').as_posix()}"
    app = create_app(db_dir=tmp_path / "app", database_url=database_url, show_banner=False)
    assert app.state.async_engine.sync_engine.url.database == make_url(database_url).database
