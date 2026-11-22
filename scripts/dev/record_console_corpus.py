"""Regenerate the checked-in FastAPI transport and GET response corpora."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from starlette.testclient import TestClient  # noqa: E402
from tests.console_corpus import (  # noqa: E402
    build_app,
    environment_fingerprint,
    get_routes,
    isolated_environment,
    isolated_sqlalchemy_state,
    normalise,
    record,
)
from tests.console_corpus.transport import TRANSPORT_CASES  # noqa: E402
from tests.fastapi.test_console_corpus_get import DEFERRED  # noqa: E402

CORPUS_DIR = ROOT / "tests" / "fixtures" / "console_corpus"


def _write(path: Path, corpus: dict[str, Any]) -> None:
    text = json.dumps(corpus, indent=2, sort_keys=True) + "\n"
    path.write_text(text, encoding="utf-8", newline="\n")


def _transport_corpus() -> dict[str, Any]:
    corpus: dict[str, Any] = {}
    with isolated_sqlalchemy_state():
        for case in TRANSPORT_CASES:
            with TemporaryDirectory(prefix="sharpit-console-corpus-") as state_dir, isolated_environment(state_dir):
                app = build_app(state_dir=state_dir, **case.get("install", {}))
                peer = case.get("peer", ("127.0.0.1", 50000))
                with TestClient(app, base_url="http://localhost", client=peer) as client:
                    corpus[case["id"]] = record(client, case.get("method", "GET"), case["path"], case.get("headers"))
    return corpus


def _get_corpus() -> dict[str, Any]:
    deferred = {path for path, _reason in DEFERRED}
    with (
        isolated_sqlalchemy_state(),
        TemporaryDirectory(prefix="sharpit-console-corpus-") as state_dir,
        isolated_environment(state_dir),
    ):
        paths = sorted(path for method, path in get_routes(build_app(state_dir=state_dir)) if method == "GET")
        if not deferred <= set(paths):
            raise RuntimeError(f"Deferred routes are absent from the mounted API: {sorted(deferred - set(paths))}")
        corpus: dict[str, Any] = {}
        for path in paths:
            if path in deferred:
                continue
            app = build_app(state_dir=state_dir)
            with TestClient(app, base_url="http://localhost", client=("127.0.0.1", 50000)) as client:
                corpus[path] = normalise(record(client, "GET", f"/sharpit{path}"))
        return corpus


def main() -> None:
    transport = _transport_corpus()
    get = _get_corpus()
    _write(CORPUS_DIR / "transport.json", transport)
    _write(CORPUS_DIR / "panels_get.json", get)
    _write(CORPUS_DIR / "environment.json", environment_fingerprint())
    print(f"Recorded {len(transport)} transport cases and {len(get)} GET routes.")


if __name__ == "__main__":
    main()
