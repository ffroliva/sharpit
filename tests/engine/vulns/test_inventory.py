"""Installed-distribution inventory (spec 8 Vulnerabilities: dedupe/skip rules)."""

from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from sharpit.engine.collectors.vulns.inventory import Package, inventory


class FakeDist:
    def __init__(self, name: str | None, version: str | None, where: str | None = "/site") -> None:
        self.metadata = {"Name": name} if name is not None else {}
        self.version = version
        self._where = where

    def locate_file(self, path: str) -> Path:
        if self._where is None:
            raise NotImplementedError
        if self._where == "boom":
            raise RuntimeError("third-party finder bug")
        return Path(self._where) / path


# new: spec 8 inventory rules (PEP 503 names, first-on-sys.path dedupe, skip versionless and sharpit)
def test_dedupes_skips_versionless_and_sharpit():
    dists = [
        FakeDist("Jinja2", "3.1.2", "/first"),
        FakeDist("jinja2", "3.1.2", "/second"),  # same normalised name and version -> later copy dropped
        FakeDist("jinja2", "3.1.4", "/second"),  # another version of the same name is a separate entry
        FakeDist("No_Version.Pkg", None),
        FakeDist("SharpIt", "0.1.0"),
        FakeDist(None, "1.0"),
        FakeDist("Typing_Extensions", "4.12.2", None),
    ]

    result = inventory(lambda: dists)

    assert result == [
        Package("jinja2", "3.1.2", str(Path("/first"))),
        Package("jinja2", "3.1.4", str(Path("/second"))),
        Package("typing-extensions", "4.12.2", None),
    ]


# adapted: OsvVulnerabilityScannerTests.deduplicatesIdenticalPackageVersionInputsBeforeQueryingOsv
# (BootUI dedupes package:version before querying; sharpit does it once, in the inventory)
def test_identical_name_version_queried_once():
    dists = [FakeDist("requests", "2.32.3"), FakeDist("Requests", "2.32.3")]

    assert [p.name for p in inventory(lambda: dists)] == ["requests"]


# new: any locate_file failure leaves the location unknown instead of aborting the inventory
def test_location_failure_of_any_kind_is_none():
    assert inventory(lambda: [FakeDist("rich", "13.7.1", "boom")]) == [Package("rich", "13.7.1", None)]


# new: Package is a dict key in QueryResult.ids
def test_package_is_frozen_and_hashable():
    pkg = Package("jinja2", "3.1.2", None)
    with pytest.raises(FrozenInstanceError):
        pkg.version = "x"  # type: ignore[misc]
    assert {pkg: 1}[Package("jinja2", "3.1.2", None)] == 1


# new: default source is importlib.metadata.distributions()
def test_default_source_is_importlib_metadata():
    found = inventory()

    assert found, "the test environment has installed distributions"
    assert all(p.name and p.version for p in found)
    assert "sharpit" not in {p.name for p in found}
    assert len({(p.name, p.version) for p in found}) == len(found)
