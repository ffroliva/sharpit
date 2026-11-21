import atexit
import json
import math
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path


def _fs_path(path: str | Path) -> Path:
    raw = os.path.abspath(os.fspath(path)).removeprefix("\\\\?\\")
    return Path("\\\\?\\" + raw) if os.name == "nt" else Path(raw)


def _iter_java_files(root: str | Path) -> list[Path]:
    base = _fs_path(root)
    if not base.exists():
        return []
    files: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(base):
        dirnames[:] = sorted(d for d in dirnames if d not in {"node_modules", "target", ".git"})
        files.extend(Path(dirpath) / fname for fname in sorted(filenames) if fname.endswith(".java"))
    return files


def _rel_posix(path: str | Path, root: str | Path) -> str:
    return _fs_path(path).relative_to(_fs_path(root)).as_posix()


def _extract_and_build(repo: Path, tag: str, version: str) -> tuple[str, str, list[str], str, str, str]:
    tag_object = subprocess.check_output(["git", "-C", str(repo), "rev-parse", tag], text=True).strip()
    bootui_root = tempfile.mkdtemp(prefix=f"bootui-{version}-")
    atexit.register(shutil.rmtree, bootui_root, ignore_errors=True)
    settings_file = Path(bootui_root) / "maven-settings.xml"
    settings_file.write_text(
        '<settings xmlns="http://maven.apache.org/SETTINGS/1.2.0"><mirrors><mirror>'
        "<id>bootui-central</id><mirrorOf>*</mirrorOf><url>https://repo.maven.apache.org/maven2</url>"
        "</mirror></mirrors></settings>",
        encoding="utf-8",
    )
    archive = subprocess.Popen(["git", "-C", str(repo), "archive", tag], stdout=subprocess.PIPE)
    extract = subprocess.run(["tar", "-x", "-C", bootui_root], stdin=archive.stdout, check=False)
    if archive.stdout:
        archive.stdout.close()
    if archive.wait() or extract.returncode:
        raise SystemExit("git archive extraction failed")
    java_version = subprocess.run(["java", "-version"], capture_output=True, text=True, check=True)
    maven_version = subprocess.run(["cmd", "/c", "mvn", "-v"], capture_output=True, text=True, check=True)
    maven_command = [
        "mvn",
        "-pl",
        "bootui-spring-boot-starter",
        "-am",
        "-DskipTests",
        "-U",
        "-Dmaven.compiler.release=17",
        "-Dmaven.compiler.proc=full",
        "compile",
    ]
    settings_override = (
        "BOOTUI_MAVEN_SETTINGS environment file"
        if os.environ.get("BOOTUI_MAVEN_SETTINGS")
        else "temporary settings.xml mirrors all repositories to Maven Central"
    )
    actual_maven_command = [*maven_command, "-s", os.environ.get("BOOTUI_MAVEN_SETTINGS", str(settings_file))]
    subprocess.run(["cmd", "/c", *actual_maven_command], cwd=bootui_root, check=True)
    java_version_output = (java_version.stdout + java_version.stderr).strip()
    maven_version_output = (maven_version.stdout + maven_version.stderr).strip()
    maven_version_output = re.sub(r"(?m)^(Maven home: ).*$", r"\1<local-path>", maven_version_output)
    maven_version_output = re.sub(r"(?m)^(Java version:.*?runtime: ).*$", r"\1<local-path>", maven_version_output)
    maven_version_output = re.sub(r"(?i)(?<![A-Za-z0-9])[A-Z]:[/\\][^\s,)]*", "<local-path>", maven_version_output)
    return bootui_root, tag_object, maven_command, java_version_output, maven_version_output, settings_override


def _capture_panels(bootui_root: str, output_dir: str) -> None:
    panels_file = f"{bootui_root}/bootui-engine/src/main/java/io/github/jdubois/bootui/engine/panel/BootUiPanels.java"
    with open(panels_file, encoding="utf-8") as f:
        panels_code = f.read()

    consts = dict(re.findall(r'public\s+static\s+final\s+String\s+(\w+)\s*=\s*"([^"]+)";', panels_code))
    panel_regex = re.compile(r'new\s+Panel\(\s*(\w+)\s*,\s*"([^"]+)"\s*,\s*(true|false)\s*,\s*(.*?)\s*\)')

    panels_list = []
    for m in panel_regex.finditer(panels_code):
        c_id, title, action_str, prefix_expr = m.groups()
        panel_id = consts.get(c_id, c_id)
        action = action_str == "true"
        prefixes = []
        if "List.of()" not in prefix_expr and ('"' in prefix_expr or "List.of(" in prefix_expr):
            prefixes = re.findall(r'"([^"]+)"', prefix_expr)
        panels_list.append({"id": panel_id, "title": title, "actionCapable": action, "apiPrefixes": prefixes})

    with open(f"{output_dir}/panels.json", "w", encoding="utf-8", newline="\n") as f:
        json.dump({"panels": panels_list}, f, indent=2)
    print(f"Wrote panels.json ({len(panels_list)} panels)")


def _parse_tool_limits(bootui_root: str) -> dict[str, int]:
    tool_catalog = _fs_path(bootui_root) / (
        "bootui-engine/src/main/java/io/github/jdubois/bootui/engine/mcp/McpToolCatalog.java"
    )
    tool_catalog_code = tool_catalog.read_text(encoding="utf-8")
    limits_block = re.search(r"DEFAULT_LIMITS\s*=\s*Map\.ofEntries\((.*?)\);", tool_catalog_code, re.DOTALL)
    assert limits_block, "Could not find BootUI McpToolCatalog.DEFAULT_LIMITS"
    source_constants: dict[str, dict[str, int]] = {}
    for source_file in _iter_java_files(bootui_root):
        if "/src/main/java/" not in _rel_posix(source_file, bootui_root):
            continue
        source = source_file.read_text(encoding="utf-8", errors="ignore")
        class_match = re.search(r"\b(?:class|record|enum)\s+(\w+)", source)
        if class_match:
            for name, value in re.findall(r"static\s+final\s+int\s+(\w+)\s*=\s*(\d+)\s*;", source):
                source_constants.setdefault(class_match.group(1), {})[name] = int(value)
    default_limits: dict[str, int] = {}
    for name, expression in re.findall(r'Map\.entry\("([^"]+)",\s*([\w.]+)\)', limits_block.group(1)):
        if expression.isdecimal():
            default_limits[name] = int(expression)
        else:
            owner, constant = expression.rsplit(".", 1)
            default_limits[name] = source_constants[owner][constant]
    return default_limits


def _tool_annotations(name: str, action: bool) -> dict[str, bool]:
    if not action:
        return {"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False}
    destructive = name.startswith("clear_") or name == "enable_low_footprint"
    idempotent = (
        destructive or name.startswith("pause_") or name.startswith("resume_") or name == "disable_low_footprint"
    )
    return {
        "readOnlyHint": False,
        "destructiveHint": destructive,
        "idempotentHint": idempotent,
        "openWorldHint": name == "vulnerabilities_scan",
    }


def _tool_input_schema(tool: str, schema_name: str, default_limits: dict[str, int]) -> dict[str, object]:
    props: dict[str, object] = {}
    required: list[str] = []

    if schema_name == "LIMIT":
        compacted = default_limits.get(tool)
        default_limit = compacted if compacted is not None else 100
        meaning = (
            "Optional number of routes each ranking criterion contributes"
            if tool == "get_http_routes"
            else "Optional maximum number of items to return"
        )
        limit_note = " (the server's limit)" if compacted is None else ""
        desc = f"{meaning}; default {default_limit}{limit_note}, capped by the bootui.mcp.max-results server limit."
        props["limit"] = {"type": "integer", "minimum": 1, "default": default_limit, "description": desc}
    elif schema_name == "QUERY_LIMIT":
        compacted = default_limits.get(tool)
        default_limit = compacted if compacted is not None else 100
        limit_note = " (the server's limit)" if compacted is None else ""
        desc = (
            f"Optional maximum number of items to return; default {default_limit}{limit_note}, "
            "capped by the bootui.mcp.max-results server limit."
        )
        props["query"] = {"type": "string", "description": "Optional case-insensitive filter applied to the results."}
        props["limit"] = {"type": "integer", "minimum": 1, "default": default_limit, "description": desc}
    elif schema_name == "QUERY":
        props["query"] = {"type": "string", "description": "Optional case-insensitive filter applied to the results."}
    elif schema_name == "ID":
        props["id"] = {"type": "string", "description": "Exact identifier of the resource to fetch."}
        required.append("id")
    elif schema_name == "OPTIONAL_ID":
        props["id"] = {
            "type": "string",
            "description": "Optional identifier; omitted selects the tool's documented default.",
        }
    elif schema_name == "RULE_VIOLATIONS":
        report = tool.replace("_rule_violations", "_report")
        props["id"] = {"type": "string", "minLength": 1, "description": f"The rule id, from {report}."}
        required.append("id")
        props["scanId"] = {
            "type": "string",
            "minLength": 1,
            "description": "The cached report's violationDetails.scanId. Never starts a scan.",
        }
        required.append("scanId")
        props["offset"] = {
            "type": "integer",
            "minimum": 0,
            "default": 0,
            "description": (
                "Zero-based offset into the retained violations; advance it by page.returned while page.hasMore."
            ),
        }
        props["limit"] = {
            "type": "integer",
            "minimum": 1,
            "default": 100,
            "description": "Page size, default 100, capped at min(1000, bootui.mcp.max-results).",
        }

    schema_obj: dict[str, object] = {"type": "object", "properties": props, "additionalProperties": False}
    if required:
        schema_obj["required"] = required
    return schema_obj


def _capture_tools(bootui_root: str, output_dir: str) -> None:
    tools_file = f"{bootui_root}/bootui-cli/src/main/resources/bootui-tools.json"
    with open(tools_file, encoding="utf-8") as f:
        raw_tools = json.load(f).get("tools", [])

    default_limits = _parse_tool_limits(bootui_root)
    decorated_tools = []
    for t in raw_tools:
        name = t["name"]
        action = t.get("action", False)
        schema_name = t.get("schema", "NONE")
        t_copy = dict(t)
        t_copy["annotations"] = _tool_annotations(name, action)
        if name in default_limits:
            t_copy["defaultLimit"] = default_limits[name]
        t_copy["inputSchema"] = _tool_input_schema(name, schema_name, default_limits)
        decorated_tools.append(t_copy)

    with open(f"{output_dir}/tools.json", "w", encoding="utf-8", newline="\n") as f:
        json.dump({"tools": decorated_tools}, f, indent=2)
    print(f"Wrote tools.json ({len(decorated_tools)} tools)")


def _extract_catalog_routes(catalog_code: str) -> tuple[list[dict], list[dict]]:
    reads = []
    read_call_regex = re.compile(
        r'(?:read|capabilityList|pagedCapabilityList|pagedList|memory|advisor|locatedAdvisor|inventory|capture|agent|array)\(\s*"([^"]+)"\s*,\s*"([^"]+)"'
    )
    seen_reads = set()
    for m in read_call_regex.finditer(catalog_code):
        panel, path = m.groups()
        if ("GET", path) not in seen_reads:
            seen_reads.add(("GET", path))
            reads.append(
                {
                    "method": "GET",
                    "path": path,
                    "panel": panel,
                    "operationId": f"read_{panel.replace('-', '_')}",
                    "runtimes": ["SPRING_MVC", "SPRING_WEBFLUX", "QUARKUS"],
                }
            )

    actions = []
    action_call_regex = re.compile(
        r'(?:all|spring|springMvc|quarkus|infrastructure)\(\s*actions\s*,\s*"([^"]+)"\s*(?:,\s*"([^"]+)")?\s*,\s*"([^"]+)"\s*,\s*"([^"]+)"'
    )
    seen_actions = set()
    for m in action_call_regex.finditer(catalog_code):
        action_id, panel, method, path = m.groups()
        if (method, path) not in seen_actions:
            seen_actions.add((method, path))
            actions.append(
                {
                    "id": action_id,
                    "method": method,
                    "path": path,
                    "panel": panel if panel is not None else None,
                    "runtimes": ["SPRING_MVC", "SPRING_WEBFLUX", "QUARKUS"],
                }
            )
    return reads, actions


_MAPPING_REASONS = {
    "infrastructure": "Infrastructure receiver/endpoint outside panel API catalog",
    "transport": "Protocol transport endpoint, not a panel read/action",
    "framework-introspection": "Framework introspection metadata endpoint",
    "session-management": "Session management endpoint outside catalog",
    "uncatalogued-starter-endpoint": "Starter mapping absent from BootUI contract catalog",
}


def _classify_unmatched_mapping(mapping: dict[str, object]) -> None:
    path = str(mapping["path"])
    classification = (
        "infrastructure"
        if "/otlp/" in path
        else "transport"
        if path.startswith(("/cli", "/mcp", "/stream", "/events"))
        else "framework-introspection"
        if path.startswith(("/panels", "/mappings"))
        else "session-management"
        if "session" in path
        else "uncatalogued-starter-endpoint"
    )
    mapping["classification"] = classification
    mapping["reason"] = _MAPPING_REASONS[classification]


def _extract_starter_mappings(bootui_root: str) -> tuple[list[dict], list[dict]]:
    starter_src = _fs_path(bootui_root) / "bootui-spring-boot-starter/src/main/java"
    starter_controllers = _iter_java_files(starter_src)
    starter_mappings = []
    source_by_class: dict[str, str] = {}
    prefix_by_class: dict[str, str] = {}
    parent_by_class: dict[str, str] = {}
    file_by_class: dict[str, Path] = {}
    for cp in starter_controllers:
        ccode = cp.read_text(encoding="utf-8")
        ccode = re.sub(r"/\*.*?\*/", "", ccode, flags=re.DOTALL)
        ccode = re.sub(r"//[^\n]*", "", ccode)
        cm = re.search(
            r'@RequestMapping\(\s*(?:(?:path|value)\s*=\s*)?"([^"]*)"\s*\)\s*(?:@\w+(?:\([^)]*\))?\s*)*(?:public\s+)?(?:final\s+)?class',
            ccode,
        )
        prefix = cm.group(1) if cm else ""
        prefix = re.sub(r"^\$\{[^}]*\}", "", prefix).replace("/api}", "").replace("/bootui/api", "")
        class_match = re.search(r"\bclass\s+(\w+)(?:\s+extends\s+(\w+))?", ccode)
        if class_match:
            class_name, parent_name = class_match.groups()
            source_by_class[class_name] = ccode
            prefix_by_class[class_name] = prefix
            file_by_class[class_name] = cp
            if parent_name:
                parent_by_class[class_name] = parent_name
        for match in re.finditer(r"@(Get|Post|Delete|Put|Patch)Mapping\b(\s*\((?:[^()]|\([^()]*\))*\))?", ccode):
            method, args = match.group(1).upper(), match.group(2) or ""
            for suffix in re.findall(r'"([^"]*)"', args) or [""]:
                path = (prefix + suffix).replace("//", "/") or "/"
                if not path.startswith("/"):
                    path = "/" + path
                starter_mappings.append(
                    {
                        "controller": cp.name,
                        "source": _rel_posix(cp, bootui_root),
                        "line": ccode[: match.start()].count("\n") + 1,
                        "verb": method,
                        "path": path,
                    }
                )

    inherited_mappings = []
    for child, parent in parent_by_class.items():
        parent_source = source_by_class.get(parent, "")
        prefix = prefix_by_class[child]
        child_source = _rel_posix(file_by_class[child], bootui_root) if child in file_by_class else f"{child}.java"
        for match in re.finditer(
            r"@(Get|Post|Delete|Put|Patch)Mapping\b(\s*\((?:[^()]|\([^()]*\))*\))?", parent_source
        ):
            method, args = match.group(1).upper(), match.group(2) or ""
            for suffix in re.findall(r'"([^"]*)"', args) or [""]:
                path = (prefix + suffix).replace("//", "/") or "/"
                if not path.startswith("/"):
                    path = "/" + path
                inherited_mappings.append(
                    {
                        "controller": f"{child}.java",
                        "source": child_source,
                        "line": parent_source[: match.start()].count("\n") + 1,
                        "verb": method,
                        "path": path,
                    }
                )
    return starter_mappings, inherited_mappings


def _cross_check_routes(
    catalog_routes: list[tuple[str, str]],
    starter_mappings: list[dict],
    inherited_mappings: list[dict],
    catalog_code: str,
    catalog_rel_path: str = (
        "bootui-conformance/src/main/java/io/github/jdubois/bootui/conformance/BootUiApiContractCatalog.java"
    ),
) -> tuple[list[dict], list[dict]]:
    def path_matches(concrete: str, template: str) -> bool:
        route_parts = concrete.split("?", 1)[0].strip("/").split("/")
        template_parts = template.split("?", 1)[0].strip("/").split("/")
        return len(route_parts) == len(template_parts) and all(
            left == right or "{" in left or "{" in right
            for left, right in zip(route_parts, template_parts, strict=True)
        )

    def is_catalog_mapping(method: str, path: str) -> bool:
        return any(
            method == catalog_method and path_matches(path, template) for catalog_method, template in catalog_routes
        )

    all_starter = [*starter_mappings, *inherited_mappings]
    unmatched = [m for m in starter_mappings if not is_catalog_mapping(m["verb"], m["path"])]
    catalog_only = [
        {"method": method, "path": path}
        for method, path in catalog_routes
        if not any(mapping["verb"] == method and path_matches(mapping["path"], path) for mapping in all_starter)
    ]

    for mapping in [*unmatched, *inherited_mappings]:
        if not is_catalog_mapping(mapping["verb"], mapping["path"]):
            _classify_unmatched_mapping(mapping)

    route_gaps = []
    for route in catalog_only:
        if route["method"] == "POST" and route["path"] == "/dev-services/services/conformance/restart":
            mapping = next(
                m for m in starter_mappings if m["verb"] == "POST" and m["path"] == "/dev-services/{id}/restart"
            )
            catalog_match = re.search(re.escape(route["path"]), catalog_code)
            catalog_line = catalog_code[: catalog_match.start()].count("\n") + 1 if catalog_match else 1
            starter_line = mapping.get("line", 1)
            route_gaps.append(
                {
                    "category": "catalog-without-mapping",
                    "method": route["method"],
                    "path": route["path"],
                    "catalogSource": f"{catalog_rel_path}:{catalog_line}",
                    "starterSource": f"{mapping['source']}:{starter_line}",
                    "reason": "BootUI catalog names the conformance service while the starter mapping accepts an id",
                }
            )
        else:
            route_gaps.append({"category": "catalog-without-mapping", "method": route["method"], "path": route["path"]})

    unpanelled_routes = [m for m in unmatched if m["verb"] == "GET"]
    cross_check_gaps = [{"category": "starter-without-catalog", **mapping} for mapping in unmatched] + route_gaps
    return cross_check_gaps, unpanelled_routes


def _capture_routes(bootui_root: str, output_dir: str) -> tuple[int, int, int, int, int]:
    catalog_rel = "bootui-conformance/src/main/java/io/github/jdubois/bootui/conformance/BootUiApiContractCatalog.java"
    catalog_file = _fs_path(bootui_root) / catalog_rel
    catalog_code = catalog_file.read_text(encoding="utf-8")

    reads, actions = _extract_catalog_routes(catalog_code)
    starter_mappings, inherited_mappings = _extract_starter_mappings(bootui_root)
    catalog_routes = [(r["method"], r["path"]) for r in reads] + [(a["method"], a["path"]) for a in actions]
    cross_check_gaps, unpanelled_routes = _cross_check_routes(
        catalog_routes, starter_mappings, inherited_mappings, catalog_code, catalog_rel
    )

    routes_out = {
        "reads": reads,
        "actions": actions,
        "crossCheck": {
            "starterMappingsCount": len(starter_mappings),
            "starterMappings": starter_mappings,
            "inheritedMappings": inherited_mappings,
            "unpanelledRoutes": unpanelled_routes,
            "gaps": cross_check_gaps,
        },
    }
    with open(_fs_path(output_dir) / "routes.json", "w", encoding="utf-8", newline="\n") as f:
        json.dump(routes_out, f, indent=2)
    print(f"Wrote routes.json ({len(reads)} reads, {len(actions)} actions)")
    return len(reads), len(actions), len(starter_mappings), len(cross_check_gaps), len(unpanelled_routes)


def _apply_doc_table_row(line: str, fname: str, doc_rules: dict[str, dict[str, object]]) -> None:
    tm = re.match(r"^\|\s*([A-Z0-9_\-\.,\s]+)\s*\|\s*([^|]+)\|\s*([^|]+)\|", line)
    if not tm:
        return
    status = tm.group(2).strip()
    explanation = f"Retired: {tm.group(3).strip()}" if status == "Retired" else None
    for raw_id in tm.group(1).split(","):
        trid = raw_id.strip()
        if not re.match(r"^[A-Z]+-[A-Z0-9]+-\d+$", trid):
            continue
        if doc_rules.get(trid, {}).get("retired") and explanation is None:
            continue
        doc_rules[trid] = {
            "id": trid,
            "title": status,
            "source": fname,
            "retired": explanation is not None,
            "retiredExplanation": explanation,
        }


def _apply_doc_retired_sections(text: str, fname: str, doc_rules: dict[str, dict[str, object]]) -> None:
    for heading in ("Retired rules", "Retired rule IDs"):
        retired_section = re.search(rf"(?ms)^## {re.escape(heading)}\s*\n(.*?)(?=^## |\Z)", text)
        if retired_section:
            for row in re.finditer(r"(?m)^\|\s*([A-Z][A-Z0-9]*(?:-[A-Z0-9]+)+)\s*\|([^\n]+)", retired_section.group(1)):
                rid, columns = row.groups()
                explanation = "Retired: " + " ".join(columns.strip().strip("|").split("|")[-1].split())
                doc_rules[rid] = {
                    "id": rid,
                    "title": "Retired",
                    "source": fname,
                    "retired": True,
                    "retiredExplanation": explanation,
                }
    for row in re.finditer(r"(?m)^\|\s*(PT-[A-Z0-9-]+)\s*\|\s*REMOVE\s*\|([^\n]+)", text):
        rid, columns = row.groups()
        explanation = "Retired: " + " ".join(columns.strip().strip("|").split("|")[0].split())
        doc_rules[rid] = {
            "id": rid,
            "title": "Retired",
            "source": fname,
            "retired": True,
            "retiredExplanation": explanation,
        }


def _collect_doc_rules(bootui_root: str) -> dict[str, dict[str, object]]:
    doc_rules: dict[str, dict[str, object]] = {}
    docs_dir = _fs_path(bootui_root) / "docs"
    check_md_files = sorted(docs_dir.glob("*-CHECKS.md")) if docs_dir.exists() else []
    for fpath in check_md_files:
        fname = fpath.name
        text = fpath.read_text(encoding="utf-8")
        sections = {
            match.group(1): match.group(2)
            for match in re.finditer(r"(?ms)^###\s+([A-Z0-9_\-\.]+)\s+-.*?\n(.*?)(?=^###\s+|\Z)", text)
        }
        for raw_line in text.splitlines():
            line = raw_line.strip()
            m = re.match(r"^###\s+([A-Z0-9_\-\.]+)\s+-\s+(.*)", line)
            if m:
                rid, rtitle = m.groups()
                section = sections.get(rid, "")
                retirement = re.search(r"(?ms)^(\*\*Retired\.\*\*|Retired:)(.*?)(?=\n\s*\n|\Z)", section)
                explanation = " ".join((retirement.group(1) + retirement.group(2)).split()) if retirement else None
                doc_rules[rid] = {
                    "id": rid,
                    "title": rtitle,
                    "source": fname,
                    "retired": explanation is not None,
                    "retiredExplanation": explanation,
                }
            _apply_doc_table_row(line, fname, doc_rules)
        _apply_doc_retired_sections(text, fname, doc_rules)
    return doc_rules


def _collect_java_rules(bootui_root: str) -> dict[str, str]:
    java_rules: dict[str, str] = {}
    rule_pattern = re.compile(r'"([A-Z][A-Z0-9]*(?:-[A-Z0-9]+)+)"')

    for jf in _iter_java_files(bootui_root):
        jf_norm = _rel_posix(jf, bootui_root)
        if "/src/main/java/" not in f"/{jf_norm}" or "DocsCommand.java" in jf_norm:
            continue
        jcode = jf.read_text(encoding="utf-8", errors="ignore")
        for match in rule_pattern.finditer(jcode):
            cand = match.group(1)
            if re.match(
                r"^(ARCH|SPRING|HIB|CRAC|GRAAL|GRAALVM|SEC|MEM|PENTEST|PT|REST|RAPI|QUARKUS|QA|QS|VULN|DB|JVM)-", cand
            ):
                java_rules[cand] = jf_norm
        if "SpringRules.java" in jf_norm:
            for sm in re.finditer(r'super\(\s*"([A-Z0-9]+-\d+)"\s*,\s*"([^"]+)"', jcode):
                s_id = "SPRING-" + sm.group(1)
                java_rules[s_id] = jf_norm
    return java_rules


def _collect_java_retired_rules(bootui_root: str) -> dict[str, str]:
    java_retired: dict[str, str] = {}
    for jf in _iter_java_files(bootui_root):
        jf_norm = _rel_posix(jf, bootui_root)
        if "/src/main/java/" not in f"/{jf_norm}" or "DocsCommand.java" in jf_norm:
            continue
        jcode = jf.read_text(encoding="utf-8", errors="ignore")
        for m in re.finditer(r"\bRETIRED_(?:RULE_IDS|CHECK_IDS|RULES)\s*=\s*Set\.of\((.*?)\);", jcode, re.DOTALL):
            for rid in re.findall(r'"([A-Z0-9-]+)"', m.group(1)):
                java_retired.setdefault(rid, f"Retired: reserved in {jf.name}")
        if "/restapi/" in jf_norm:
            classes = re.finditer(
                r"(?s)(?:final\s+)?class\s+\w+\s+extends\s+AbstractRestApiRule\s*\{(.*?)(?=\n(?:final\s+)?class\s+|\Z)",
                jcode,
            )
            for rule_class in classes:
                body = rule_class.group(1)
                rid_match = re.search(r'new\s+RestApiRuleDefinition\(\s*"(RAPI-[A-Z0-9-]+)"', body)
                evaluate = re.search(
                    r"(?s)doEvaluate\s*\([^)]*\)\s*\{\s*return\s+RestApiRuleSupport\.skipped\("
                    r"\s*definition\(\)\s*,(.*?)\);\s*\}",
                    body,
                )
                if rid_match and evaluate:
                    reason = "".join(re.findall(r'"((?:\\.|[^"\\])*)"', evaluate.group(1)))
                    if reason.startswith("Retired heuristic:"):
                        java_retired[rid_match.group(1)] = reason
    return java_retired


def _collect_reviewer_union(bootui_root: str, reviewer_rule_id: re.Pattern[str]) -> tuple[set[str], dict[str, str]]:
    reviewer_docs = {}
    docs_dir = _fs_path(bootui_root) / "docs"
    if docs_dir.exists():
        for fpath in sorted(docs_dir.rglob("*.md")):
            content = fpath.read_text(encoding="utf-8")
            for match in re.finditer(rf"^###\s+({reviewer_rule_id.pattern})\b", content, re.MULTILINE):
                reviewer_docs[match.group(1)] = _rel_posix(fpath, bootui_root)

    reviewer_java = {}
    for fpath in _iter_java_files(bootui_root):
        rel = _rel_posix(fpath, bootui_root)
        if "/src/main/java/" not in f"/{rel}" or "DocsCommand.java" in rel:
            continue
        content = fpath.read_text(encoding="utf-8", errors="ignore")
        for match in re.finditer(rf'"({reviewer_rule_id.pattern})"', content):
            reviewer_java[match.group(1)] = rel

    return set(reviewer_docs) | set(reviewer_java), reviewer_java


def _build_rule_exclusions(
    reviewer_union: set[str],
    fixture_rule_ids: set[str],
    reviewer_java: dict[str, str],
) -> list[dict[str, str]]:
    rule_exclusions = []
    for rid in sorted(reviewer_union - fixture_rule_ids):
        if rid in {"SHA-256", "SHA-512"}:
            reason = f"{rid} is a digest algorithm label in Java code, not a rule identifier."
            source = reviewer_java[rid]
        elif rid.startswith("BOOTUI-COMPAT-"):
            source = reviewer_java[rid]
            reason = (
                f"{rid} is a platform compatibility diagnostic identifier in PlatformCompatibility.java, "
                "not an advisor rule."
            )
        elif f"SPRING-{rid}" in fixture_rule_ids and any(
            path.endswith("SpringRules.java") for path in reviewer_java.values()
        ):
            source = next(path for path in reviewer_java.values() if path.endswith("SpringRules.java"))
            reason = (
                "SpringRules stores the shorthand; AbstractSpringRule adds the SPRING- prefix, "
                f"so the canonical entry is SPRING-{rid}."
            )
        else:
            raise ValueError(f"Unclassified independent rule id: {rid}")
        rule_exclusions.append({"id": rid, "source": source, "reason": reason})
    return rule_exclusions


def _build_rule_additions(
    bootui_root: str,
    fixture_rule_ids: set[str],
    reviewer_union: set[str],
    java_rules: dict[str, str],
    reviewer_rule_id: re.Pattern[str],
) -> list[dict[str, str]]:
    rule_additions = []
    docs_dir = _fs_path(bootui_root) / "docs"
    check_md_files = sorted(docs_dir.glob("*-CHECKS.md")) if docs_dir.exists() else []
    for rid in sorted(fixture_rule_ids - reviewer_union):
        source = next(
            (
                _rel_posix(fpath, bootui_root)
                for fpath in check_md_files
                if re.search(rf"^\|\s*{re.escape(rid)}(?:\s*,|\s*\|)", fpath.read_text(encoding="utf-8"), re.MULTILINE)
            ),
            None,
        )
        if source:
            reason = "Documented in a rule table; the independent counter scans headings and Java literals only."
        elif not reviewer_rule_id.fullmatch(rid) and rid.startswith("QS-"):
            source = java_rules.get(rid)
            reason = (
                "Valid non-numeric Quarkus security identifier; the independent counter requires a three-digit suffix."
            )
        else:
            raise ValueError(f"Unclassified fixture-only rule id: {rid}")
        rule_additions.append({"id": rid, "source": source, "reason": reason})
    return rule_additions


def _build_diff_explanations(
    in_doc_only: list[str],
    in_java_only: list[str],
    doc_rules: dict[str, dict],
    java_rules: dict[str, str] | None = None,
    java_retired: dict[str, str] | None = None,
) -> dict[str, str]:
    java_rules = java_rules or {}
    java_retired = java_retired or {}
    diff_explanations: dict[str, str] = {}
    for rid in in_doc_only:
        r_info = doc_rules.get(rid, {})
        if r_info.get("retired"):
            diff_explanations[rid] = str(r_info["retiredExplanation"])
        elif rid in java_retired:
            diff_explanations[rid] = java_retired[rid]
        elif "HIB" in rid:
            diff_explanations[rid] = "Documented Hibernate check; retired or Jakarta Persistence implicit default"
        elif "DB-" in rid:
            diff_explanations[rid] = "Documented database schema check"
        else:
            diff_explanations[rid] = f"Documented check specification in {r_info.get('source')}"
    for rid in in_java_only:
        if rid in java_retired:
            diff_explanations[rid] = java_retired[rid]
        elif "MEM-" in rid:
            diff_explanations[rid] = "Runtime memory check rule implemented in engine MemoryRules.java"
        elif "ARCH-" in rid:
            diff_explanations[rid] = "Architecture check rule constant in ArchitectureRules.java"
        elif "QS-" in rid:
            diff_explanations[rid] = "Quarkus security check constant in QuarkusSecurityChecks.java"
        else:
            diff_explanations[rid] = f"Internal rule constant in {os.path.basename(java_rules.get(rid, ''))}"
    return diff_explanations


def _reconcile_rule_ids(
    bootui_root: str,
    rules_list: list[dict],
    doc_rules: dict[str, dict],
    java_rules: dict[str, str],
    java_retired: dict[str, str] | None = None,
) -> tuple[dict[str, object], list[str], list[str], dict[str, str]]:
    reviewer_rule_id = re.compile(r"[A-Z][A-Z0-9]*(?:-[A-Z0-9]+)*-\d{3}")
    reviewer_union, reviewer_java = _collect_reviewer_union(bootui_root, reviewer_rule_id)
    fixture_rule_ids = {rule["id"] for rule in rules_list}

    rule_exclusions = _build_rule_exclusions(reviewer_union, fixture_rule_ids, reviewer_java)
    rule_additions = _build_rule_additions(bootui_root, fixture_rule_ids, reviewer_union, java_rules, reviewer_rule_id)

    rule_reconciliation = {
        "independentUnionCount": len(reviewer_union),
        "fixtureCount": len(fixture_rule_ids),
        "independentIdsExcluded": rule_exclusions,
        "fixtureIdsOutsideIndependentCounter": rule_additions,
        "method": (
            "All docs/**/*.md heading IDs plus src/main/java quoted IDs matching the independent "
            "counter pattern; table-only and non-three-digit fixture IDs are listed with reasons"
        ),
    }

    in_doc_only = sorted(set(doc_rules.keys()) - set(java_rules.keys()))
    in_java_only = sorted(set(java_rules.keys()) - set(doc_rules.keys()))
    diff_explanations = _build_diff_explanations(in_doc_only, in_java_only, doc_rules, java_rules, java_retired)

    return rule_reconciliation, in_doc_only, in_java_only, diff_explanations


def _capture_rules(bootui_root: str, output_dir: str) -> None:
    doc_rules = _collect_doc_rules(bootui_root)
    java_rules = _collect_java_rules(bootui_root)
    java_retired = _collect_java_retired_rules(bootui_root)

    all_rule_ids = sorted(set(doc_rules.keys()) | set(java_rules.keys()))
    rules_list = []
    for rid in all_rule_ids:
        r_info = doc_rules.get(rid, {})
        is_retired = bool(r_info.get("retired", False) or rid in java_retired)
        java_reason = java_retired.get(rid)
        retired_exp = (
            java_reason
            if java_reason and java_reason.startswith("Retired heuristic:")
            else r_info.get("retiredExplanation") or java_reason
        )
        title = str(r_info.get("title", "")) or ("Retired" if is_retired else "")
        rules_list.append(
            {
                "id": rid,
                "title": title,
                "docSource": r_info.get("source"),
                "javaSource": java_rules.get(rid),
                "inDocs": rid in doc_rules,
                "inJava": rid in java_rules,
                "retired": is_retired,
                "retiredExplanation": retired_exp,
            }
        )

    rule_reconciliation, in_doc_only, in_java_only, diff_explanations = _reconcile_rule_ids(
        bootui_root, rules_list, doc_rules, java_rules, java_retired
    )

    with open(_fs_path(output_dir) / "rule-ids.json", "w", encoding="utf-8", newline="\n") as f:
        json.dump({"rules": rules_list, "total": len(rules_list), "reconciliation": rule_reconciliation}, f, indent=2)
    print(f"Wrote rule-ids.json ({len(rules_list)} rules)")

    with open(_fs_path(output_dir) / "rule-ids-diff.json", "w", encoding="utf-8", newline="\n") as f:
        json.dump(
            {
                "inDocOnlyCount": len(in_doc_only),
                "inJavaOnlyCount": len(in_java_only),
                "inDocOnly": in_doc_only,
                "inJavaOnly": in_java_only,
                "docCount": len(doc_rules),
                "javaCount": len(java_rules),
                "unionCount": len(all_rule_ids),
                "explanations": diff_explanations,
            },
            f,
            indent=2,
        )
    print(f"Wrote rule-ids-diff.json (inDocOnly: {len(in_doc_only)}, inJavaOnly: {len(in_java_only)})")


def _scan_constants_file(
    source_file: Path,
    constants: dict[str, dict[str, object]],
    deferred_refs: list[tuple[str, str, str, str]],
) -> None:
    source = source_file.read_text(encoding="utf-8", errors="ignore")
    class_match = re.search(r"\b(?:class|record|enum)\s+(\w+)", source)
    if not class_match:
        return
    cls = class_match.group(1)
    cls_consts = constants.setdefault(cls, {})
    for name, val in re.findall(r'static\s+final\s+String\s+(\w+)\s*=\s*"([^"]*)"\s*;', source):
        cls_consts[name] = val
    for name, expr in re.findall(r"static\s+final\s+(?:int|long)\s+(\w+)\s*=\s*([\d_\s*L]+)\s*;", source):
        factors = [int(x.replace("_", "")) for x in re.findall(r"[\d_]+", expr) if x.replace("_", "")]
        if factors:
            cls_consts[name] = math.prod(factors)
    for name, unit, num in re.findall(
        r"static\s+final\s+Duration\s+(\w+)\s*=\s*Duration\.of(Seconds|Minutes|Millis|Days)\(\s*([\d_]+)\s*\)\s*;",
        source,
    ):
        n = int(num.replace("_", ""))
        suffix = {"Seconds": "s", "Minutes": "m", "Millis": "ms", "Days": "d"}[unit]
        cls_consts[name] = f"{n // 1000}s" if suffix == "ms" and n % 1000 == 0 else f"{n}{suffix}"
    for name, ref_cls, ref_name in re.findall(
        r"static\s+final\s+Duration\s+(\w+)\s*=\s*([A-Z]\w+)\.([A-Z0-9_]+)\s*;", source
    ):
        deferred_refs.append((cls, name, ref_cls, ref_name))
    for name, body in re.findall(
        r"static\s+final\s+List<String>\s+(\w+)\s*=\s*List\.of\((.*?)\)\s*;", source, re.DOTALL
    ):
        clean_body = re.sub(r"//[^\n]*", "", body)
        items: list[str] = []
        for token in [t.strip() for t in clean_body.split(",") if t.strip()]:
            if token.startswith('"') and token.endswith('"'):
                items.append(token[1:-1])
            elif token in cls_consts and isinstance(cls_consts[token], str):
                items.append(str(cls_consts[token]))
        cls_consts[name] = items


def _parse_java_constants(bootui_root: str) -> dict[str, dict[str, object]]:
    constants: dict[str, dict[str, object]] = {}
    deferred_refs: list[tuple[str, str, str, str]] = []
    for sub in ("bootui-engine", "bootui-spring-boot-starter"):
        for source_file in _iter_java_files(_fs_path(bootui_root) / sub):
            _scan_constants_file(source_file, constants, deferred_refs)
    for cls, name, ref_cls, ref_name in deferred_refs:
        if ref_cls in constants and ref_name in constants[ref_cls]:
            constants.setdefault(cls, {})[name] = constants[ref_cls][ref_name]
    return constants


def _parse_bootui_properties_fields(
    bootui_root: str,
) -> tuple[dict[tuple[str, str], tuple[int, str | None]], dict[str, str], int]:
    props_java = _fs_path(bootui_root) / (
        "bootui-spring-boot-starter/src/main/java/io/github/jdubois/bootui/autoconfigure/BootUiProperties.java"
    )
    if not props_java.exists():
        return {}, {}, 273
    lines = props_java.read_text(encoding="utf-8").splitlines()
    class_stack: list[tuple[str, int]] = []
    brace_depth = 0
    parent_by_class: dict[str, str] = {}
    fields: dict[tuple[str, str], tuple[int, str | None]] = {}
    api_path_return_line = 273

    for idx, raw_line in enumerate(lines, 1):
        clean = re.sub(r"//.*$", "", raw_line)
        cm = re.search(r"\bclass\s+(\w+)(?:\s+extends\s+(\w+))?", clean)
        if cm and "{" in clean:
            cname, pname = cm.groups()
            if pname:
                parent_by_class[cname] = pname
            class_stack.append((cname, brace_depth))
        if class_stack:
            cur_cls = class_stack[-1][0]
            fm = re.match(
                r"^\s*private\s+(?!static\s+final)(?:final\s+)?[\w<>, ?\[\].]+\s+(\w+)\s*(?:=\s*([^;]+))?;\s*$",
                clean,
            )
            if fm:
                fname, expr = fm.groups()
                fields[(cur_cls, fname)] = (idx, expr.strip() if expr is not None else None)
            if 'path + "/api"' in clean and "return" in clean:
                api_path_return_line = idx
        brace_depth += clean.count("{") - clean.count("}")
        while class_stack and brace_depth <= class_stack[-1][1]:
            class_stack.pop()

    return fields, parent_by_class, api_path_return_line


def _resolve_property_default(
    prop: dict[str, object],
    fields: dict[tuple[str, str], tuple[int, str | None]],
    parent_by_class: dict[str, str],
    api_path_return_line: int,
    constants: dict[str, dict[str, object]],
) -> tuple[object, str] | None:
    name = str(prop.get("name", ""))
    source_type = str(prop.get("sourceType", "io.github.jdubois.bootui.autoconfigure.BootUiProperties"))
    suffix = name.rsplit(".", 1)[-1]
    field_name = re.sub(r"-([a-z])", lambda m: m.group(1).upper(), suffix)
    cls_name = source_type.replace("$", ".").rsplit(".", 1)[-1]
    entry = fields.get((cls_name, field_name))
    if entry is None and cls_name in parent_by_class:
        entry = fields.get((parent_by_class[cls_name], field_name))
    if entry is None:
        return None
    line_no, expr = entry
    if expr is None or expr == "new LinkedHashMap<>()":
        return None, f"BootUiProperties.java:{line_no}"
    if expr == "null":
        if field_name == "apiPath":
            return "/bootui/api", f"BootUiProperties.java:{line_no},{api_path_return_line}"
        return None, f"BootUiProperties.java:{line_no}"
    if expr == "new ArrayList<>()":
        return [], f"BootUiProperties.java:{line_no}"
    if re.fullmatch(r"\d+(?:\s*\*\s*\d+)+L?", expr):
        factors = [int(x) for x in re.findall(r"\d+", expr)]
        return math.prod(factors), f"BootUiProperties.java:{line_no} ({expr})"
    ref_match = re.search(r"([A-Z]\w+)\.([A-Z0-9_]+)", expr)
    if ref_match:
        owner, const_name = ref_match.groups()
        val = constants.get(owner, {}).get(const_name)
        if expr.startswith("Duration.ofMillis(") and isinstance(val, int):
            val = f"{val // 1000}s" if val % 1000 == 0 else f"{val}ms"
        return val, f"BootUiProperties.java:{line_no} ({owner}.{const_name})"
    return None, f"BootUiProperties.java:{line_no}"


def _capture_properties(bootui_root: str, output_dir: str) -> None:
    base = _fs_path(bootui_root)
    metadata_file = base / "bootui-spring-boot-starter/target/classes/META-INF/spring-configuration-metadata.json"
    add_metadata_file = base / (
        "bootui-spring-boot-starter/src/main/resources/META-INF/additional-spring-configuration-metadata.json"
    )
    if not metadata_file.is_file():
        raise FileNotFoundError(f"Maven build did not generate required metadata: {metadata_file}")

    props_dict: dict[str, dict[str, object]] = {}
    for p in json.loads(metadata_file.read_text(encoding="utf-8")).get("properties", []):
        if str(p.get("name", "")).startswith("bootui."):
            props_dict[p["name"]] = dict(p)

    if add_metadata_file.is_file():
        for p in json.loads(add_metadata_file.read_text(encoding="utf-8")).get("properties", []):
            if str(p.get("name", "")).startswith("bootui."):
                props_dict[p["name"]] = dict(p)

    constants = _parse_java_constants(bootui_root)
    fields, parent_by_class, api_path_return_line = _parse_bootui_properties_fields(bootui_root)

    for p in props_dict.values():
        resolved = _resolve_property_default(p, fields, parent_by_class, api_path_return_line, constants)
        if resolved is not None:
            if "defaultValue" not in p or resolved[0] is not None:
                p["defaultValue"] = resolved[0]
            p["defaultValueSource"] = resolved[1]
        elif "defaultValue" not in p:
            p["defaultValue"] = None

    final_properties = sorted(props_dict.values(), key=lambda x: str(x["name"]))
    with open(_fs_path(output_dir) / "properties.json", "w", encoding="utf-8", newline="\n") as f:
        json.dump({"properties": final_properties, "total": len(final_properties)}, f, indent=2)
    print(f"Wrote properties.json ({len(final_properties)} properties)")


def _capture_tests(bootui_root: str, output_dir: str) -> tuple[int, int]:
    test_files = _iter_java_files(bootui_root)
    method_regex = re.compile(
        r"@(?:Test|ParameterizedTest|RepeatedTest|TestFactory)\b(?:\([^)]*\))?"
        r"(?:\s*@\w+(?:\([^)]*\))?)*"
        r"\s+(?:(?:public|protected|private|static|final|synchronized)\s+)*(?:void|[\w<>\[\],]+)\s+(\w+)\s*\("
    )
    arch_regex = re.compile(
        r"@ArchTest\b(?:\([^)]*\))?"
        r"(?:\s*@\w+(?:\([^)]*\))?)*"
        r"\s+(?:(?:public|protected|private|static|final)\s+)*(?:ArchRule|(?:void|[\w<>\[\],]+))\s+(\w+)\s*(?:\(|=)"
    )

    test_classes: dict[str, list[str]] = {}
    for tf in test_files:
        tcode = tf.read_text(encoding="utf-8", errors="ignore")
        clean = re.sub(r"/\*.*?\*/|//[^\n]*|\"(?:\\.|[^\"\\])*\"|'(?:\\.|[^'\\])*'", " ", tcode, flags=re.DOTALL)
        package = re.search(r"^\s*package\s+([\w.]+)\s*;", clean, re.MULTILINE)
        cmatches = list(
            re.finditer(
                r"(?:\b(?:public|protected|private|static|final|abstract|sealed|non-sealed)\s+)*class\s+(\w+)",
                clean,
            )
        )
        if not cmatches or not package:
            continue
        top_c = f"{package.group(1)}.{cmatches[0].group(1)}"

        meths = {mm.group(1) for mm in method_regex.finditer(clean)} | {
            mm.group(1) for mm in arch_regex.finditer(clean)
        }
        if meths:
            test_classes[top_c] = sorted(meths)

    sorted_test_classes = {cls: test_classes[cls] for cls in sorted(test_classes)}
    simple_names: dict[str, list[str]] = {}
    for fqcn in sorted_test_classes:
        simple_names.setdefault(fqcn.rsplit(".", 1)[-1], []).append(fqcn)
    simple_name_index = {
        name: {"classes": sorted(classes), "ambiguous": len(classes) > 1}
        for name, classes in sorted(simple_names.items())
    }

    with open(_fs_path(output_dir) / "bootui-tests.json", "w", encoding="utf-8", newline="\n") as f:
        json.dump(
            {
                "testClasses": sorted_test_classes,
                "simpleNameIndex": simple_name_index,
                "totalClasses": len(sorted_test_classes),
                "totalMethods": sum(len(m) for m in sorted_test_classes.values()),
            },
            f,
            indent=2,
        )
    print(f"Wrote bootui-tests.json ({len(sorted_test_classes)} test classes)")
    return len(sorted_test_classes), sum(len(m) for m in sorted_test_classes.values())


def capture(
    *,
    tag: str,
    commit: str,
    output_dir: Path | str,
    version: str,
    date: str,
    repo: Path | None = None,
) -> None:
    output_dir = str(Path(output_dir).resolve())
    if repo is None:
        repo = Path(os.environ.get("BOOTUI_GIT", Path(__file__).resolve().parents[1] / "boot-ui"))

    bootui_root, tag_object, maven_command, java_version_output, maven_version_output, settings_override = (
        _extract_and_build(repo, tag, version)
    )
    command = f"python scripts/capture_bootui.py --version {version}"
    meta = {
        "bootuiVersion": version,
        "app": "tiny-ledger",
        "profile": "full",
        "commit": commit,
        "tag": tag,
        "command": command,
        "tagObject": tag_object,
        "mavenCommand": " ".join(maven_command) + " -s <temporary settings override>",
        "javaVersionOutput": java_version_output,
        "mavenVersionOutput": maven_version_output,
        "settingsOverride": settings_override,
        "jdk": java_version_output,
        "captured": date,
        "fixtures": [
            "meta.json",
            "panels.json",
            "routes.json",
            "tools.json",
            "rule-ids.json",
            "rule-ids-diff.json",
            "properties.json",
            "bootui-tests.json",
        ],
    }
    with open(f"{output_dir}/meta.json", "w", encoding="utf-8", newline="\n") as f:
        json.dump(meta, f, indent=2)
    print("Wrote meta.json")

    _capture_panels(bootui_root, output_dir)
    _capture_tools(bootui_root, output_dir)
    reads, actions, mappings, gaps, unpanelled = _capture_routes(bootui_root, output_dir)
    _capture_rules(bootui_root, output_dir)
    _capture_properties(bootui_root, output_dir)
    test_classes, test_methods = _capture_tests(bootui_root, output_dir)

    meta["counts"] = {
        "reads": reads,
        "actions": actions,
        "starterMappings": mappings,
        "gaps": gaps,
        "unpanelledRoutes": unpanelled,
        "routeCountMethod": "catalog read/action helper calls and all starter src/main/java @*Mapping declarations",
        "testClasses": test_classes,
        "testMethods": test_methods,
    }
    with open(f"{output_dir}/meta.json", "w", encoding="utf-8", newline="\n") as f:
        json.dump(meta, f, indent=2)


_CAPTURE_VERSIONS = {
    "2.3.0": ("v2.3.0", "7c89042c6a0a47e1cb22d2df7412d2177d7416d1", "2026-11-10"),
    "2.4.0": ("v2.4.0", "0df7ed764688d04f83c246c9965e90158c1db488", "2026-11-18"),
    "2.5.0": ("v2.5.0", "c4458db8dd18c08074119f22a79dda3e714abbda", "2026-11-20"),
}


def main(version: str | None = None) -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Capture pinned BootUI tracker fixtures")
    parser.add_argument("--version", choices=tuple(_CAPTURE_VERSIONS), default=version)
    parser.add_argument("--output-dir", default=None)
    args = parser.parse_args([] if version is not None else None)
    if args.version is None:
        parser.error("--version is required")
    tag, commit, date = _CAPTURE_VERSIONS[args.version]
    repo = Path(os.environ.get("BOOTUI_GIT", Path(__file__).resolve().parents[1] / "boot-ui"))
    actual_commit = subprocess.check_output(
        ["git", "-C", str(repo), "rev-parse", f"{tag}^{{commit}}"], text=True
    ).strip()
    if actual_commit != commit:
        raise RuntimeError(f"Pinned tag resolves to {actual_commit}, expected {commit}")
    out = (
        Path(args.output_dir)
        if args.output_dir is not None
        else Path(__file__).resolve().parents[1] / f"tests/fixtures/bootui/{args.version}"
    )
    capture(
        tag=tag,
        commit=commit,
        output_dir=out,
        version=args.version,
        date=date,
        repo=repo,
    )


if __name__ == "__main__":
    main()
