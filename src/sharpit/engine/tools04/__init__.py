"""The 0.4 panels' tools, collected by ``engine.tools`` at its import."""

# first: ``engine.tools`` imports every module here, so a module imported on its own would meet itself half-loaded
from sharpit.engine import tools as _tools  # noqa: F401  # pyright: ignore[reportUnusedImport]
