"""Capture BootUI 2.3.0 tracker fixtures (provenance, catalogs, goldens)."""

import os
import subprocess
from pathlib import Path

from scripts.capture_bootui import capture

PINNED_COMMIT = "7c89042c6a0a47e1cb22d2df7412d2177d7416d1"
PINNED_TAG = "v2.3.0"
REPO = Path(__file__).resolve().parents[1]
output_dir = str((REPO / "tests/fixtures/bootui/2.3.0").resolve())
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
        version="2.3.0",
        date="2026-11-10",
        repo=repo,
    )
