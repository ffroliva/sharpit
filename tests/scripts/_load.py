"""Load a script under scripts/ as a module (scripts/ is not a package)."""

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

ROOT = Path(__file__).resolve().parents[2]


def load_script(relative: str) -> ModuleType:
    path = ROOT / relative
    name = "_script_" + path.stem
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec
    assert spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module
