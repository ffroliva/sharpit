"""Installed-distribution inventory (spec 8 Vulnerabilities; the PyPI stand-in for BootUI's classpath scan).

Distributions come from ``importlib.metadata.distributions()`` in ``sys.path`` order. Names are PEP 503 normalised;
duplicates by (name, version) keep the first copy found; distributions without a name or version are skipped, and so is
sharpit itself.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from importlib.metadata import Distribution, distributions

from packaging.utils import canonicalize_name

_OWN = "sharpit"


@dataclass(frozen=True)
class Package:
    name: str  # PEP 503 normalised
    version: str
    location: str | None


def inventory(source: Callable[[], Iterable[Distribution]] = distributions) -> list[Package]:
    packages: list[Package] = []
    seen: set[tuple[str, str]] = set()
    for dist in source():
        raw_name = dist.metadata.get("Name")  # a missing key via [] is deprecated (KeyError in a future Python)
        version: str | None = dist.version
        if not raw_name or not version:
            continue
        name = canonicalize_name(raw_name)
        if name == _OWN or (name, version) in seen:
            continue
        seen.add((name, version))
        packages.append(Package(name, version, _location(dist)))
    return packages


def _location(dist: Distribution) -> str | None:
    try:
        return str(dist.locate_file(""))
    except Exception:  # custom finders need not support locate_file, and a broken one must not stop the scan
        return None
