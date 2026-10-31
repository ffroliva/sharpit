"""Packaging metadata that PyPI and installers read from pyproject.toml."""

from __future__ import annotations

import tomllib
from pathlib import Path

import sharpit

PYPROJECT = tomllib.loads((Path(__file__).resolve().parents[1] / "pyproject.toml").read_text(encoding="utf-8"))
PROJECT = PYPROJECT["project"]


def test_version_is_0_2_0() -> None:
    assert sharpit.__version__ == "0.2.0"


def test_runtime_dependencies_are_exactly_starlette_and_packaging() -> None:
    assert sorted(d.split(">")[0] for d in PROJECT["dependencies"]) == ["packaging", "starlette"]


def test_user_extras_match_the_test_extra_floors() -> None:
    extras = PROJECT["optional-dependencies"]
    assert extras["fastapi"] == ["fastapi>=0.115"]
    assert extras["settings"] == ["pydantic-settings>=2.4"]
    assert set(extras["fastapi"] + extras["settings"]) <= set(extras["test"])


def test_pypi_metadata_is_complete() -> None:
    classifiers = set(PROJECT["classifiers"])
    assert {
        "Development Status :: 3 - Alpha",
        "Framework :: FastAPI",
        "Typing :: Typed",
        "Programming Language :: Python :: 3.12",
        "Programming Language :: Python :: 3.13",
        "Programming Language :: Python :: 3.14",
    } <= classifiers
    assert PROJECT["authors"] == [{"name": "Flavio Oliva"}]
    assert PROJECT["keywords"]
    assert set(PROJECT["urls"]) == {"Homepage", "Source", "Issues", "Changelog"}
    assert all(u.startswith("https://github.com/ffroliva/sharpit") for u in PROJECT["urls"].values())


def test_sdist_keeps_internal_material_out() -> None:
    exclude = PYPROJECT["tool"]["hatch"]["build"]["targets"]["sdist"]["exclude"]
    assert {"/.superpowers", "/.claude", "/replica", "/skills", "/docs/superpowers", "/ui"} <= set(exclude)
