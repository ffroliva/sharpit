# Capture BootUI 2.3.0 tracker fixtures from pinned v2.3.0 repository
param(
    [string]$BootUiPath = "C:/development/github/boot-ui-v2.3.0",
    [string]$OutputDir = "$PSScriptRoot/../tests/fixtures/bootui/2.3.0"
)

$ErrorActionPreference = "Stop"

Write-Host "Capturing BootUI 2.3.0 fixtures from $BootUiPath into $OutputDir..."

if (-not (Test-Path $OutputDir)) {
    New-Item -ItemType Directory -Path $OutputDir -Force | Out-Null
}

$pyScript = @'
import os
import sys
import glob
import json
import re

bootui_root = sys.argv[1].replace("\\", "/")
output_dir = sys.argv[2].replace("\\", "/")

PINNED_COMMIT = "7c89042c6a0a47e1cb22d2df7412d2177d7416d1"
PINNED_TAG = "v2.3.0"

print(f"BootUI Root: {bootui_root}")
print(f"Output Dir: {output_dir}")

# 1. meta.json
meta = {
    "bootuiVersion": "2.3.0",
    "commit": PINNED_COMMIT,
    "tag": PINNED_TAG,
    "command": "powershell scripts/capture_bootui_23.ps1",
    "mavenCommand": "mvn -pl bootui-spring-boot-starter -am -DskipTests -Dmaven.compiler.proc=full compile",
    "jdk": "Amazon Corretto 25.0.3_9 (target release 17)",
    "captured": "2026-11-10",
    "fixtures": [
        "meta.json",
        "panels.json",
        "routes.json",
        "tools.json",
        "rule-ids.json",
        "rule-ids-diff.json",
        "properties.json",
        "bootui-tests.json"
    ]
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
    panels_list.append({
        "id": panel_id,
        "title": title,
        "actionCapable": action,
        "apiPrefixes": prefixes
    })

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
    "get_threads": 50
}

OPEN_WORLD = {"vulnerabilities_scan"}

def get_annotations(name: str, action: bool):
    if not action:
        return {
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False
        }
    destructive = name.startswith("clear_") or name == "enable_low_footprint"
    idempotent = destructive or name.startswith("pause_") or name.startswith("resume_") or name == "disable_low_footprint"
    return {
        "readOnlyHint": False,
        "destructiveHint": destructive,
        "idempotentHint": idempotent,
        "openWorldHint": name in OPEN_WORLD
    }

def get_input_schema(tool: str, schema_name: str):
    props = {}
    required = []

    if schema_name == "NONE":
        pass
    elif schema_name == "LIMIT":
        compacted = DEFAULT_LIMITS.get(tool)
        default_limit = compacted if compacted is not None else 100
        meaning = "Optional number of routes each ranking criterion contributes" if tool == "get_http_routes" else "Optional maximum number of items to return"
        desc = f"{meaning}; default {default_limit}{' (the server\'s limit)' if compacted is None else ''}, capped by the bootui.mcp.max-results server limit."
        props["limit"] = {
            "type": "integer",
            "minimum": 1,
            "default": default_limit,
            "description": desc
        }
    elif schema_name == "QUERY_LIMIT":
        props["query"] = {
            "type": "string",
            "description": "Optional case-insensitive filter applied to the results."
        }
        compacted = DEFAULT_LIMITS.get(tool)
        default_limit = compacted if compacted is not None else 100
        desc = f"Optional maximum number of items to return; default {default_limit}{' (the server\'s limit)' if compacted is None else ''}, capped by the bootui.mcp.max-results server limit."
        props["limit"] = {
            "type": "integer",
            "minimum": 1,
            "default": default_limit,
            "description": desc
        }
    elif schema_name == "QUERY":
        props["query"] = {
            "type": "string",
            "description": "Optional case-insensitive filter applied to the results."
        }
    elif schema_name == "ID":
        props["id"] = {
            "type": "string",
            "description": "Exact identifier of the resource to fetch."
        }
        required.append("id")
    elif schema_name == "OPTIONAL_ID":
        props["id"] = {
            "type": "string",
            "description": "Optional identifier; omitted selects the tool's documented default."
        }
    elif schema_name == "RULE_VIOLATIONS":
        report = tool.replace("_rule_violations", "_report")
        props["id"] = {
            "type": "string",
            "minLength": 1,
            "description": f"The rule id, from {report}."
        }
        required.append("id")
        props["scanId"] = {
            "type": "string",
            "minLength": 1,
            "description": "The cached report's violationDetails.scanId. Never starts a scan."
        }
        required.append("scanId")
        props["offset"] = {
            "type": "integer",
            "minimum": 0,
            "default": 0,
            "description": "Zero-based offset into the retained violations; advance it by page.returned while page.hasMore."
        }
        props["limit"] = {
            "type": "integer",
            "minimum": 1,
            "default": 100,
            "description": "Page size, default 100, capped at min(1000, bootui.mcp.max-results)."
        }

    schema_obj = {
        "type": "object",
        "properties": props,
        "additionalProperties": False
    }
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
catalog_file = f"{bootui_root}/bootui-conformance/src/main/java/io/github/jdubois/bootui/conformance/BootUiApiContractCatalog.java"
with open(catalog_file, encoding="utf-8") as f:
    catalog_code = f.read()

# Reads extraction
reads = []
# Match read("panel", "/path", ...), capabilityList, pagedList, memory, advisor, capture, agent, etc.
# Parse read helper calls
read_call_regex = re.compile(r'(?:read|capabilityList|pagedCapabilityList|pagedList|memory|advisor|inventory|capture|agent)\(\s*"([^"]+)"\s*,\s*"([^"]+)"')
seen_reads = set()
for m in read_call_regex.finditer(catalog_code):
    panel, path = m.groups()
    key = ("GET", path)
    if key not in seen_reads:
        seen_reads.add(key)
        reads.append({
            "method": "GET",
            "path": path,
            "panel": panel,
            "operationId": f"read_{panel.replace('-', '_')}",
            "runtimes": ["SPRING_MVC", "SPRING_WEBFLUX", "QUARKUS"]
        })

# Actions extraction
actions = []
action_call_regex = re.compile(r'(?:all|spring|springMvc|quarkus|infrastructure)\(\s*actions\s*,\s*"([^"]+)"\s*(?:,\s*"([^"]+)")?\s*,\s*"([^"]+)"\s*,\s*"([^"]+)"')
seen_actions = set()
for m in action_call_regex.finditer(catalog_code):
    action_id, panel, method, path = m.groups()
    if panel is None:
        panel = None
    key = (method, path)
    if key not in seen_actions:
        seen_actions.add(key)
        actions.append({
            "id": action_id,
            "method": method,
            "path": path,
            "panel": panel,
            "runtimes": ["SPRING_MVC", "SPRING_WEBFLUX", "QUARKUS"]
        })

# Also parse all @*Mapping in starter controllers
starter_controllers = glob.glob(f"{bootui_root}/bootui-spring-boot-starter/src/main/java/**/autoconfigure/**/*Controller.java", recursive=True)
starter_mappings = []
for cp in starter_controllers:
    with open(cp, encoding="utf-8") as f:
        ccode = f.read()
    c_prefix = ""
    cm = re.search(r'@RequestMapping\(\s*"(?:[^"]*api\}|/bootui/api)([^"]*)"\s*\)', ccode)
    if cm:
        c_prefix = cm.group(1)

    for mm in re.finditer(r'@(GetMapping|PostMapping|DeleteMapping|RequestMapping)\s*(?:\(\s*(?:(?:path|value)\s*=\s*)?("([^"]*)"|{([^}]*)})?[^)]*\))?', ccode):
        verb = mm.group(1).replace("Mapping", "").upper()
        if verb == "REQUEST":
            verb = "ANY"
        subpath = mm.group(3) or ""
        if not subpath and mm.group(4):
            subpath = mm.group(4)
        full_p = (c_prefix + subpath).replace("//", "/")
        if not full_p.startswith("/"):
            full_p = "/" + full_p
        starter_mappings.append({
            "controller": os.path.basename(cp),
            "verb": verb,
            "path": full_p
        })

unpanelled = [
    {
        "method": "POST",
        "path": "/otlp/v1/traces",
        "controller": "OtlpReceiverController.java",
        "reason": "OTLP telemetry receiver mounted under /bootui/api/otlp; un-panelled infrastructure receiver"
    }
]

routes_data = {
    "reads": reads,
    "actions": actions,
    "crossCheck": {
        "starterMappingsCount": len(starter_mappings),
        "starterMappings": starter_mappings,
        "unpanelledRoutes": unpanelled,
        "gaps": [
            "OTLP receiver /otlp/v1/traces is un-panelled infrastructure POST route",
            "GET /overview is shell chrome data source with no panel API prefix gating",
            "GET /cli and POST /cli/tools/{name} are command-line transport endpoints gated by bootui.cli.enabled"
        ]
    }
}
with open(f"{output_dir}/routes.json", "w", encoding="utf-8") as f:
    json.dump(routes_data, f, indent=2)
print(f"Wrote routes.json ({len(reads)} reads, {len(actions)} actions)")

# 5 & 6. rule-ids.json and rule-ids-diff.json
doc_rules = {}
check_md_files = glob.glob(f"{bootui_root}/docs/*-CHECKS.md")
for fpath in check_md_files:
    fname = os.path.basename(fpath)
    with open(fpath, encoding="utf-8") as fp:
        for line in fp:
            m = re.match(r'^###\s+([A-Z0-9_\-\.]+)\s+-\s+(.*)', line.strip())
            if m:
                rid, rtitle = m.groups()
                doc_rules[rid] = {"id": rid, "title": rtitle, "source": fname}
            # Also catch table rows for retired rules: | ARCH-CODE-005 | ...
            tm = re.match(r'^\|\s*([A-Z0-9_\-\.]+)\s*\|\s*([^|]+)\|\s*([^|]+)\|', line.strip())
            if tm:
                trid = tm.group(1).strip()
                if re.match(r'^[A-Z]+-[A-Z0-9]+-\d+$', trid):
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
        if re.match(r'^(ARCH|SPRING|HIB|CRAC|GRAAL|GRAALVM|SEC|MEM|PENTEST|PT|REST|RAPI|QUARKUS|QA|QS|VULN|DB|JVM)-', cand):
            java_rules[cand] = jf_norm
    # Also catch "SPRING-" + id pattern in SpringRules.java
    if "SpringRules.java" in jf_norm:
        for sm in re.finditer(r'super\(\s*"([A-Z0-9]+-\d+)"\s*,\s*"([^"]+)"', jcode):
            s_id = "SPRING-" + sm.group(1)
            java_rules[s_id] = jf_norm

all_rule_ids = sorted(list(set(doc_rules.keys()) | set(java_rules.keys())))
rules_list = []
for rid in all_rule_ids:
    r_info = doc_rules.get(rid, {})
    rules_list.append({
        "id": rid,
        "title": r_info.get("title", ""),
        "docSource": r_info.get("source"),
        "javaSource": java_rules.get(rid),
        "inDocs": rid in doc_rules,
        "inJava": rid in java_rules,
        "retired": r_info.get("retired", False)
    })

with open(f"{output_dir}/rule-ids.json", "w", encoding="utf-8") as f:
    json.dump({"rules": rules_list, "total": len(rules_list)}, f, indent=2)
print(f"Wrote rule-ids.json ({len(rules_list)} rules)")

# Diff explanation
in_doc_only = sorted(list(set(doc_rules.keys()) - set(java_rules.keys())))
in_java_only = sorted(list(set(java_rules.keys()) - set(doc_rules.keys())))

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
    "explanations": diff_explanations
}
with open(f"{output_dir}/rule-ids-diff.json", "w", encoding="utf-8") as f:
    json.dump(diff_obj, f, indent=2)
print(f"Wrote rule-ids-diff.json (doc only: {len(in_doc_only)}, java only: {len(in_java_only)})")

# 7. properties.json from spring-configuration-metadata.json + additional + hand-filled non-literal defaults
metadata_file = f"{bootui_root}/bootui-spring-boot-starter/target/classes/META-INF/spring-configuration-metadata.json"
add_metadata_file = f"{bootui_root}/bootui-spring-boot-starter/src/main/resources/META-INF/additional-spring-configuration-metadata.json"

props_dict = {}
if os.path.exists(metadata_file):
    with open(metadata_file, encoding="utf-8") as f:
        for p in json.load(f).get("properties", []):
            props_dict[p["name"]] = p

if os.path.exists(add_metadata_file):
    with open(add_metadata_file, encoding="utf-8") as f:
        for p in json.load(f).get("properties", []):
            props_dict[p["name"]] = p

# Hand-filled non-literal defaults from BootUiProperties.java with line citations
HAND_FILLED = {
    "bootui.api-path": {
        "defaultValue": "/bootui/api",
        "defaultValueSource": "BootUiProperties.java:49,273"
    },
    "bootui.authentication.token": {
        "defaultValue": None,
        "defaultValueSource": "BootUiProperties.java:3524"
    },
    "bootui.enabled-profiles": {
        "defaultValue": ["dev", "local"],
        "defaultValueSource": "BootUiProperties.java:103 (BootUiDefaults.ENABLED_PROFILES)"
    },
    "bootui.disabled-profiles": {
        "defaultValue": ["prod", "production"],
        "defaultValueSource": "BootUiProperties.java:107 (BootUiDefaults.DISABLED_PROFILES)"
    },
    "bootui.dev-services.log-tail-bytes": {
        "defaultValue": 65536,
        "defaultValueSource": "BootUiProperties.java:761 (64 * 1024)"
    },
    "bootui.cli.max-payload-bytes": {
        "defaultValue": 1048576,
        "defaultValueSource": "BootUiProperties.java:2638 (1 * 1024 * 1024)"
    },
    "bootui.cli.max-concurrent-calls": {
        "defaultValue": 20,
        "defaultValueSource": "BootUiProperties.java:2644"
    },
    "bootui.cli.execution-timeout": {
        "defaultValue": "30s",
        "defaultValueSource": "BootUiProperties.java:2647 (Duration.ofSeconds(30))"
    },
    "bootui.cli.max-response-bytes": {
        "defaultValue": 4194304,
        "defaultValueSource": "BootUiProperties.java:2650 (4 * 1024 * 1024)"
    },
    "bootui.mcp.max-payload-bytes": {
        "defaultValue": 1048576,
        "defaultValueSource": "BootUiProperties.java:2638 (1 * 1024 * 1024)"
    },
    "bootui.mcp.max-concurrent-calls": {
        "defaultValue": 20,
        "defaultValueSource": "BootUiProperties.java:2725 (McpProtocol.DEFAULT_MAX_CONCURRENT_CALLS)"
    },
    "bootui.mcp.execution-timeout": {
        "defaultValue": "30s",
        "defaultValueSource": "BootUiProperties.java:2728 (McpProtocol.DEFAULT_EXECUTION_TIMEOUT_MILLIS)"
    },
    "bootui.mcp.max-response-bytes": {
        "defaultValue": 4194304,
        "defaultValueSource": "BootUiProperties.java:2650 (4 * 1024 * 1024)"
    },
    "bootui.runtime-insights.ai-token-threshold": {
        "defaultValue": 8000,
        "defaultValueSource": "BootUiProperties.java:2776 (AiUsageByRoute.DEFAULT_TOKEN_THRESHOLD)"
    },
    "bootui.code-inventory.max-classes": {
        "defaultValue": 20000,
        "defaultValueSource": "BootUiProperties.java:2791 (CodeInventorySettings.DEFAULT_MAX_CLASSES)"
    },
    "bootui.code-inventory.scan-timeout": {
        "defaultValue": "30s",
        "defaultValueSource": "BootUiProperties.java:2794 (CodeInventorySettings.DEFAULT_SCAN_TIMEOUT)"
    },
    "bootui.runtime-journal.max-events": {
        "defaultValue": 50000,
        "defaultValueSource": "BootUiProperties.java:2830 (RuntimeJournalSettings.DEFAULT_MAX_EVENTS)"
    },
    "bootui.runtime-journal.max-bytes": {
        "defaultValue": None,
        "defaultValueSource": "BootUiProperties.java:2836"
    },
    "bootui.runtime-journal.agent-evidence-max-bytes": {
        "defaultValue": None,
        "defaultValueSource": "BootUiProperties.java:2844"
    },
    "bootui.runtime-journal.queue-capacity": {
        "defaultValue": 10000,
        "defaultValueSource": "BootUiProperties.java:2850 (RuntimeJournalSettings.DEFAULT_QUEUE_CAPACITY)"
    },
    "bootui.runtime-journal.sources": {
        "defaultValue": None,
        "defaultValueSource": "BootUiProperties.java:2858"
    },
    "bootui.runtime-journal.baseline-file": {
        "defaultValue": None,
        "defaultValueSource": "BootUiProperties.java:2866"
    },
    "bootui.agent.packages": {
        "defaultValue": [],
        "defaultValueSource": "BootUiProperties.java:2955"
    },
    "bootui.agent.sensors": {
        "defaultValue": ["executors", "inventory", "code-paths", "processes", "network", "files", "blocking", "resources"],
        "defaultValueSource": "BootUiProperties.java:2983 (AgentSensorSettings.DEFAULT_SENSORS)"
    },
    "bootui.agent.ring-capacity": {
        "defaultValue": 65536,
        "defaultValueSource": "BootUiProperties.java:2989 (AgentSensorSettings.DEFAULT_RING_CAPACITY)"
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
            "com.github.benmanes.caffeine."
        ],
        "defaultValueSource": "BootUiProperties.java:3082 (AgentSensorSettings.DEFAULT_SKIP_TASKS)"
    },
    "bootui.agent.executors.skip-threads": {
        "defaultValue": ["vert.x-", "bootui-"],
        "defaultValueSource": "BootUiProperties.java:3088 (AgentSensorSettings.DEFAULT_SKIP_THREADS)"
    },
    "bootui.agent.executors.max-handoff": {
        "defaultValue": "5m",
        "defaultValueSource": "BootUiProperties.java:3094 (AgentHandoffs.DEFAULT_MAX_HANDOFF)"
    },
    "bootui.resources.sample-interval": {
        "defaultValue": "1s",
        "defaultValueSource": "BootUiProperties.java:3132 (ResourceSettings.DEFAULT_SAMPLE_INTERVAL)"
    },
    "bootui.resources.max-threads": {
        "defaultValue": 500,
        "defaultValueSource": "BootUiProperties.java:3135 (ResourceSettings.DEFAULT_MAX_THREADS)"
    },
    "bootui.resources.jfr.max-duration": {
        "defaultValue": "30s",
        "defaultValueSource": "BootUiProperties.java:3168 (ResourceSettings.DEFAULT_JFR_MAX_DURATION)"
    },
    "bootui.telemetry.max-attribute-value-bytes": {
        "defaultValue": 4096,
        "defaultValueSource": "BootUiProperties.java:2307 (4 * 1024)"
    },
    "bootui.telemetry.max-request-bytes": {
        "defaultValue": 8388608,
        "defaultValueSource": "BootUiProperties.java:2325 (8 * 1024 * 1024)"
    },
    "bootui.threads.max-threads": {
        "defaultValue": 2048,
        "defaultValueSource": "BootUiProperties.java:2060"
    },
    "bootui.threads.max-retained-bytes": {
        "defaultValue": 16777216,
        "defaultValueSource": "BootUiProperties.java:2066 (16 * 1024 * 1024L)"
    },
    "bootui.threads.max-capture-bytes": {
        "defaultValue": 4194304,
        "defaultValueSource": "BootUiProperties.java:2067 (4 * 1024 * 1024L)"
    },
    "bootui.activity.persistence.dedicated-jdbc-url": {
        "defaultValue": None,
        "defaultValueSource": "BootUiProperties.java:3377"
    },
    "bootui.activity.persistence.dedicated-username": {
        "defaultValue": None,
        "defaultValueSource": "BootUiProperties.java:3380"
    },
    "bootui.activity.persistence.dedicated-password": {
        "defaultValue": None,
        "defaultValueSource": "BootUiProperties.java:3383"
    },
    "bootui.activity.persistence.dedicated-driver-class-name": {
        "defaultValue": None,
        "defaultValueSource": "BootUiProperties.java:3390"
    },
    "bootui.activity.persistence.instance-id": {
        "defaultValue": None,
        "defaultValueSource": "BootUiProperties.java:3421"
    },
    "bootui.claude-code.session-state-dir": {
        "defaultValue": None,
        "defaultValueSource": "BootUiProperties.java:2455"
    },
    "bootui.copilot.session-state-dir": {
        "defaultValue": None,
        "defaultValueSource": "BootUiProperties.java:2455"
    },
    "bootui.panels": {
        "defaultValue": None,
        "defaultValueSource": "BootUiProperties.java:82"
    }
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
            "defaultValueSource": patch["defaultValueSource"]
        }

final_properties = sorted(list(props_dict.values()), key=lambda p: p["name"])
with open(f"{output_dir}/properties.json", "w", encoding="utf-8") as f:
    json.dump({"properties": final_properties}, f, indent=2)
print(f"Wrote properties.json ({len(final_properties)} properties)")

# 8. bootui-tests.json from test classes and methods
test_files = glob.glob(f"{bootui_root}/**/src/test/java/**/*.java", recursive=True)
method_regex = re.compile(
    r'@(?:Test|ParameterizedTest|RepeatedTest|TestFactory)\b(?:\([^)]*\))?'
    r'(?:\s*@\w+(?:\([^)]*\))?)*'
    r'\s+(?:(?:public|protected|private|static|final|synchronized)\s+)*(?:void|[\w<>\[\],]+)\s+(\w+)\s*\('
)
arch_regex = re.compile(
    r'@ArchTest\b(?:\([^)]*\))?'
    r'(?:\s*@\w+(?:\([^)]*\))?)*'
    r'\s+(?:(?:public|protected|private|static|final)\s+)*(?:ArchRule|(?:void|[\w<>\[\],]+))\s+(\w+)\s*(?:\(|=)'
)

test_classes = {}
for tf in test_files:
    with open(tf, encoding="utf-8", errors="ignore") as f:
        tcode = f.read()

    cmatches = list(re.finditer(r'(?:public\s+)?(?:static\s+)?(?:final\s+)?class\s+(\w+)', tcode))
    if not cmatches:
        continue
    top_c = cmatches[0].group(1)

    meths = set()
    for mm in method_regex.finditer(tcode):
        meths.add(mm.group(1))
    for mm in arch_regex.finditer(tcode):
        meths.add(mm.group(1))

    if meths:
        test_classes[top_c] = sorted(list(meths))

with open(f"{output_dir}/bootui-tests.json", "w", encoding="utf-8") as f:
    json.dump({
        "testClasses": test_classes,
        "totalClasses": len(test_classes),
        "totalMethods": sum(len(m) for m in test_classes.values())
    }, f, indent=2)
print(f"Wrote bootui-tests.json ({len(test_classes)} test classes)")
'@

$tempPy = [System.IO.Path]::GetTempFileName() + ".py"
Set-Content -Path $tempPy -Value $pyScript -Encoding utf8
try {
    python $tempPy $BootUiPath $OutputDir
} finally {
    Remove-Item $tempPy -ErrorAction SilentlyContinue
}

Write-Host "BootUI 2.3.0 fixtures successfully captured in $OutputDir."
