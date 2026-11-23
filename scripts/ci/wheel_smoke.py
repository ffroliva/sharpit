"""Smoke test for an installed sharpit wheel: read bundled docs and serve the sample app.

Run from the repository root with PYTHONPATH=. and the venv python, after installing the wheel plus fastapi,
pydantic-settings, uvicorn and httpx. Fails if sharpit was imported from the source tree instead of the installed wheel.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

from examples.fastapi_sample.app import create_app
from fastapi.testclient import TestClient

import sharpit
from sharpit.cli.docs_catalog import TOPICS


def check_docs(package: Path) -> None:
    root = Path(__file__).resolve().parents[2]
    docs = package / "_docs"
    sources = {file for file, _, _ in TOPICS.values()}
    packaged = {page.relative_to(docs).as_posix() for page in docs.rglob("*") if page.is_file()}
    assert sources, "documentation catalog is empty"
    assert packaged == sources, f"unexpected documentation corpus: {packaged ^ sources}"
    for file in sources:
        assert (docs / file).read_bytes() == (root / file).read_bytes(), f"documentation differs: {file}"

    executable = Path(sys.executable).with_name("sharpit.exe" if os.name == "nt" else "sharpit")
    environment = {**os.environ, "SHARPIT_URL": "not an application URL"}
    environment.pop("PYTHONPATH", None)
    with TemporaryDirectory() as outside_repo:
        commands = ((), ("cli",), ("--search", "sharpit"))
        outputs: list[bytes] = []
        for args in commands:
            result = subprocess.run(
                [str(executable), "docs", *args],
                cwd=outside_repo,
                env=environment,
                capture_output=True,
                check=False,
                timeout=15,
            )
            assert result.returncode == 0, result.stderr.decode("utf-8", errors="replace")
            outputs.append(result.stdout)
    listing, page, search = outputs
    assert listing.startswith(f"Bundled documentation for sharpit {sharpit.__version__}:".encode())
    assert b"cli - " in listing
    file = TOPICS["cli"][0]
    assert page == (docs / file).read_bytes()
    assert any(line.startswith(f"{file}:".encode()) for line in search.splitlines())
    print(f"sharpit docs: {len(sources)} bundled pages, listing, page and search OK")


location = Path(sharpit.__file__).resolve()
assert "site-packages" in location.parts, f"sharpit came from {location}, not an installed wheel"
assert (location.parent / "py.typed").is_file(), "py.typed missing from the wheel"
assert (location.parent / "ui" / "static" / "index.html").is_file(), "ui/static/index.html missing from the wheel"
check_docs(location.parent)

with TestClient(
    create_app(enabled="ON", show_banner=False), base_url="http://localhost", client=("127.0.0.1", 50000)
) as client:
    overview = client.get("/sharpit/api/overview")
    shell = client.get("/sharpit/")
print(f"sharpit {sharpit.__version__} from {location.parent}")
print(f"GET /sharpit/api/overview -> {overview.status_code}")
print(f"GET /sharpit/ -> {shell.status_code}")
sys.exit(0 if overview.status_code == 200 and shell.status_code == 200 else 1)
