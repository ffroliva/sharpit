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

    proof_header = "### Outside proof: gflow-cli"
    proof_start = readme_text.find(proof_header)
    assert proof_start != -1, "README.md must contain '### Outside proof: gflow-cli'"
    proof_end = readme_text.find("## 60 seconds", proof_start)
    assert proof_end != -1, "README.md must contain '## 60 seconds' after gflow proof"
    proof_section = readme_text[proof_start:proof_end]

    assert "independent" not in proof_section.lower(), (
        "gflow-cli proof must drop 'independent' claim as it was run by sharpit's author"
    )
    assert "sharpit's author" in proof_section.lower(), "gflow-cli proof must state run by sharpit's author"
    assert "0.3.0 integration branch" in proof_section, "gflow-cli proof must state run on 0.3.0 integration branch"
    assert "sharpit's own report" in proof_section, "gflow-cli proof link text must state it is sharpit's own report"
    assert "5 failed by sharpit gates" in proof_section, (
        "gflow-cli proof must mention that 5 tests failed by sharpit gates"
    )
    assert "53k" in proof_section, "gflow-cli proof must mention ~53k statements executed"
    assert "27,997 attributed" in proof_section, "gflow-cli proof must state 27,997 attributed statements"
    assert "25,092 filtered" in proof_section, "gflow-cli proof must state 25,092 filtered statements"
    assert "0 unattributed" in proof_section, "gflow-cli proof must state 0 unattributed statements"
    assert "6 N+1 findings" in proof_section, "gflow-cli proof must state 6 N+1 findings instead of defects"
    assert "1 was a real defect" in proof_section or "1 real" in proof_section, (
        "gflow-cli proof must state 1 real defect"
    )
    assert "2 were noise" in proof_section or "2 noise" in proof_section, (
        "gflow-cli proof must state 2 were noise (filtered since 0.3.0)"
    )
    assert "3 were expected polling" in proof_section or "3 expected polling" in proof_section, (
        "gflow-cli proof must state 3 were expected polling"
    )


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


def _parse_yaml(text: str) -> dict[str, object]:
    try:
        import yaml  # type: ignore[import-not-found]

        loaded = yaml.safe_load(text)
        if isinstance(loaded, dict):
            return loaded
    except ImportError:
        pass

    result: dict[str, object] = {}
    updates: list[dict[str, object]] = []
    current_update: dict[str, object] | None = None
    sub_map: dict[str, object] | None = None

    for line in text.splitlines():
        trimmed = line.strip()
        if not trimmed or trimmed.startswith("#"):
            continue
        indent = len(line) - len(line.lstrip())

        if indent == 0:
            if ":" in trimmed:
                k, v = trimmed.split(":", 1)
                k = k.strip()
                v = v.strip().strip("\"'")
                if k == "version":
                    result["version"] = int(v) if v.isdigit() else v
                elif k == "updates":
                    result["updates"] = updates
            continue

        if trimmed.startswith("- "):
            current_update = {}
            updates.append(current_update)
            sub_map = None
            item_part = trimmed[2:].strip()
            if ":" in item_part:
                k, v = item_part.split(":", 1)
                v = v.strip().strip("\"'")
                current_update[k.strip()] = int(v) if v.isdigit() else v
            continue

        if current_update is not None:
            if ":" in trimmed:
                k, v = trimmed.split(":", 1)
                k = k.strip()
                v = v.strip().strip("\"'")
                if not v:
                    sub_dict: dict[str, object] = {}
                    if indent == 4:
                        current_update[k] = sub_dict
                        sub_map = sub_dict
                    elif indent > 4 and sub_map is not None:
                        nested_sub: dict[str, object] = {}
                        sub_map[k] = nested_sub
                        sub_map = nested_sub
                else:
                    val: object = int(v) if v.isdigit() else v
                    if indent == 4:
                        current_update[k] = val
                        sub_map = None
                    elif sub_map is not None:
                        sub_map[k] = val
            elif trimmed.startswith("- ") and sub_map is not None:
                val = trimmed[2:].strip().strip("\"'")
                raw_patterns = sub_map.get("patterns")
                if not isinstance(raw_patterns, list):
                    patterns_list: list[object] = [val]
                    sub_map["patterns"] = patterns_list
                else:
                    raw_patterns.append(val)

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
