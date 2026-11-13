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


def test_readme_console_leads_then_gate_and_exact_gflow_proof() -> None:
    """Owner, 2026-11-13: the README leads with the console and the one-call install; the CI gate and the gflow-cli
    proof follow it (this reverses the 2026-11-02 order, which put the gate first)."""
    readme_path = ROOT / "README.md"
    assert readme_path.is_file(), "README.md must exist"
    readme_text = readme_path.read_text(encoding="utf-8")

    install_pos = readme_text.find("sharpit.install(app)")
    assert install_pos != -1, "README.md must show the one-call sharpit.install(app) integration"
    gate_heading = readme_text.find("## Gate CI on findings")
    assert gate_heading != -1, "README.md must have a 'Gate CI on findings' section"
    assert install_pos < gate_heading, "the one-call install must lead; the CI gate section follows it"
    assert re.search(r"pytest\s+--sharpit --sharpit-report", readme_text[gate_heading:]), (
        "the gate section must show the command that emits the report"
    )
    assert re.search(r"gflow-cli", readme_text[gate_heading:], re.IGNORECASE), "the gate section must cite gflow-cli"

    assert "N+1" in readme_text, "gflow-cli proof must mention findings (N+1 queries caught)"

    proof_header = "### On the author's own project: gflow-cli"
    proof_start = readme_text.find(proof_header)
    assert proof_start != -1, "README.md must contain the author's gflow-cli proof"
    proof_end = readme_text.find("\n## ", proof_start + len(proof_header))
    assert proof_end != -1, "README.md must have a section after the gflow proof"
    proof_section = readme_text[proof_start:proof_end]

    assert "independent" not in proof_section.lower(), (
        "gflow-cli proof must drop 'independent' claim as it was run by sharpit's author"
    )
    assert "sharpit's author" in proof_section.lower(), "gflow-cli proof must state run by sharpit's author"
    assert "sharpit's own report" in proof_section, "gflow-cli proof link text must state it is sharpit's own report"
    assert "No production code was changed" in proof_section, "gflow-cli proof must say no production code changed"

    # every figure the README states comes from the dated report it links to (the 2026-11-13 0.6.0 re-run)
    report_link = re.search(r"\(docs/reports/([^)]+\.md)\)", proof_section)
    assert report_link is not None, "gflow-cli proof must link its dated report under docs/reports/"
    report_text = (ROOT / "docs" / "reports" / report_link.group(1)).read_text(encoding="utf-8")
    figures = ["6,804", "4 failed by sharpit gates", "3 min 21 s", "25,772 attributed", "32,583 filtered", "~58k"]
    for figure in figures:
        assert figure in proof_section, f"gflow-cli proof must state {figure!r}"
    for figure in ("6,804", "25,772 attributed", "32,583 filtered", "3 min 21 s", "**0 unattributed**", "~58k"):
        assert figure in report_text, f"the linked report must back {figure!r}"
    assert "0 unattributed" in proof_section, "gflow-cli proof must state 0 unattributed statements"
    assert "0 N+1 findings" in proof_section, "gflow-cli proof must state the N+1 count of the run"


def test_security_policy_names_supported_versions() -> None:
    security_path = ROOT / "SECURITY.md"
    assert security_path.is_file(), "SECURITY.md must exist"
    security_text = security_path.read_text(encoding="utf-8")

    assert "## Supported Versions" in security_text, "SECURITY.md must include a 'Supported Versions' section"
    start = security_text.find("## Supported Versions")
    end = security_text.find("## Reporting a Vulnerability", start)
    assert end != -1, "SECURITY.md must contain '## Reporting a Vulnerability' after supported versions"
    supported_section = security_text[start:end]

    major_minor = re.match(r"^(\d+\.\d+)", sharpit.__version__)
    assert major_minor is not None, "sharpit.__version__ must start with major.minor"
    mm_prefix = f"{major_minor.group(1)}.x"

    assert mm_prefix in supported_section, (
        f"SECURITY.md supported row must compare major.minor ('{mm_prefix}') without requiring exact __version__"
    )
    assert "latest release on pypi" in supported_section.lower(), (
        "SECURITY.md must state verifiable support boundary (latest release on PyPI)"
    )
    assert "only the current release line receives security updates" not in supported_section.lower(), (
        "SECURITY.md must not state unsupported 'only the current release line receives security updates' policy"
    )


def test_security_policy_has_private_reporting_route() -> None:
    security_path = ROOT / "SECURITY.md"
    assert security_path.is_file(), "SECURITY.md must exist"
    security_text = security_path.read_text(encoding="utf-8")

    assert "## Reporting a Vulnerability" in security_text, "SECURITY.md must include '## Reporting a Vulnerability'"
    start = security_text.find("## Reporting a Vulnerability")
    end = security_text.find("## Network Egress and Trust Boundaries", start)
    assert end != -1, "SECURITY.md must contain '## Network Egress and Trust Boundaries' after reporting"
    reporting_section = security_text[start:end]

    assert "Report a vulnerability" in reporting_section, (
        "SECURITY.md must mention GitHub's 'Report a vulnerability' feature on the Security tab once enabled"
    )
    assert "Security contact request" in reporting_section, (
        "SECURITY.md must instruct opening an issue titled 'Security contact request' until private reporting is"
        " enabled"
    )
    assert "no details" in reporting_section.lower(), (
        "SECURITY.md must instruct that the contact request issue contain no vulnerability details"
    )
    assert "48 hours" not in reporting_section, "SECURITY.md must remove unsupported 48-hour response promise"
    assert "48-hour" not in reporting_section, "SECURITY.md must remove unsupported 48-hour response promise"


def test_security_policy_network_claim_matches_gatekeepers() -> None:
    security_path = ROOT / "SECURITY.md"
    assert security_path.is_file(), "SECURITY.md must exist"
    security_text = security_path.read_text(encoding="utf-8")

    assert "## Network Egress and Trust Boundaries" in security_text, (
        "SECURITY.md must contain '## Network Egress and Trust Boundaries'"
    )
    start = security_text.find("## Network Egress and Trust Boundaries")
    section = security_text[start:]

    osv_gatekeeper = ROOT / "src" / "sharpit" / "engine" / "collectors" / "vulns" / "osv.py"
    epss_gatekeeper = ROOT / "src" / "sharpit" / "engine" / "collectors" / "vulns" / "epss.py"
    assert osv_gatekeeper.is_file(), "OSV gatekeeper src/sharpit/engine/collectors/vulns/osv.py must exist"
    assert epss_gatekeeper.is_file(), "EPSS gatekeeper src/sharpit/engine/collectors/vulns/epss.py must exist"

    assert "entirely offline" not in section.lower(), (
        "SECURITY.md must not falsely claim components operate 'entirely offline'"
    )
    assert "open no sockets" in section.lower(), "SECURITY.md must state that GET routes and MCP tools open no sockets"
    assert "health check (post)" in section.lower() or "health check" in section.lower(), (
        "SECURITY.md must specify the health check behavior"
    )
    assert "pings configured database engines" in section.lower(), (
        "SECURITY.md must state health check pings configured database engines"
    )
    assert "runs user health callables" in section.lower(), (
        "SECURITY.md must state health check runs user health callables"
    )
    assert "read-only sql" in section.lower(), (
        "SECURITY.md must state database panels run read-only SQL through the app's own engines"
    )
    assert "vulnerability scan" in section.lower(), "SECURITY.md must specify vulnerability scan"
    assert "500" in section, "SECURITY.md must mention vulnerability scan package limit (up to 500 packages)"
    assert "SHARPIT_VULNERABILITIES_OSV_BASE_URI" in section, (
        "SECURITY.md must document SHARPIT_VULNERABILITIES_OSV_BASE_URI"
    )
    assert "SHARPIT_VULNERABILITIES_EPSS_BASE_URI" in section, (
        "SECURITY.md must document SHARPIT_VULNERABILITIES_EPSS_BASE_URI"
    )
    assert "SHARPIT_VULNERABILITIES_OSV_ENABLED=false" in section, (
        "SECURITY.md must document SHARPIT_VULNERABILITIES_OSV_ENABLED=false"
    )
    assert "SHARPIT_VULNERABILITIES_EPSS_ENABLED=false" in section, (
        "SECURITY.md must document SHARPIT_VULNERABILITIES_EPSS_ENABLED=false"
    )


def _clean_val(val: str) -> object:
    cleaned = val.strip().strip("\"'")
    return int(cleaned) if cleaned.isdigit() else cleaned


def _parse_block(block: str) -> dict[str, object]:
    entry: dict[str, object] = {}
    for line in block.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or ":" not in stripped:
            continue
        k, v = stripped.split(":", 1)
        key, val = k.strip(), v.strip()
        if val:
            entry[key] = _clean_val(val)
        else:
            entry[key] = {}
    return entry


def _parse_yaml(text: str) -> dict[str, object]:
    try:
        import yaml  # type: ignore[import-not-found]

        loaded = yaml.safe_load(text)
        if isinstance(loaded, dict):
            return loaded
    except ImportError:
        pass

    result: dict[str, object] = {"version": 2, "updates": []}
    updates_list: list[dict[str, object]] = []
    result["updates"] = updates_list

    if "updates:" not in text:
        return result

    updates_text = text.split("updates:", 1)[1]
    blocks = updates_text.split("\n  - ")
    updates_list.extend(_parse_block(b) for b in blocks[1:])

    return result


def test_dependabot_covers_uv_pip_actions_and_ui_npm() -> None:
    dependabot_path = ROOT / ".github" / "dependabot.yml"
    assert dependabot_path.is_file(), ".github/dependabot.yml must exist"
    raw_content = dependabot_path.read_text(encoding="utf-8")

    config = _parse_yaml(raw_content)
    assert config.get("version") == 2, ".github/dependabot.yml must declare version: 2"
    updates = config.get("updates", [])
    assert isinstance(updates, list), "Dependabot configuration must declare updates list"
    assert len(updates) >= 4, "Dependabot must cover at least 4 updates entries"

    entries = [(u.get("package-ecosystem"), u.get("directory")) for u in updates if isinstance(u, dict)]
    assert ("uv", "/") in entries, "Dependabot must cover uv at / (not pip)"
    assert ("pip", "/") not in entries, "Dependabot must not use pip for /"
    assert ("pip", "/website") in entries, "Dependabot must cover pip at /website"
    assert ("github-actions", "/") in entries, "Dependabot must cover github-actions at /"
    assert ("npm", "/ui") in entries, "Dependabot must cover npm at /ui"

    npm_entry = next(
        (
            u
            for u in updates
            if isinstance(u, dict) and u.get("package-ecosystem") == "npm" and u.get("directory") == "/ui"
        ),
        None,
    )
    assert npm_entry is not None, "npm update entry at /ui must exist"
    assert npm_entry.get("open-pull-requests-limit") == 2, "npm update entry must specify open-pull-requests-limit: 2"
    assert "groups" in npm_entry, "npm update entry must group dependencies into one PR"

    assert "npm --prefix ui run build" in raw_content, (
        "Dependabot configuration must comment that npm PRs need 'npm --prefix ui run build' committed"
    )
    assert "drift" in raw_content.lower(), "Dependabot configuration comment must mention CI drift job"


def test_skills_readme_stale_line_corrected() -> None:
    skills_path = ROOT / "skills" / "README.md"
    assert skills_path.is_file(), "skills/README.md must exist"
    skills_text = skills_path.read_text(encoding="utf-8")

    assert (
        re.search(
            r"\|\s*`sharpit`\s*\|\s*\(none:\s*user-facing\)\s*\|.*pre-release",
            skills_text,
            re.IGNORECASE,
        )
        is not None
    ), "skills/README.md must retain user-facing sharpit skill entry labelled pre-release"

    assert "sharpit has no SonarQube project" not in skills_text, (
        "skills/README.md must not claim sharpit has no SonarQube project (it uses SonarCloud)"
    )
    assert "SonarCloud" in skills_text or "sonar" in skills_text.lower(), (
        "skills/README.md provenance table must accurately cite SonarCloud"
    )

    assert "CHANGELOG.md" not in skills_text, (
        "skills/README.md must not list CHANGELOG.md as a file sharpit does not have yet"
    )
    assert "KNOWN_ISSUES.md" in skills_text, (
        "skills/README.md must cite KNOWN_ISSUES.md as a file sharpit does not have yet"
    )
