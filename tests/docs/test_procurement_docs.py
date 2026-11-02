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


def test_security_policy_names_supported_versions() -> None:
    security_path = ROOT / "SECURITY.md"
    assert security_path.is_file(), "SECURITY.md must exist"
    security_text = security_path.read_text(encoding="utf-8")

    current_version = sharpit.__version__
    assert "Supported Versions" in security_text, "SECURITY.md must include a 'Supported Versions' section"
    assert current_version in security_text, (
        f"SECURITY.md must name current version '{current_version}' in supported versions"
    )


def test_security_policy_has_private_reporting_route() -> None:
    security_path = ROOT / "SECURITY.md"
    assert security_path.is_file(), "SECURITY.md must exist"
    security_text = security_path.read_text(encoding="utf-8")

    assert "private" in security_text.lower(), "SECURITY.md must describe a private reporting route"
    assert "security/advisories" in security_text or "Security Advisories" in security_text, (
        "SECURITY.md must route reports to GitHub Security Advisories"
    )

    assert "open an issue" not in security_text.lower(), (
        "SECURITY.md must not instruct reporters to open a public issue"
    )
    assert "public issue" not in security_text.lower(), "SECURITY.md must not instruct reporters to use public issues"


def test_security_policy_network_claim_matches_gatekeepers() -> None:
    security_path = ROOT / "SECURITY.md"
    assert security_path.is_file(), "SECURITY.md must exist"
    security_text = security_path.read_text(encoding="utf-8")

    assert "OSV" in security_text, "SECURITY.md must explicitly name OSV client"
    assert "EPSS" in security_text, "SECURITY.md must explicitly name EPSS client"
    assert "network" in security_text.lower(), "SECURITY.md must define the network egress boundary"

    osv_gatekeeper = ROOT / "src" / "sharpit" / "engine" / "collectors" / "vulns" / "osv.py"
    epss_gatekeeper = ROOT / "src" / "sharpit" / "engine" / "collectors" / "vulns" / "epss.py"
    assert osv_gatekeeper.is_file(), "OSV gatekeeper src/sharpit/engine/collectors/vulns/osv.py must exist"
    assert epss_gatekeeper.is_file(), "EPSS gatekeeper src/sharpit/engine/collectors/vulns/epss.py must exist"

    assert "GET" in security_text, "SECURITY.md must clarify that ordinary GET routes make no network requests"
    assert "MCP" in security_text, "SECURITY.md must clarify that MCP tools make no network requests"


def test_dependabot_covers_uv_pip_actions_and_ui_npm() -> None:
    dependabot_path = ROOT / ".github" / "dependabot.yml"
    assert dependabot_path.is_file(), ".github/dependabot.yml must exist"
    content = dependabot_path.read_text(encoding="utf-8")

    assert "version: 2" in content, ".github/dependabot.yml must declare version: 2"
    assert "updates:" in content, ".github/dependabot.yml must declare updates list"

    ecosystems = re.findall(r"package-ecosystem:\s*[\"']?([a-zA-Z0-9_\-]+)[\"']?", content)
    directories = re.findall(r"directory:\s*[\"']?([^\"'\n]+)[\"']?", content)
    assert len(ecosystems) >= 3, "Dependabot must cover at least 3 ecosystems"
    assert len(directories) == len(ecosystems), "Each ecosystem must have a matching directory"

    entries = list(zip(ecosystems, [d.strip() for d in directories], strict=True))
    assert ("pip", "/") in entries, "Dependabot must cover pip at /"
    assert ("github-actions", "/") in entries, "Dependabot must cover github-actions at /"
    assert ("npm", "/ui") in entries, "Dependabot must cover npm at /ui"

    assert "interval:" in content, "Dependabot configuration must declare schedule interval"


def test_skills_readme_stale_line_corrected() -> None:
    skills_path = ROOT / "skills" / "README.md"
    assert skills_path.is_file(), "skills/README.md must exist"
    skills_text = skills_path.read_text(encoding="utf-8")

    assert "Labelled pre-release" not in skills_text, (
        "skills/README.md must not contain stale 'Labelled pre-release' in skill index"
    )
    assert re.search(r"\|\s*`sharpit`\s*\|\s*\(none:\s*user-facing\)\s*\|", skills_text) is not None, (
        "skills/README.md must retain user-facing sharpit skill entry"
    )
