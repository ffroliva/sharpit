"""sharpit is a local developer console and pytest gate for FastAPI apps, a Python port of BootUI by Julien Dubois."""

__version__ = "0.5.0"

from sharpit.engine.capture.securitylogs import record_security_event as record_security_event  # noqa: E402
from sharpit.fastapi.adapter import install  # noqa: E402 - after __version__, which the adapter's modules read
from sharpit.fastapi.sources import attach_sql_sources, detach_sql_sources  # noqa: E402

__all__ = ["__version__", "attach_sql_sources", "detach_sql_sources", "install", "record_security_event"]
