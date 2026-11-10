import atexit
import glob
import json
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

PINNED_COMMIT = "7c89042c6a0a47e1cb22d2df7412d2177d7416d1"
PINNED_TAG = "v2.3.0"
REPO = Path(__file__).resolve().parents[1]
output_dir = str((REPO / "tests/fixtures/bootui/2.3.0").resolve())
repo = Path(os.environ.get("BOOTUI_GIT", REPO.parents[1] / "boot-ui"))
actual_commit = subprocess.check_output(
    ["git", "-C", str(repo), "rev-parse", f"{PINNED_TAG}^{{commit}}"], text=True
).strip()
assert actual_commit == PINNED_COMMIT, f"Pinned tag resolves to {actual_commit}, expected {PINNED_COMMIT}"
tag_object = subprocess.check_output(["git", "-C", str(repo), "rev-parse", PINNED_TAG], text=True).strip()
bootui_root = tempfile.mkdtemp(prefix="bootui-2.3.0-")
atexit.register(shutil.rmtree, bootui_root, ignore_errors=True)
settings_file = Path(bootui_root) / "maven-settings.xml"
settings_file.write_text(
    '<settings xmlns="http://maven.apache.org/SETTINGS/1.2.0"><mirrors><mirror>'
    "<id>bootui-central</id><mirrorOf>*</mirrorOf><url>https://repo.maven.apache.org/maven2</url>"
    "</mirror></mirrors></settings>",
    encoding="utf-8",
)
archive = subprocess.Popen(["git", "-C", str(repo), "archive", PINNED_TAG], stdout=subprocess.PIPE)
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

print(f"BootUI Root: {bootui_root}")
print(f"Output Dir: {output_dir}")

# 1. meta.json
meta = {
    "bootuiVersion": "2.3.0",
    "commit": PINNED_COMMIT,
    "tag": PINNED_TAG,
    "command": "python scripts/capture_bootui_23.py",
    "tagObject": tag_object,
    "mavenCommand": " ".join(maven_command) + " -s <temporary settings override>",
    "javaVersionOutput": java_version_output,
    "mavenVersionOutput": maven_version_output,
    "settingsOverride": settings_override,
    "jdk": java_version_output,
    "captured": "2026-11-10",
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
with open(f"{output_dir}/meta.json", "w", encoding="utf-8") as f:
    json.dump(meta, f, indent=2)
print("Wrote meta.json")

# 2. panels.json from BootUiPanels.java
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

with open(f"{output_dir}/panels.json", "w", encoding="utf-8") as f:
    json.dump({"panels": panels_list}, f, indent=2)
print(f"Wrote panels.json ({len(panels_list)} panels)")

# 3. tools.json from bootui-tools.json + McpToolCatalog.DEFAULT_LIMITS + schema expansion + annotations
tools_file = f"{bootui_root}/bootui-cli/src/main/resources/bootui-tools.json"
with open(tools_file, encoding="utf-8") as f:
    raw_tools = json.load(f).get("tools", [])

DEFAULT_LIMITS = {
    "get_thread_snapshots": 6,
    "get_thread_analysis": 25,
    "get_thread_observation": 25,
    "cancel_thread_observation": 25,
    "get_runtime_insights": 25,
    "get_code_inventory": 200,
    "get_code_paths": 50,
    "get_side_effects": 25,
    "get_sql_traces": 25,
    "get_rest_client_traces": 25,
    "get_startup_timeline": 200,
    "get_log_tail": 100,
    "get_copilot_sessions": 25,
    "get_claude_code_sessions": 25,
    "get_vulnerabilities_report": 10,
    "get_live_activity": 25,
    "get_http_exchanges": 50,
    "get_beans": 50,
    "get_metrics": 50,
    "get_conditions": 50,
    "get_config": 50,
    "get_threads": 50,
}

OPEN_WORLD = {"vulnerabilities_scan"}


def get_annotations(name: str, action: bool):
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
        "openWorldHint": name in OPEN_WORLD,
    }


def get_input_schema(tool: str, schema_name: str):
    props = {}
    required = []

    if schema_name == "NONE":
        pass
    elif schema_name == "LIMIT":
        compacted = DEFAULT_LIMITS.get(tool)
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
        props["query"] = {"type": "string", "description": "Optional case-insensitive filter applied to the results."}
        compacted = DEFAULT_LIMITS.get(tool)
        default_limit = compacted if compacted is not None else 100
        limit_note = " (the server's limit)" if compacted is None else ""
        desc = (
            f"Optional maximum number of items to return; default {default_limit}{limit_note}, "
            "capped by the bootui.mcp.max-results server limit."
        )
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

    schema_obj = {"type": "object", "properties": props, "additionalProperties": False}
    if required:
        schema_obj["required"] = required
    return schema_obj


decorated_tools = []
for t in raw_tools:
    name = t["name"]
    action = t.get("action", False)
    schema_name = t.get("schema", "NONE")

    t_copy = dict(t)
    t_copy["annotations"] = get_annotations(name, action)
    if name in DEFAULT_LIMITS:
        t_copy["defaultLimit"] = DEFAULT_LIMITS[name]
    t_copy["inputSchema"] = get_input_schema(name, schema_name)
    decorated_tools.append(t_copy)

with open(f"{output_dir}/tools.json", "w", encoding="utf-8") as f:
    json.dump({"tools": decorated_tools}, f, indent=2)
print(f"Wrote tools.json ({len(decorated_tools)} tools)")

# 4. routes.json from BootUiApiContractCatalog.java and starter @*Mapping cross-check
catalog_file = (
    f"{bootui_root}/bootui-conformance/src/main/java/io/github/jdubois/bootui/conformance/BootUiApiContractCatalog.java"
)
with open(catalog_file, encoding="utf-8") as f:
    catalog_code = f.read()

# Reads extraction
reads = []
# Match read("panel", "/path", ...), capabilityList, pagedList, memory, advisor, capture, agent, etc.
# Parse read helper calls
read_call_regex = re.compile(
    r'(?:read|capabilityList|pagedCapabilityList|pagedList|memory|advisor|locatedAdvisor|inventory|capture|agent|array)\(\s*"([^"]+)"\s*,\s*"([^"]+)"'
)
seen_reads = set()
for m in read_call_regex.finditer(catalog_code):
    panel, path = m.groups()
    key = ("GET", path)
    if key not in seen_reads:
        seen_reads.add(key)
        reads.append(
            {
                "method": "GET",
                "path": path,
                "panel": panel,
                "operationId": f"read_{panel.replace('-', '_')}",
                "runtimes": ["SPRING_MVC", "SPRING_WEBFLUX", "QUARKUS"],
            }
        )

# Actions extraction
actions = []
action_call_regex = re.compile(
    r'(?:all|spring|springMvc|quarkus|infrastructure)\(\s*actions\s*,\s*"([^"]+)"\s*(?:,\s*"([^"]+)")?\s*,\s*"([^"]+)"\s*,\s*"([^"]+)"'
)
seen_actions = set()
for m in action_call_regex.finditer(catalog_code):
    action_id, panel, method, path = m.groups()
    if panel is None:
        panel = None
    key = (method, path)
    if key not in seen_actions:
        seen_actions.add(key)
        actions.append(
            {
                "id": action_id,
                "method": method,
                "path": path,
                "panel": panel,
                "runtimes": ["SPRING_MVC", "SPRING_WEBFLUX", "QUARKUS"],
            }
        )

# Scan all starter source files and ignore annotations in comments.
starter_controllers = glob.glob(f"{bootui_root}/bootui-spring-boot-starter/src/main/java/**/*.java", recursive=True)
starter_mappings = []
inherited_mappings = []
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
            if not path.startswith("/"):
                path = "/" + path
            starter_mappings.append(
                {
                    "controller": os.path.basename(cp),
                    "source": Path(cp).relative_to(bootui_root).as_posix(),
                    "line": ccode[: match.start()].count("\n") + 1,
                    "verb": method,
                    "path": path,
                }
            )

for child, parent in parent_by_class.items():
    parent_source = source_by_class.get(parent, "")
    prefix = prefix_by_class[child]
    for match in re.finditer(r"@(Get|Post|Delete|Put|Patch)Mapping\b(\s*\((?:[^()]|\([^()]*\))*\))?", parent_source):
        method, args = match.group(1).upper(), match.group(2) or ""
        for suffix in re.findall(r'"([^"]*)"', args) or [""]:
            path = (prefix + suffix).replace("//", "/") or "/"
            if not path.startswith("/"):
                path = "/" + path
            inherited_mappings.append(
                {
                    "controller": f"{child}.java",
                    "source": Path(next(p for p in starter_controllers if Path(p).stem == child))
                    .relative_to(bootui_root)
                    .as_posix(),
                    "line": parent_source[: match.start()].count("\n") + 1,
                    "verb": method,
                    "path": path,
                }
            )

catalog_routes = [(r["method"], r["path"]) for r in [*reads, *actions]]


def path_matches(route: str, template: str) -> bool:
    route_parts = route.split("?", 1)[0].strip("/").split("/")
    template_parts = template.split("?", 1)[0].strip("/").split("/")
    return len(route_parts) == len(template_parts) and all(
        left == right or "{" in left or "{" in right for left, right in zip(route_parts, template_parts, strict=True)
    )


def is_catalog_mapping(method: str, path: str) -> bool:
    return any(method == catalog_method and path_matches(path, template) for catalog_method, template in catalog_routes)


unmatched = [mapping for mapping in starter_mappings if not is_catalog_mapping(mapping["verb"], mapping["path"])]
catalog_only = [
    route
    for route in [*reads, *actions]
    if not any(
        route["method"] == mapping["verb"] and path_matches(mapping["path"], route["path"])
        for mapping in [*starter_mappings, *inherited_mappings]
    )
]
for mapping in [*unmatched, *inherited_mappings]:
    if is_catalog_mapping(mapping["verb"], mapping["path"]):
        continue
    path = mapping["path"]
    mapping["classification"] = (
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
    mapping["reason"] = {
        "infrastructure": "Infrastructure receiver/endpoint outside panel API catalog",
        "transport": "Protocol transport endpoint, not a panel read/action",
        "framework-introspection": "Framework introspection metadata endpoint",
        "session-management": "Session management endpoint outside catalog",
        "uncatalogued-starter-endpoint": "Starter mapping absent from BootUI contract catalog",
    }[mapping["classification"]]

route_gaps = []
for route in catalog_only:
    if route["method"] == "POST" and route["path"] == "/dev-services/services/conformance/restart":
        mapping = next(m for m in starter_mappings if m["verb"] == "POST" and m["path"] == "/dev-services/{id}/restart")
        catalog_match = re.search(re.escape(route["path"]), catalog_code)
        catalog_line = catalog_code[: catalog_match.start()].count("\n") + 1
        catalog_source = Path(catalog_file).relative_to(bootui_root).as_posix()
        route_gaps.append(
            {
                "category": "catalog-without-mapping",
                "method": route["method"],
                "path": route["path"],
                "catalogSource": f"{catalog_source}:{catalog_line}",
                "starterSource": f"{mapping['source']}:{mapping['line']}",
                "reason": "BootUI catalog names the conformance service while the starter mapping accepts an id",
            }
        )
    else:
        route_gaps.append({"category": "catalog-without-mapping", "method": route["method"], "path": route["path"]})

routes_data = {
    "reads": reads,
    "actions": actions,
    "crossCheck": {
        "starterMappingsCount": len(starter_mappings),
        "starterMappings": starter_mappings,
        "inheritedMappings": inherited_mappings,
        "unpanelledRoutes": [m for m in unmatched if m["verb"] == "GET"],
        "gaps": [{"category": "starter-without-catalog", **mapping} for mapping in unmatched] + route_gaps,
    },
}
with open(f"{output_dir}/routes.json", "w", encoding="utf-8") as f:
    json.dump(routes_data, f, indent=2)
print(f"Wrote routes.json ({len(reads)} reads, {len(actions)} actions)")
meta["counts"] = {
    "reads": len(reads),
    "actions": len(actions),
    "starterMappings": len(starter_mappings),
    "gaps": len(unmatched) + len(route_gaps),
    "unpanelledRoutes": sum(mapping["verb"] == "GET" for mapping in unmatched),
    "routeCountMethod": "catalog read/action helper calls and all starter src/main/java @*Mapping declarations",
}

# 5 & 6. rule-ids.json and rule-ids-diff.json
doc_rules = {}
check_md_files = glob.glob(f"{bootui_root}/docs/*-CHECKS.md")
for fpath in check_md_files:
    fname = os.path.basename(fpath)
    with open(fpath, encoding="utf-8") as fp:
        for line in fp:
            m = re.match(r"^###\s+([A-Z0-9_\-\.]+)\s+-\s+(.*)", line.strip())
            if m:
                rid, rtitle = m.groups()
                doc_rules[rid] = {"id": rid, "title": rtitle, "source": fname}
            # Also catch table rows for retired rules: | ARCH-CODE-005 | ...
            tm = re.match(r"^\|\s*([A-Z0-9_\-\.]+)\s*\|\s*([^|]+)\|\s*([^|]+)\|", line.strip())
            if tm:
                trid = tm.group(1).strip()
                if re.match(r"^[A-Z]+-[A-Z0-9]+-\d+$", trid):
                    doc_rules[trid] = {"id": trid, "title": tm.group(2).strip(), "source": fname, "retired": True}

java_rules = {}
java_files = glob.glob(f"{bootui_root}/**/src/main/java/**/*.java", recursive=True)
rule_pattern = re.compile(r'"([A-Z][A-Z0-9]*(?:-[A-Z0-9]+)+)"')

for jf in java_files:
    jf_norm = jf.replace("\\", "/")
    with open(jf, encoding="utf-8", errors="ignore") as fp:
        jcode = fp.read()
    for match in rule_pattern.finditer(jcode):
        cand = match.group(1)
        if re.match(
            r"^(ARCH|SPRING|HIB|CRAC|GRAAL|GRAALVM|SEC|MEM|PENTEST|PT|REST|RAPI|QUARKUS|QA|QS|VULN|DB|JVM)-", cand
        ):
            java_rules[cand] = Path(jf).relative_to(bootui_root).as_posix()
    # Also catch "SPRING-" + id pattern in SpringRules.java
    if "SpringRules.java" in jf_norm:
        for sm in re.finditer(r'super\(\s*"([A-Z0-9]+-\d+)"\s*,\s*"([^"]+)"', jcode):
            s_id = "SPRING-" + sm.group(1)
            java_rules[s_id] = Path(jf).relative_to(bootui_root).as_posix()

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
        }
    )

with open(f"{output_dir}/rule-ids.json", "w", encoding="utf-8") as f:
    json.dump({"rules": rules_list, "total": len(rules_list)}, f, indent=2)
print(f"Wrote rule-ids.json ({len(rules_list)} rules)")

# Diff explanation
in_doc_only = sorted(set(doc_rules.keys()) - set(java_rules.keys()))
in_java_only = sorted(set(java_rules.keys()) - set(doc_rules.keys()))

diff_explanations = {}
for rid in in_doc_only:
    r_info = doc_rules.get(rid, {})
    if r_info.get("retired"):
        diff_explanations[rid] = "Documented as retired rule in checks markdown"
    elif "HIB" in rid:
        diff_explanations[rid] = "Documented Hibernate check; retired or Jakarta Persistence implicit default"
    elif "DB-" in rid:
        diff_explanations[rid] = "Documented database schema check"
    else:
        diff_explanations[rid] = f"Documented check specification in {r_info.get('source')}"

for rid in in_java_only:
    if "MEM-" in rid:
        diff_explanations[rid] = "Runtime memory check rule implemented in engine MemoryRules.java"
    elif "ARCH-" in rid:
        diff_explanations[rid] = "Architecture check rule constant in ArchitectureRules.java"
    elif "QS-" in rid:
        diff_explanations[rid] = "Quarkus security check constant in QuarkusSecurityChecks.java"
    else:
        diff_explanations[rid] = f"Internal rule constant in {os.path.basename(java_rules.get(rid, ''))}"

diff_obj = {
    "inDocOnlyCount": len(in_doc_only),
    "inJavaOnlyCount": len(in_java_only),
    "inDocOnly": in_doc_only,
    "inJavaOnly": in_java_only,
    "explanations": diff_explanations,
}
with open(f"{output_dir}/rule-ids-diff.json", "w", encoding="utf-8") as f:
    json.dump(diff_obj, f, indent=2)
print(f"Wrote rule-ids-diff.json (doc only: {len(in_doc_only)}, java only: {len(in_java_only)})")

# 7. properties.json from spring-configuration-metadata.json + additional + hand-filled non-literal defaults
metadata_file = f"{bootui_root}/bootui-spring-boot-starter/target/classes/META-INF/spring-configuration-metadata.json"
add_metadata_file = (
    f"{bootui_root}/bootui-spring-boot-starter/src/main/resources/META-INF/"
    "additional-spring-configuration-metadata.json"
)

props_dict = {}
if not os.path.isfile(metadata_file):
    raise FileNotFoundError(f"Maven build did not generate required metadata: {metadata_file}")
with open(metadata_file, encoding="utf-8") as f:
    for p in json.load(f).get("properties", []):
        props_dict[p["name"]] = p

if os.path.exists(add_metadata_file):
    with open(add_metadata_file, encoding="utf-8") as f:
        for p in json.load(f).get("properties", []):
            props_dict[p["name"]] = p

# Hand-filled non-literal defaults from BootUiProperties.java with line citations
HAND_FILLED = {
    "bootui.api-path": {"defaultValue": "/bootui/api", "defaultValueSource": "BootUiProperties.java:49,273"},
    "bootui.authentication.token": {"defaultValue": None, "defaultValueSource": "BootUiProperties.java:3524"},
    "bootui.enabled-profiles": {
        "defaultValue": ["dev", "local"],
        "defaultValueSource": "BootUiProperties.java:103 (BootUiDefaults.ENABLED_PROFILES)",
    },
    "bootui.disabled-profiles": {
        "defaultValue": ["prod", "production"],
        "defaultValueSource": "BootUiProperties.java:107 (BootUiDefaults.DISABLED_PROFILES)",
    },
    "bootui.dev-services.log-tail-bytes": {
        "defaultValue": 65536,
        "defaultValueSource": "BootUiProperties.java:761 (64 * 1024)",
    },
    "bootui.cli.max-payload-bytes": {
        "defaultValue": 1048576,
        "defaultValueSource": "BootUiProperties.java:2638 (1 * 1024 * 1024)",
    },
    "bootui.cli.max-concurrent-calls": {"defaultValue": 20, "defaultValueSource": "BootUiProperties.java:2644"},
    "bootui.cli.execution-timeout": {
        "defaultValue": "30s",
        "defaultValueSource": "BootUiProperties.java:2647 (Duration.ofSeconds(30))",
    },
    "bootui.cli.max-response-bytes": {
        "defaultValue": 4194304,
        "defaultValueSource": "BootUiProperties.java:2650 (4 * 1024 * 1024)",
    },
    "bootui.mcp.max-payload-bytes": {
        "defaultValue": 1048576,
        "defaultValueSource": "BootUiProperties.java:2638 (1 * 1024 * 1024)",
    },
    "bootui.mcp.max-concurrent-calls": {
        "defaultValue": 20,
        "defaultValueSource": "BootUiProperties.java:2725 (McpProtocol.DEFAULT_MAX_CONCURRENT_CALLS)",
    },
    "bootui.mcp.execution-timeout": {
        "defaultValue": "30s",
        "defaultValueSource": "BootUiProperties.java:2728 (McpProtocol.DEFAULT_EXECUTION_TIMEOUT_MILLIS)",
    },
    "bootui.mcp.max-response-bytes": {
        "defaultValue": 4194304,
        "defaultValueSource": "BootUiProperties.java:2650 (4 * 1024 * 1024)",
    },
    "bootui.runtime-insights.ai-token-threshold": {
        "defaultValue": 8000,
        "defaultValueSource": "BootUiProperties.java:2776 (AiUsageByRoute.DEFAULT_TOKEN_THRESHOLD)",
    },
    "bootui.code-inventory.max-classes": {
        "defaultValue": 20000,
        "defaultValueSource": "BootUiProperties.java:2791 (CodeInventorySettings.DEFAULT_MAX_CLASSES)",
    },
    "bootui.code-inventory.scan-timeout": {
        "defaultValue": "30s",
        "defaultValueSource": "BootUiProperties.java:2794 (CodeInventorySettings.DEFAULT_SCAN_TIMEOUT)",
    },
    "bootui.runtime-journal.max-events": {
        "defaultValue": 50000,
        "defaultValueSource": "BootUiProperties.java:2830 (RuntimeJournalSettings.DEFAULT_MAX_EVENTS)",
    },
    "bootui.runtime-journal.max-bytes": {"defaultValue": None, "defaultValueSource": "BootUiProperties.java:2836"},
    "bootui.runtime-journal.agent-evidence-max-bytes": {
        "defaultValue": None,
        "defaultValueSource": "BootUiProperties.java:2844",
    },
    "bootui.runtime-journal.queue-capacity": {
        "defaultValue": 10000,
        "defaultValueSource": "BootUiProperties.java:2850 (RuntimeJournalSettings.DEFAULT_QUEUE_CAPACITY)",
    },
    "bootui.runtime-journal.sources": {"defaultValue": None, "defaultValueSource": "BootUiProperties.java:2858"},
    "bootui.runtime-journal.baseline-file": {"defaultValue": None, "defaultValueSource": "BootUiProperties.java:2866"},
    "bootui.agent.packages": {"defaultValue": [], "defaultValueSource": "BootUiProperties.java:2955"},
    "bootui.agent.sensors": {
        "defaultValue": [
            "executors",
            "inventory",
            "code-paths",
            "processes",
            "network",
            "files",
            "blocking",
            "resources",
        ],
        "defaultValueSource": "BootUiProperties.java:2983 (AgentSensorSettings.DEFAULT_SENSORS)",
    },
    "bootui.agent.ring-capacity": {
        "defaultValue": 65536,
        "defaultValueSource": "BootUiProperties.java:2989 (AgentSensorSettings.DEFAULT_RING_CAPACITY)",
    },
    "bootui.agent.executors.skip-tasks": {
        "defaultValue": [
            "io.github.jdubois.bootui.engine.correlation.ManagedTasks",
            "io.micrometer.context.",
            "org.springframework.core.task.support.ContextPropagatingTaskDecorator",
            "jdk.internal.",
            "sun.",
            "java.lang.ProcessHandleImpl",
            "com.zaxxer.hikari.",
            "com.github.benmanes.caffeine.",
        ],
        "defaultValueSource": "BootUiProperties.java:3082 (AgentSensorSettings.DEFAULT_SKIP_TASKS)",
    },
    "bootui.agent.executors.skip-threads": {
        "defaultValue": ["vert.x-", "bootui-"],
        "defaultValueSource": "BootUiProperties.java:3088 (AgentSensorSettings.DEFAULT_SKIP_THREADS)",
    },
    "bootui.agent.executors.max-handoff": {
        "defaultValue": "5m",
        "defaultValueSource": "BootUiProperties.java:3094 (AgentHandoffs.DEFAULT_MAX_HANDOFF)",
    },
    "bootui.resources.sample-interval": {
        "defaultValue": "1s",
        "defaultValueSource": "BootUiProperties.java:3132 (ResourceSettings.DEFAULT_SAMPLE_INTERVAL)",
    },
    "bootui.resources.max-threads": {
        "defaultValue": 500,
        "defaultValueSource": "BootUiProperties.java:3135 (ResourceSettings.DEFAULT_MAX_THREADS)",
    },
    "bootui.resources.jfr.max-duration": {
        "defaultValue": "30s",
        "defaultValueSource": "BootUiProperties.java:3168 (ResourceSettings.DEFAULT_JFR_MAX_DURATION)",
    },
    "bootui.telemetry.max-attribute-value-bytes": {
        "defaultValue": 4096,
        "defaultValueSource": "BootUiProperties.java:2307 (4 * 1024)",
    },
    "bootui.telemetry.max-request-bytes": {
        "defaultValue": 8388608,
        "defaultValueSource": "BootUiProperties.java:2325 (8 * 1024 * 1024)",
    },
    "bootui.threads.max-threads": {"defaultValue": 2048, "defaultValueSource": "BootUiProperties.java:2060"},
    "bootui.threads.max-retained-bytes": {
        "defaultValue": 16777216,
        "defaultValueSource": "BootUiProperties.java:2066 (16 * 1024 * 1024L)",
    },
    "bootui.threads.max-capture-bytes": {
        "defaultValue": 4194304,
        "defaultValueSource": "BootUiProperties.java:2067 (4 * 1024 * 1024L)",
    },
    "bootui.activity.persistence.dedicated-jdbc-url": {
        "defaultValue": None,
        "defaultValueSource": "BootUiProperties.java:3377",
    },
    "bootui.activity.persistence.dedicated-username": {
        "defaultValue": None,
        "defaultValueSource": "BootUiProperties.java:3380",
    },
    "bootui.activity.persistence.dedicated-password": {
        "defaultValue": None,
        "defaultValueSource": "BootUiProperties.java:3383",
    },
    "bootui.activity.persistence.dedicated-driver-class-name": {
        "defaultValue": None,
        "defaultValueSource": "BootUiProperties.java:3390",
    },
    "bootui.activity.persistence.instance-id": {
        "defaultValue": None,
        "defaultValueSource": "BootUiProperties.java:3421",
    },
    "bootui.claude-code.session-state-dir": {"defaultValue": None, "defaultValueSource": "BootUiProperties.java:2455"},
    "bootui.copilot.session-state-dir": {"defaultValue": None, "defaultValueSource": "BootUiProperties.java:2455"},
    "bootui.panels": {"defaultValue": None, "defaultValueSource": "BootUiProperties.java:82"},
}

for name, patch in HAND_FILLED.items():
    if name in props_dict:
        props_dict[name]["defaultValue"] = patch["defaultValue"]
        props_dict[name]["defaultValueSource"] = patch["defaultValueSource"]
    else:
        props_dict[name] = {
            "name": name,
            "type": "java.lang.Object",
            "defaultValue": patch["defaultValue"],
            "defaultValueSource": patch["defaultValueSource"],
        }

final_properties = sorted(props_dict.values(), key=lambda p: p["name"])
with open(f"{output_dir}/properties.json", "w", encoding="utf-8") as f:
    json.dump({"properties": final_properties}, f, indent=2)
print(f"Wrote properties.json ({len(final_properties)} properties)")

# 8. bootui-tests.json from test classes and methods
test_files = glob.glob(f"{bootui_root}/**/src/test/java/**/*.java", recursive=True)
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

test_classes = {}
for tf in test_files:
    with open(tf, encoding="utf-8", errors="ignore") as f:
        tcode = f.read()

    cmatches = list(re.finditer(r"(?:public\s+)?(?:static\s+)?(?:final\s+)?class\s+(\w+)", tcode))
    if not cmatches:
        continue
    top_c = cmatches[0].group(1)

    meths = set()
    for mm in method_regex.finditer(tcode):
        meths.add(mm.group(1))
    for mm in arch_regex.finditer(tcode):
        meths.add(mm.group(1))

    if meths:
        test_classes[top_c] = sorted(meths)

with open(f"{output_dir}/bootui-tests.json", "w", encoding="utf-8") as f:
    json.dump(
        {
            "testClasses": test_classes,
            "totalClasses": len(test_classes),
            "totalMethods": sum(len(m) for m in test_classes.values()),
        },
        f,
        indent=2,
    )
print(f"Wrote bootui-tests.json ({len(test_classes)} test classes)")

with open(f"{output_dir}/meta.json", "w", encoding="utf-8") as f:
    json.dump(meta, f, indent=2)
