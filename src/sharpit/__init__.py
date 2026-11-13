"""sharpit is a local developer console and pytest gate for FastAPI apps, a Python port of BootUI by Julien Dubois."""

__version__ = "0.6.0"

from typing import TYPE_CHECKING  # noqa: E402  # after __version__, the only version site

__all__ = ["__version__", "attach_sql_sources", "detach_sql_sources", "install", "record_security_event"]

if TYPE_CHECKING:
    from sharpit.engine.capture.securitylogs import record_security_event as record_security_event
    from sharpit.fastapi.adapter import install as install
    from sharpit.fastapi.sources import attach_sql_sources as attach_sql_sources
    from sharpit.fastapi.sources import detach_sql_sources as detach_sql_sources

if not TYPE_CHECKING:  # runtime only: a module ``__getattr__`` pyright could see would accept any ``sharpit.<name>``

    def __getattr__(name: str) -> object:
        """Load a public name on first use (PEP 562), so ``import sharpit`` does not import FastAPI or the adapter."""
        if name == "install":
            from sharpit.fastapi.adapter import install as value  # noqa: PLC0415
        elif name == "attach_sql_sources":
            from sharpit.fastapi.sources import attach_sql_sources as value  # noqa: PLC0415
        elif name == "detach_sql_sources":
            from sharpit.fastapi.sources import detach_sql_sources as value  # noqa: PLC0415
        elif name == "record_security_event":
            from sharpit.engine.capture.securitylogs import record_security_event as value  # noqa: PLC0415
        else:
            raise AttributeError(f"module 'sharpit' has no attribute {name!r}")
        globals()[name] = value
        return value

    def __dir__() -> list[str]:
        return sorted(set(globals()) | set(__all__))
