import json
from pathlib import Path
from typing import Any

import pytest
from starlette.testclient import TestClient
from tests.console_corpus import build_app, record
from tests.console_corpus.transport import TRANSPORT_CASES

CORPUS = Path(__file__).parents[1] / "fixtures" / "console_corpus" / "transport.json"


@pytest.mark.parametrize("case", TRANSPORT_CASES, ids=lambda case: case["id"])
def test_transport_response_matches_corpus(case: dict[str, Any], tmp_path: Path) -> None:
    expected = json.loads(CORPUS.read_text(encoding="utf-8"))[case["id"]]
    app = build_app(state_dir=str(tmp_path / case["id"]), **case.get("install", {}))
    peer = case.get("peer", ("127.0.0.1", 50000))
    with TestClient(app, base_url="http://localhost", client=peer) as client:
        actual = record(client, case.get("method", "GET"), case["path"], case.get("headers"))

    assert actual == expected
