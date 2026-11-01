"""sharpit: embedded, local-only developer console for Python apps."""

__version__ = "0.3.0"

from sharpit.fastapi.adapter import install  # noqa: E402 - after __version__, which the adapter's modules read
from sharpit.fastapi.sources import attach_sql_sources, detach_sql_sources  # noqa: E402

__all__ = ["__version__", "attach_sql_sources", "detach_sql_sources", "install"]
