import logging
import os
import socket
import tempfile
from pathlib import Path

import pytest

from conftest import FIXTURES, SideEffectGuard, golden


def test_golden_shapes_load() -> None:
    names = [p.stem for p in FIXTURES.glob("*.json") if p.stem != "meta"]
    assert {"overview", "config", "loggers", "beans", "mappings", "health", "panels", "vulnerabilities"} <= set(names)
    assert golden("overview")["activation"]["enabled"] is True
    for name in names:
        page = golden(name).get("page")
        if page is None:
            continue
        items = next(v for k, v in golden(name).items() if isinstance(v, list) and len(v) == page["returned"])
        assert page["returned"] == len(items), name
        assert page["hasMore"] == (page["offset"] + page["returned"] < page["matched"]), name


def test_no_side_effects_blocks_socket(no_side_effects: SideEffectGuard) -> None:
    with pytest.raises(AssertionError, match="socket.connect"):
        socket.socket().connect(("127.0.0.1", 9))
    with pytest.raises(AssertionError, match="create_connection"):
        socket.create_connection(("127.0.0.1", 9))
    no_side_effects.rebaseline()


def test_no_side_effects_detects_dns(no_side_effects: SideEffectGuard) -> None:
    with pytest.raises(AssertionError, match="getaddrinfo"):
        socket.getaddrinfo("example.invalid", 80)
    with pytest.raises(AssertionError, match="gethostbyname"):
        socket.gethostbyname("example.invalid")
    no_side_effects.rebaseline()


@pytest.fixture
def own_cwd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # requested before the guard so it snapshots tmp_path: under xdist the shared repo root would trip other workers
    monkeypatch.chdir(tmp_path)


def test_no_side_effects_detects_tempfile_write(own_cwd: None, no_side_effects: SideEffectGuard) -> None:
    with tempfile.NamedTemporaryFile(dir=Path.cwd()), pytest.raises(AssertionError, match="cwd changed"):
        no_side_effects.verify()
    no_side_effects.rebaseline()
    no_side_effects.verify()


def test_no_side_effects_detects_state_dir_write(no_side_effects: SideEffectGuard, tmp_state_dir: Path) -> None:
    (tmp_state_dir / "x").write_text("x")
    with pytest.raises(AssertionError, match="state dir changed"):
        no_side_effects.verify()
    no_side_effects.rebaseline()


def test_no_side_effects_detects_level_change(
    no_side_effects: SideEffectGuard, monkeypatch: pytest.MonkeyPatch
) -> None:
    logger = logging.getLogger("sharpit.test.level")
    logger.setLevel(logging.DEBUG)
    with pytest.raises(AssertionError, match="logger level"):
        no_side_effects.verify()
    logger.setLevel(logging.NOTSET)
    monkeypatch.setitem(os.environ, "SHARPIT_X", "1")
    with pytest.raises(AssertionError, match="os.environ"):
        no_side_effects.verify()
