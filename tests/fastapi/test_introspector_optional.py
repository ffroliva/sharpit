from __future__ import annotations

import builtins
import importlib
import sys

import pytest


def test_introspector_imports_without_fastapi(monkeypatch: pytest.MonkeyPatch) -> None:
    fastapi_modules = {
        name: module for name, module in sys.modules.items() if name == "fastapi" or name.startswith("fastapi.")
    }
    for name in fastapi_modules:
        monkeypatch.delitem(sys.modules, name)
    monkeypatch.delitem(sys.modules, "sharpit.fastapi.introspector", raising=False)
    original_import = builtins.__import__

    def guarded_import(name: str, *args: object, **kwargs: object) -> object:
        if name == "fastapi" or name.startswith("fastapi."):
            raise ImportError("FastAPI intentionally unavailable")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded_import)
    module = importlib.import_module("sharpit.fastapi.introspector")

    assert module.FastApiIntrospector(object()).routes() == []
