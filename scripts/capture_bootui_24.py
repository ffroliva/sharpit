"""Capture BootUI 2.4.0 tracker fixtures (provenance, catalogs, goldens)."""

import os
import subprocess
from pathlib import Path

from scripts.capture_bootui import capture

PINNED_COMMIT = "0df7ed764688d04f83c246c9965e90158c1db488"
PINNED_TAG = "v2.4.0"
REPO = Path(__file__).resolve().parents[1]
output_dir = str((REPO / "tests/fixtures/bootui/2.4.0").resolve())
repo = Path(os.environ.get("BOOTUI_GIT", REPO.parents[1] / "boot-ui"))
actual_commit = subprocess.check_output(
    ["git", "-C", str(repo), "rev-parse", f"{PINNED_TAG}^{{commit}}"], text=True
).strip()
if actual_commit != PINNED_COMMIT:
    raise RuntimeError(f"Pinned tag resolves to {actual_commit}, expected {PINNED_COMMIT}")

if __name__ == "__main__":
    capture(
        tag=PINNED_TAG,
        commit=PINNED_COMMIT,
        output_dir=output_dir,
        version="2.4.0",
        date="2026-11-18",
        repo=repo,
    )
