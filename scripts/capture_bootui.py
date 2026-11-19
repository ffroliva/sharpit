import atexit
import glob
import json
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path


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
    tool_catalog = (
        Path(bootui_root) / "bootui-engine/src/main/java/io/github/jdubois/bootui/engine/mcp/McpToolCatalog.java"
    )
    tool_catalog_code = tool_catalog.read_text(encoding="utf-8")
    limits_block = re.search(r"DEFAULT_LIMITS\s*=\s*Map\.ofEntries\((.*?)\);", tool_catalog_code, re.DOTALL)
    assert limits_block, "Could not find BootUI McpToolCatalog.DEFAULT_LIMITS"
    source_constants: dict[str, dict[str, int]] = {}
    for source_file in glob.glob(f"{bootui_root}/**/src/main/java/**/*.java", recursive=True):
        source = Path(source_file).read_text(encoding="utf-8", errors="ignore")
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


def _extract_starter_mappings(bootui_root: str) -> tuple[list[dict], list[dict]]:
    starter_controllers = glob.glob(f"{bootui_root}/bootui-spring-boot-starter/src/main/java/**/*.java", recursive=True)
    starter_mappings = []
    source_by_class = {}
    prefix_by_class = {}
    parent_by_class = {}
    for cp in starter_controllers:
        ccode = Path(cp).read_text(encoding="utf-8")
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
            if parent_name:
                parent_by_class[class_name] = parent_name
        for match in re.finditer(r"@(Get|Post|Delete|Put|Patch)Mapping\b(\s*\((?:[^()]|\([^()]*\))*\))?", ccode):
            method, args = match.group(1).upper(), match.group(2) or ""
            for suffix in re.findall(r'"([^"]*)"', args) or [""]:
                path = (prefix + suffix).replace("//", "/") or "/"
                starter_mappings.append(
                    {"verb": method, "path": path, "source": Path(cp).relative_to(bootui_root).as_posix()}
                )

    inherited_mappings = []
    for child, parent in parent_by_class.items():
        parent_source = source_by_class.get(parent, "")
        prefix = prefix_by_class[child]
        for match in re.finditer(
            r"@(Get|Post|Delete|Put|Patch)Mapping\b(\s*\((?:[^()]|\([^()]*\))*\))?", parent_source
        ):
            method, args = match.group(1).upper(), match.group(2) or ""
            for suffix in re.findall(r'"([^"]*)"', args) or [""]:
                path = (prefix + suffix).replace("//", "/") or "/"
                inherited_mappings.append(
                    {
                        "verb": method,
                        "path": path,
                        "source": f"inherited:{child}->{parent}",
                        "classification": "inherited-controller-action",
                    }
                )
    return starter_mappings, inherited_mappings


def _cross_check_routes(
    catalog_routes: list[tuple[str, str]],
    starter_mappings: list[dict],
    inherited_mappings: list[dict],
    catalog_code: str,
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
    starter_only = [m for m in all_starter if not is_catalog_mapping(m["verb"], m["path"])]
    catalog_only = [
        {"method": method, "path": path}
        for method, path in catalog_routes
        if not any(mapping["verb"] == method and path_matches(mapping["path"], path) for mapping in all_starter)
    ]

    cross_check_gaps = []
    for route in catalog_only:
        if route["method"] == "POST" and route["path"] == "/dev-services/services/conformance/restart":
            mapping = next(
                m for m in starter_mappings if m["verb"] == "POST" and m["path"] == "/dev-services/{id}/restart"
            )
            catalog_match = re.search(re.escape(route["path"]), catalog_code)
            catalog_line = catalog_code[: catalog_match.start()].count("\n") + 1 if catalog_match else 1
            starter_lines = (
                Path(mapping["source"]).read_text(encoding="utf-8").splitlines()
                if Path(mapping["source"]).is_file()
                else []
            )
            starter_line = next(
                (
                    idx + 1
                    for idx, line in enumerate(starter_lines)
                    if "@PostMapping" in line and "{id}/restart" in line
                ),
                1,
            )
            cross_check_gaps.append(
                {
                    "method": route["method"],
                    "path": route["path"],
                    "category": "catalog-without-mapping",
                    "reason": (
                        "DevServicesController maps POST /dev-services/{id}/restart; "
                        "catalog registers /dev-services/services/conformance/restart"
                    ),
                    "catalogSource": f"bootui-conformance/.../BootUiApiContractCatalog.java:{catalog_line}",
                    "starterSource": f"{mapping['source']}:{starter_line}",
                }
            )

    unpanelled_routes = []
    for item in starter_only:
        if item.get("classification") != "inherited-controller-action":
            item["classification"] = "sse-stream" if "stream" in item["path"] else "unpanelled-endpoint"
            if item["verb"] == "GET":
                unpanelled_routes.append(item["path"])

    cross_check_gaps.extend(starter_only)
    return cross_check_gaps, unpanelled_routes


def _capture_routes(bootui_root: str, output_dir: str) -> tuple[int, int, int, int, int]:
    catalog_file = (
        f"{bootui_root}/bootui-conformance/src/main/java/io/github/jdubois/bootui/"
        "conformance/BootUiApiContractCatalog.java"
    )
    with open(catalog_file, encoding="utf-8") as f:
        catalog_code = f.read()

    reads, actions = _extract_catalog_routes(catalog_code)
    starter_mappings, inherited_mappings = _extract_starter_mappings(bootui_root)
    catalog_routes = [(r["method"], r["path"]) for r in reads] + [(a["method"], a["path"]) for a in actions]
    cross_check_gaps, unpanelled_routes = _cross_check_routes(
        catalog_routes, starter_mappings, inherited_mappings, catalog_code
    )

    routes_out = {
        "reads": reads,
        "actions": actions,
        "crossCheck": {
            "starterMappings": starter_mappings,
            "inheritedMappings": inherited_mappings,
            "unpanelledRoutes": unpanelled_routes,
            "gaps": cross_check_gaps,
        },
    }
    with open(f"{output_dir}/routes.json", "w", encoding="utf-8", newline="\n") as f:
        json.dump(routes_out, f, indent=2)
    print(f"Wrote routes.json ({len(reads)} reads, {len(actions)} actions)")
    return len(reads), len(actions), len(starter_mappings), len(cross_check_gaps), len(unpanelled_routes)


def _collect_doc_rules(bootui_root: str) -> dict[str, dict[str, object]]:
    doc_rules: dict[str, dict[str, object]] = {}
    check_md_files = glob.glob(f"{bootui_root}/docs/*-CHECKS.md")
    for fpath in check_md_files:
        fname = os.path.basename(fpath)
        with open(fpath, encoding="utf-8") as fp:
            text = fp.read()
            sections = {
                match.group(1): match.group(2)
                for match in re.finditer(r"(?ms)^###\s+([A-Z0-9_\-\.]+)\s+-.*?\n(.*?)(?=^###\s+|\Z)", text)
            }
            for line in text.splitlines():
                m = re.match(r"^###\s+([A-Z0-9_\-\.]+)\s+-\s+(.*)", line.strip())
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
                tm = re.match(r"^\|\s*([A-Z0-9_\-\.]+)\s*\|\s*([^|]+)\|\s*([^|]+)\|", line.strip())
                if tm and re.match(r"^[A-Z]+-[A-Z0-9]+-\d+$", tm.group(1).strip()):
                    trid = tm.group(1).strip()
                    status = tm.group(2).strip()
                    explanation = f"Retired: {tm.group(3).strip()}" if status == "Retired" else None
                    doc_rules[trid] = {
                        "id": trid,
                        "title": status,
                        "source": fname,
                        "retired": explanation is not None,
                        "retiredExplanation": explanation,
                    }

            for heading in ("Retired rules", "Retired rule IDs"):
                retired_section = re.search(rf"(?ms)^## {re.escape(heading)}\s*\n(.*?)(?=^## |\Z)", text)
                if retired_section:
                    for row in re.finditer(
                        r"(?m)^\|\s*([A-Z][A-Z0-9]*(?:-[A-Z0-9]+)+)\s*\|([^\n]+)", retired_section.group(1)
                    ):
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
    return doc_rules


def _collect_java_rules(bootui_root: str) -> dict[str, str]:
    java_rules: dict[str, str] = {}
    java_files = glob.glob(f"{bootui_root}/**/src/main/java/**/*.java", recursive=True)
    rule_pattern = re.compile(r'"([A-Z][A-Z0-9]*(?:-[A-Z0-9]+)+)"')

    for jf in java_files:
        jf_norm = jf.replace("\\", "/")
        if "DocsCommand.java" in jf_norm:
            continue
        with open(jf, encoding="utf-8", errors="ignore") as fp:
            jcode = fp.read()
        for match in rule_pattern.finditer(jcode):
            cand = match.group(1)
            if re.match(
                r"^(ARCH|SPRING|HIB|CRAC|GRAAL|GRAALVM|SEC|MEM|PENTEST|PT|REST|RAPI|QUARKUS|QA|QS|VULN|DB|JVM)-", cand
            ):
                java_rules[cand] = Path(jf).relative_to(bootui_root).as_posix()
        if "SpringRules.java" in jf_norm:
            for sm in re.finditer(r'super\(\s*"([A-Z0-9]+-\d+)"\s*,\s*"([^"]+)"', jcode):
                s_id = "SPRING-" + sm.group(1)
                java_rules[s_id] = Path(jf).relative_to(bootui_root).as_posix()
    return java_rules


def _collect_reviewer_union(bootui_root: str, reviewer_rule_id: re.Pattern[str]) -> tuple[set[str], dict[str, str]]:
    reviewer_docs = {}
    for fpath in glob.glob(f"{bootui_root}/docs/**/*.md", recursive=True):
        content = Path(fpath).read_text(encoding="utf-8")
        for match in re.finditer(rf"^###\s+({reviewer_rule_id.pattern})\b", content, re.MULTILINE):
            reviewer_docs[match.group(1)] = Path(fpath).relative_to(bootui_root).as_posix()

    reviewer_java = {}
    for fpath in glob.glob(f"{bootui_root}/**/src/main/java/**/*.java", recursive=True):
        if "DocsCommand.java" in fpath.replace("\\", "/"):
            continue
        content = Path(fpath).read_text(encoding="utf-8", errors="ignore")
        for match in re.finditer(rf'"({reviewer_rule_id.pattern})"', content):
            reviewer_java[match.group(1)] = Path(fpath).relative_to(bootui_root).as_posix()

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
    check_md_files = glob.glob(f"{bootui_root}/docs/*-CHECKS.md")
    for rid in sorted(fixture_rule_ids - reviewer_union):
        source = next(
            (
                Path(fpath).relative_to(bootui_root).as_posix()
                for fpath in check_md_files
                if re.search(rf"^\|\s*{re.escape(rid)}\s*\|", Path(fpath).read_text(encoding="utf-8"), re.MULTILINE)
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
) -> dict[str, str]:
    diff_explanations: dict[str, str] = {}
    for rid in in_doc_only:
        r_info = doc_rules.get(rid, {})
        if r_info.get("retired"):
            diff_explanations[rid] = str(r_info["retiredExplanation"])
        elif rid.startswith("SPRING-PROFILE-") or rid.startswith("SPRING-REACTIVE-"):
            diff_explanations[rid] = "Spring profile and reactive checks are planned"
        elif rid in {"HIB-SESSION-001", "HIB-STAT-001"}:
            diff_explanations[rid] = "Hibernate checks are documented ahead of the implementation"
    for rid in in_java_only:
        if rid.startswith("QS-"):
            diff_explanations[rid] = (
                "Quarkus security checks are implemented in code and documented in Quarkus-specific advisories"
            )
        elif rid == "SEC-STATIC-001":
            diff_explanations[rid] = "StaticSecurityAnalysisDetector implements the static security analysis scan"
    return diff_explanations


def _reconcile_rule_ids(
    bootui_root: str,
    rules_list: list[dict],
    doc_rules: dict[str, dict],
    java_rules: dict[str, str],
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
    diff_explanations = _build_diff_explanations(in_doc_only, in_java_only, doc_rules)

    return rule_reconciliation, in_doc_only, in_java_only, diff_explanations


def _capture_rules(bootui_root: str, output_dir: str) -> None:
    doc_rules = _collect_doc_rules(bootui_root)
    java_rules = _collect_java_rules(bootui_root)

    all_rule_ids = sorted(set(doc_rules.keys()) | set(java_rules.keys()))
    rules_list = []
    for rid in all_rule_ids:
        r_info = doc_rules.get(rid, {})
        rules_list.append(
            {
                "id": rid,
                "title": r_info.get("title", ""),
                "docSource": r_info.get("source"),
                "javaSource": java_rules.get(rid),
                "inDocs": rid in doc_rules,
                "inJava": rid in java_rules,
                "retired": r_info.get("retired", False),
                "retiredExplanation": r_info.get("retiredExplanation"),
            }
        )

    rule_reconciliation, in_doc_only, in_java_only, diff_explanations = _reconcile_rule_ids(
        bootui_root, rules_list, doc_rules, java_rules
    )

    with open(f"{output_dir}/rule-ids.json", "w", encoding="utf-8", newline="\n") as f:
        json.dump({"rules": rules_list, "total": len(rules_list), "reconciliation": rule_reconciliation}, f, indent=2)
    print(f"Wrote rule-ids.json ({len(rules_list)} rules)")

    with open(f"{output_dir}/rule-ids-diff.json", "w", encoding="utf-8", newline="\n") as f:
        json.dump(
            {
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


def _capture_properties(bootui_root: str, output_dir: str) -> None:
    metadata_file = (
        f"{bootui_root}/bootui-spring-boot-starter/target/classes/META-INF/spring-configuration-metadata.json"
    )
    add_metadata_file = (
        f"{bootui_root}/bootui-spring-boot-starter/src/main/resources/META-INF/"
        "additional-spring-configuration-metadata.json"
    )

    with open(metadata_file, encoding="utf-8") as f:
        props = json.load(f).get("properties", [])

    if os.path.exists(add_metadata_file):
        with open(add_metadata_file, encoding="utf-8") as f:
            add_props = json.load(f).get("properties", [])
            seen_names = {p["name"] for p in props}
            for ap in add_props:
                if ap["name"] not in seen_names:
                    props.append(ap)

    hand_filled = {
        "bootui.enabled-profiles": {
            "defaultValue": ["dev", "local"],
            "defaultValueSource": "BootUiProperties.java:61",
        },
        "bootui.disabled-profiles": {
            "defaultValue": ["prod", "production"],
            "defaultValueSource": "BootUiProperties.java:70",
        },
        "bootui.api-path": {"defaultValue": "/bootui/api", "defaultValueSource": "BootUiProperties.java:82"},
        "bootui.cli.execution-timeout": {"defaultValue": "30s", "defaultValueSource": "BootUiProperties.java:3421"},
        "bootui.copilot.session-state-dir": {"defaultValue": None, "defaultValueSource": "BootUiProperties.java:2455"},
        "bootui.panels": {"defaultValue": None, "defaultValueSource": "BootUiProperties.java:82"},
    }

    cleaned_props = []
    for p in props:
        name = p.get("name", "")
        if not name.startswith("bootui.") or name.startswith("bootui.cli.max-"):
            continue
        item = {
            "name": name,
            "type": p.get("type", "java.lang.String"),
            "description": p.get("description", ""),
            "defaultValue": p.get("defaultValue"),
            "sourceType": p.get("sourceType", "io.github.jdubois.bootui.autoconfigure.BootUiProperties"),
        }
        if name in hand_filled:
            item["defaultValue"] = hand_filled[name]["defaultValue"]
            item["defaultValueSource"] = hand_filled[name]["defaultValueSource"]
        cleaned_props.append(item)

    cleaned_props.sort(key=lambda x: x["name"])
    with open(f"{output_dir}/properties.json", "w", encoding="utf-8", newline="\n") as f:
        json.dump({"properties": cleaned_props, "total": len(cleaned_props)}, f, indent=2)
    print(f"Wrote properties.json ({len(cleaned_props)} properties)")


def _capture_tests(bootui_root: str, output_dir: str) -> tuple[int, int]:
    test_files = glob.glob(f"{bootui_root}/**/src/test/java/**/*Test*.java", recursive=True)
    conformance_files = glob.glob(f"{bootui_root}/**/src/main/java/**/conformance/**/*.java", recursive=True)

    test_classes: dict[str, list[str]] = {}
    for tf in sorted(test_files + conformance_files):
        with open(tf, encoding="utf-8", errors="ignore") as f:
            code = f.read()

        pkg_match = re.search(r"package\s+([\w\.]+);", code)
        pkg = pkg_match.group(1) if pkg_match else ""

        class_matches = re.finditer(
            r"(?:public\s+|protected\s+|private\s+|abstract\s+|static\s+)*class\s+(\w+)(?:<[^>]+>)?(?:\s+extends\s+[\w\.<>]+)?(?:\s+implements\s+[\w\.<>,\s]+)?\s*\{",
            code,
        )

        for cm in class_matches:
            cname = cm.group(1)
            if not (cname.endswith("Test") or cname.endswith("Tests") or "Test" in cname):
                continue

            fqcn = f"{pkg}.{cname}" if pkg else cname
            methods = [
                mm.group(1)
                for mm in re.finditer(
                    r"@(?:Test|ParameterizedTest)\b.*?(?:public|protected|void)\s+(\w+)\s*\(", code, re.DOTALL
                )
            ]

            if methods or "conformance" in tf:
                test_classes[fqcn] = sorted(set(methods))

    sorted_test_classes = {cls: test_classes[cls] for cls in sorted(test_classes)}
    simple_names: dict[str, list[str]] = {}
    for fqcn in sorted_test_classes:
        simple_names.setdefault(fqcn.rsplit(".", 1)[-1], []).append(fqcn)
    simple_name_index = {
        name: {"classes": sorted(classes), "ambiguous": len(classes) > 1}
        for name, classes in sorted(simple_names.items())
    }

    with open(f"{output_dir}/bootui-tests.json", "w", encoding="utf-8", newline="\n") as f:
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
}


def main(version: str | None = None) -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Capture pinned BootUI tracker fixtures")
    parser.add_argument("--version", choices=tuple(_CAPTURE_VERSIONS), default=version)
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
    capture(
        tag=tag,
        commit=commit,
        output_dir=Path(__file__).resolve().parents[1] / f"tests/fixtures/bootui/{args.version}",
        version=args.version,
        date=date,
        repo=repo,
    )


if __name__ == "__main__":
    main()
