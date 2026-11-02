from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import get_type_hints

from sharpit.fastapi.capture import CaptureWiring


def test_capture_configuration_contract_is_owned_by_install_module() -> None:
    from sharpit.fastapi.install import _configure_capture

    assert get_type_hints(_configure_capture)["return"] is CaptureWiring


def test_tool_dispatch_import_is_cycle_free() -> None:
    source_root = Path(__file__).resolve().parents[1] / "src"
    script = """
import importlib, sys, types
from pathlib import Path
root = Path(sys.argv[1]) / 'sharpit'
sharpit = types.ModuleType('sharpit')
sharpit.__path__ = [str(root)]
sharpit.__version__ = '0.3.0'
sys.modules['sharpit'] = sharpit
importlib.import_module('sharpit.engine.tool_dispatch')
"""
    result = subprocess.run(
        [sys.executable, "-c", script, str(source_root)], capture_output=True, text=True, check=False
    )

    assert result.returncode == 0, result.stderr
