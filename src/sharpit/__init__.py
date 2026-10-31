"""sharpit: embedded, local-only developer console for Python apps."""

__version__ = "0.2.0"

from sharpit.fastapi.adapter import install  # noqa: E402 - after __version__, which the adapter's modules read

__all__ = ["__version__", "install"]
