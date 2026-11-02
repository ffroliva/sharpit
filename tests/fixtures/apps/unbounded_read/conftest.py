from pathlib import Path
from runpy import run_path

root_conftest = Path(__file__).resolve().parents[3] / "conftest.py"
if root_conftest.is_file():
    shared = run_path(str(root_conftest))
    globals().update(
        {
            name: shared[name]
            for name in (
                "FIXTURES",
                "NEEDS_SQLALCHEMY_MISSING",
                "OpenStream",
                "SideEffectGuard",
                "_PATH_PARAMS",
                "get_paths",
                "golden",
                "sqlalchemy_imports_without_marker",
            )
        }
    )
else:
    from fixture import app

    import sharpit

    sharpit.install(app, enabled="ON")
