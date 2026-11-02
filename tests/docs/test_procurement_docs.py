"""Procurement hygiene documentation requirements (spec \u00a75.4, plan G4)."""

import re
import tomllib
from pathlib import Path

import sharpit

ROOT = Path(__file__).resolve().parents[2]


def test_readme_install_uses_current_pypi_version_and_valid_extra() -> None:
    readme_path = ROOT / "README.md"
    assert readme_path.is_file(), "README.md must exist"
    readme_text = readme_path.read_text(encoding="utf-8")

    pyproject_path = ROOT / "pyproject.toml"
    assert pyproject_path.is_file(), "pyproject.toml must exist"
    pyproject_data = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))
    project_meta = pyproject_data.get("project", {})
    package_name = project_meta.get("name", "sharpit")
    valid_extras = set(project_meta.get("optional-dependencies", {}).keys())
    current_version = sharpit.__version__

    assert "not on PyPI yet" not in readme_text, "README.md must not state sharpit is not on PyPI yet"
    assert "git+https://" not in readme_text, "README.md must not advertise git clone installation"

    install_matches = re.findall(
        r"(?:pip install|uv add)\s+[\"']?([a-zA-Z0-9_\-]+(?:\[([a-zA-Z0-9_,\s\-]+)\])?)[ \"']?",
        readme_text,
    )
    assert len(install_matches) > 0, "README.md must provide a pip or uv installation command"
    for full_pkg, extras_str in install_matches:
        base_pkg = full_pkg.split("[")[0].strip()
        assert base_pkg == package_name, (
            f"Install command package '{base_pkg}' does not match pyproject name '{package_name}'"
        )
        if extras_str:
            for extra in [e.strip() for e in extras_str.split(",")]:
                assert extra in valid_extras, (
                    f"Documented install extra '{extra}' is not in pyproject optional-dependencies"
                )

    assert current_version in readme_text, f"README.md must state the current version '{current_version}'"


def test_readme_gate_and_gflow_proof_precede_details() -> None:
    readme_path = ROOT / "README.md"
    assert readme_path.is_file(), "README.md must exist"
    readme_text = readme_path.read_text(encoding="utf-8")

    gate_match = re.search(r"pytest\s+--sharpit", readme_text)
    assert gate_match is not None, "README.md must mention CI gate with pytest --sharpit"
    gate_pos = gate_match.start()

    proof_match = re.search(r"gflow-cli", readme_text, re.IGNORECASE)
    assert proof_match is not None, "README.md must cite the gflow-cli proof"
    proof_pos = proof_match.start()

    quickstart_match = re.search(r"60 seconds|Quickstart", readme_text, re.IGNORECASE)
    assert quickstart_match is not None, "README.md must include a 60-seconds quickstart section"
    quickstart_pos = quickstart_match.start()

    assert gate_pos < quickstart_pos, "CI gate command must precede the 60-seconds quickstart section"
    assert proof_pos < quickstart_pos, "gflow-cli proof must precede the 60-seconds quickstart section"

    quickstart_section = readme_text[quickstart_pos:]
    assert "sharpit.install" in quickstart_section, (
        "60-seconds section must show minimal sharpit.install(app) integration"
    )
    assert "pytest --sharpit" in quickstart_section, "60-seconds section must show command that emits the report"

    assert "5,662" in readme_text or "5662" in readme_text, "gflow-cli proof must mention test count (5,662)"
    assert "N+1" in readme_text, "gflow-cli proof must mention findings (N+1 queries caught)"
