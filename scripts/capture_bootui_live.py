"""Live BootUI 2.3.0 capture driven by routes.json with an allow-list."""

from __future__ import annotations

import argparse
import ipaddress
import json
import sys
import urllib.error
import urllib.request
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlsplit

REPO_ROOT = Path(__file__).resolve().parents[1]

POST_ALLOW_LIST = (
    "/security/scan",
    "/architecture/scan",
    "/rest-api/scan",
    "/vulnerabilities/scan",
    "/database-advisor/scan",
    "/hibernate/scan",
    "/spring/scan",
    "/memory/scan",
    "/postgresql/read",
    "/mysql/read",
)

ADVISOR_PANELS = (
    "security",
    "architecture",
    "rest-api",
    "vulnerabilities",
    "database-advisor",
    "hibernate",
    "spring",
    "memory",
)

EXCLUDED_ROUTES: dict[str, str] = {
    # SSE / stream routes
    "/activity/stream": "SSE stream route",
    "/exceptions/stream": "SSE stream route",
    "/log-tail/stream": "SSE stream route",
    "/rest-client-trace/stream": "SSE stream route",
    "/security-logs/stream": "SSE stream route",
    "/sql-trace/stream": "SSE stream route",
    "/transactions/stream": "SSE stream route",
    "/websockets/stream": "SSE stream route",
    "/stream": "SSE stream route",
    # Conformance probe routes with fake ids or symbols
    "/activity/request/conformance-unknown-request": "Conformance probe route with unknown request id",
    "/activity/request/conformance-unknown-request/journal": "Conformance probe route with unknown request id",
    "/code-paths/requests/0000000000000000": "Conformance probe route with fake zero id",
    "/code-paths/route?route=GET%20%2Fnot-a-route": "Conformance probe route with non-existent route",
    "/runtime-insights/impact?symbol=conformanceUnknownSymbol": "Conformance probe route with unknown symbol",
    "/runtime-insights/impact/symbols?query=conformanceUnknownSymbol": "Conformance probe route with unknown symbol",
    "/runtime-insights/insights/conformance-unknown:0000000000": "Conformance probe route with unknown id",
    "/code-inventory/methods?status=never-executed": "Conformance probe query with non-standard status",
    "/side-effects/sensor?sensor=processes": "Conformance probe query for processes sensor",
    # Raw reveal route forbidden
    "/sessions/{id}/events/{eventId}/raw": "Raw reveal route forbidden",
    # UI index endpoints
    "/${bootui.path:/bootui}": "UI index html endpoint",
    "/${bootui.path:/bootui}/": "UI index html endpoint",
    # Parameterized sub-resources requiring runtime ID or external state
    "/activity/request/{id}": "Parameterized route requiring runtime instance id",
    "/activity/request/{id}/journal": "Parameterized route requiring runtime instance id",
    "/code-paths/requests/{requestId}": "Parameterized route requiring runtime instance id",
    "/code-paths/probes/{id}": "Parameterized route requiring runtime instance id",
    "/email/{id}": "Parameterized route requiring runtime instance id",
    "/email/{id}/eml": "Parameterized route requiring runtime instance id",
    "/ai/chats/{spanId}": "Parameterized route requiring runtime instance id",
    "/data/repositories/{name}": "Parameterized route requiring repository name",
    "/database-connection-pools/pools/{name}/snapshot": "Parameterized route requiring pool name",
    "/dev-services/{id}/logs": "Parameterized route requiring service id",
    "/threads/captures/{id}": "Parameterized route requiring capture id",
    "/threads/captures/{id}/contention": "Parameterized route requiring capture id",
    "/threads/captures/{id}/locks/{lockId}": "Parameterized route requiring capture and lock id",
    "/threads/captures/{id}/threads": "Parameterized route requiring capture id",
    "/threads/captures/{id}/threads/{observationId}": "Parameterized route requiring capture and observation id",
    "/threads/observations/{id}": "Parameterized route requiring observation id",
    "/runtime-insights/insights/{id}": "Parameterized route requiring insight id",
}


@dataclass(frozen=True)
class Step:
    phase: str
    method: str
    path: str
    panel: str
    sharpit_id: str
    name: str = "captured"


def _panel_for_path(path: str, reads_map: dict[str, str]) -> str:
    if path in reads_map:
        return reads_map[path]
    cleaned = path.strip("/")
    return cleaned.split("/")[0].split("?")[0] if cleaned else "overview"


def _name_for_path(path: str, panel: str) -> str:
    cleaned = path.strip("/")
    if cleaned == panel or not cleaned:
        return "captured"
    parts = cleaned.split("/", 1)
    if len(parts) > 1:
        sub = parts[1].split("?")[0].replace("/", "-")
        return sub or "captured"
    return "captured"


def _extract_rule_ids(resp: Any) -> list[str]:
    rule_ids: list[str] = []
    if not isinstance(resp, dict):
        return rule_ids
    rule_ids.extend(str(item["id"]) for item in resp.get("results", []) if isinstance(item, dict) and "id" in item)
    for item in resp.get("findings", []):
        if isinstance(item, dict):
            found_id = item.get("ruleId") or item.get("id")
            if found_id:
                rule_ids.append(str(found_id))
    rule_ids.extend(str(item["id"]) for item in resp.get("rules", []) if isinstance(item, dict) and "id" in item)
    return rule_ids


def _build_prescan_steps(
    routes: dict[str, Any],
    ids: dict[str, str],
    reads_map: dict[str, str],
) -> list[Step]:
    seen_paths: set[str] = set()
    steps: list[Step] = []
    all_get_sources: list[str] = [
        read["path"] for read in routes.get("reads", []) if read.get("method") == "GET" and "path" in read
    ]
    all_get_sources.extend(
        mapping["path"]
        for mapping in routes.get("crossCheck", {}).get("starterMappings", [])
        if mapping.get("verb") == "GET" and "path" in mapping
    )

    for path in all_get_sources:
        if (
            path in seen_paths
            or (path in EXCLUDED_ROUTES and not EXCLUDED_ROUTES[path].startswith("Parameterized route"))
            or "/raw" in path
        ):
            continue
        if path == "/rules/{ruleId}/violations" or path.startswith("/rules"):
            continue
        seen_paths.add(path)
        panel = _panel_for_path(path, reads_map)
        sharpit_id = ids.get(panel, panel)
        name = _name_for_path(path, panel)
        steps.append(
            Step(
                phase="pre-scan GET",
                method="GET",
                path=path,
                panel=panel,
                sharpit_id=sharpit_id,
                name=name,
            )
        )
    return steps


def build_plan(routes: dict[str, Any], ids: dict[str, str]) -> list[Step]:
    """Build a deterministic capture plan in four phases from routes.json and ids.json."""
    reads_map = {r["path"]: r["panel"] for r in routes.get("reads", []) if "path" in r and "panel" in r}
    action_paths = {a.get("path") for a in routes.get("actions", [])}

    # Phase 1: pre-scan GET
    steps = _build_prescan_steps(routes, ids, reads_map)

    # Phase 2: allow-listed POST
    for post_path in POST_ALLOW_LIST:
        if post_path in action_paths and "/raw" not in post_path:
            panel = post_path.strip("/").split("/")[0]
            sharpit_id = ids.get(panel, panel)
            action_name = post_path.strip("/").split("/")[1]
            steps.append(
                Step(
                    phase="allow-listed POST",
                    method="POST",
                    path=post_path,
                    panel=panel,
                    sharpit_id=sharpit_id,
                    name=action_name,
                )
            )

    # Phase 3: post-scan GET
    for post_path in POST_ALLOW_LIST:
        if post_path in action_paths and "/raw" not in post_path:
            panel = post_path.strip("/").split("/")[0]
            sharpit_id = ids.get(panel, panel)
            get_path = f"/{panel}"
            steps.append(
                Step(
                    phase="post-scan GET",
                    method="GET",
                    path=get_path,
                    panel=panel,
                    sharpit_id=sharpit_id,
                    name="scanned",
                )
            )

    # Phase 4: violations
    for advisor in ADVISOR_PANELS:
        sharpit_id = ids.get(advisor, advisor)
        viol_path = f"/{advisor}/rules/{{ruleId}}/violations?limit=5"
        steps.append(
            Step(
                phase="violations",
                method="GET",
                path=viol_path,
                panel=advisor,
                sharpit_id=sharpit_id,
                name="violations",
            )
        )

    return steps


def _resolve_raw_out(raw_out: Path | str) -> Path:
    raw_path = Path(raw_out).resolve()
    current = raw_path
    while current != current.parent:
        if (current / ".git").exists():
            raise ValueError(f"raw_out must not be inside the git repo root/work tree: {raw_out}")
        current = current.parent
    raw_path.mkdir(parents=True, exist_ok=True)
    return raw_path


def _fetch(opener: Any, base_url: str, method: str, path: str) -> Any:
    url = f"{base_url.rstrip('/')}{path}"
    data = b"{}" if method == "POST" else None
    req = urllib.request.Request(url, data=data, method=method)
    if hasattr(opener, "open"):
        resp = opener.open(req, timeout=30)
    elif callable(opener):
        resp = opener(req)
    else:
        resp = urllib.request.urlopen(req, timeout=30)
    if hasattr(resp, "read"):
        content = resp.read()
        return json.loads(content.decode("utf-8")) if content else {}
    if isinstance(resp, (dict, list)):
        return resp
    return {}


def _record_error(
    uncaptured: dict[str, dict[str, Any]],
    key: str,
    exc: Exception,
) -> None:
    code = getattr(exc, "code", None)
    if code == 404:
        status: Any = "404"
    elif code == 403:
        status = "disabled"
    else:
        status = "error"
    uncaptured[key] = {"status": status, "http": code, "reason": str(exc)}


def _resolve_parameterized_path(path: str, responses: dict[str, Any]) -> str | None:
    if "{" not in path:
        return path
    root = path.split("/{", 1)[0]
    field = path.split("{", 1)[1].split("}", 1)[0]
    parent = responses.get(root)
    items = (
        parent
        if isinstance(parent, list)
        else next(
            (
                parent.get(key)
                for key in ("items", "results", "sessions", "exceptions", "traces")
                if isinstance(parent, dict) and isinstance(parent.get(key), list)
            ),
            [],
        )
    )
    first = items[0] if items and isinstance(items[0], dict) else {}
    item_id = first.get("id") or first.get("traceId")
    return path.replace("{" + field + "}", quote(str(item_id), safe=""), 1) if item_id else None


def _write_capture(
    raw_out: Path,
    sharpit_id: str,
    name: str,
    data: Any,
) -> None:
    panel_dir = raw_out / sharpit_id
    panel_dir.mkdir(parents=True, exist_ok=True)
    filename = "captured.json" if name in ("", "captured") else f"{name}.captured.json"
    (panel_dir / filename).write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _run_violations(
    step: Step,
    post_scan_responses: dict[str, Any],
    opener: Any,
    base_url: str,
    raw_out: Path,
    uncaptured: dict[str, dict[str, Any]],
) -> None:
    post_resp = post_scan_responses.get(step.panel, {})
    rule_ids = _extract_rule_ids(post_resp)
    if not rule_ids:
        uncaptured[f"GET {step.path}"] = {
            "status": "not-probed",
            "http": None,
            "reason": "No rule violations in scan response",
        }
        return
    rule_id = rule_ids[0]
    viol_path = step.path.replace("{ruleId}", quote(rule_id, safe=""))
    if "/raw" in viol_path:
        uncaptured[f"GET {step.path}"] = {
            "status": "not-probed",
            "http": None,
            "reason": "final path refused by safety rules",
        }
        return
    scan_id = (
        post_resp.get("violationDetails", {}).get("scanId")
        if isinstance(post_resp.get("violationDetails"), dict)
        else None
    )
    if scan_id and "scanId=" not in viol_path:
        viol_path = f"{viol_path}&scanId={scan_id}"
    try:
        data = _fetch(opener, base_url, "GET", viol_path)
        _write_capture(raw_out, step.sharpit_id, step.name, data)
    except Exception as exc:
        _record_error(uncaptured, f"GET {viol_path}", exc)


def _run_step(
    step: Step,
    opener: Any,
    base_url: str,
    raw_path: Path,
    uncaptured: dict[str, dict[str, Any]],
    post_scan_responses: dict[str, Any],
    list_responses: dict[str, Any],
) -> None:
    if step.phase == "violations":
        _run_violations(step, post_scan_responses, opener, base_url, raw_path, uncaptured)
        return
    try:
        path = _resolve_parameterized_path(step.path, list_responses)
        if path is None:
            uncaptured[f"{step.method} {step.path}"] = {
                "status": "not-probed",
                "http": None,
                "reason": "no id in the list response",
            }
            return
        data = _fetch(opener, base_url, step.method, path)
        if step.method == "GET" and "{" not in step.path:
            list_responses[step.path.rstrip("/")] = data
        if step.method == "POST" or step.phase == "post-scan GET":
            post_scan_responses[step.panel] = data
        _write_capture(raw_path, step.sharpit_id, step.name, data)
    except Exception as exc:
        _record_error(uncaptured, f"{step.method} {step.path}", exc)


def run(
    plan: list[Step],
    opener: Any,
    raw_out: Path | str,
    base_url: str = "http://127.0.0.1:8080/bootui/api",
) -> dict[str, Any]:
    """Execute plan writing raw captures to raw_out and uncaptured entries to uncaptured.json."""
    raw_path = _resolve_raw_out(raw_out)
    uncaptured: dict[str, dict[str, Any]] = {}
    post_scan_responses: dict[str, Any] = {}
    list_responses: dict[str, Any] = {}
    for path, reason in EXCLUDED_ROUTES.items():
        if reason.startswith("Conformance probe"):
            uncaptured[f"GET {path}"] = {"status": "not-probed", "http": None, "reason": "conformance probe"}

    for step in plan:
        if (
            step.method not in ("GET", "POST")
            or (step.method == "POST" and step.path not in POST_ALLOW_LIST)
            or "/raw" in step.path
        ):
            raise ValueError(f"method/path not allowed: {step.method} {step.path}")

        _run_step(step, opener, base_url, raw_path, uncaptured, post_scan_responses, list_responses)

    uncaptured_file = raw_path / "uncaptured.json"
    uncaptured_file.write_text(json.dumps(uncaptured, indent=2) + "\n", encoding="utf-8")
    return uncaptured


def build_default_opener(token_file: Path | str | None = None) -> Any:
    """Build a urllib opener with Authorization / X-BootUI-Token header from token_file."""
    headers: dict[str, str] = {}
    if token_file:
        token = Path(token_file).read_text(encoding="utf-8").strip()
        headers["Authorization"] = f"Bearer {token}"

    class HeaderOpener:
        def open(self, req: urllib.request.Request | str) -> Any:
            if isinstance(req, str):
                req = urllib.request.Request(req)
            for k, v in headers.items():
                req.add_header(k, v)
            return urllib.request.urlopen(req)

    return HeaderOpener()


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Capture live BootUI 2.3.0 raw responses.")
    parser.add_argument("--base", default="http://127.0.0.1:8080/bootui/api", help="BootUI API base URL.")
    parser.add_argument("--token-file", help="Path to file containing BootUI auth token.")
    parser.add_argument("--raw-out", required=True, help="Directory to write raw captures (must be outside repo).")
    parser.add_argument(
        "--routes",
        default=str(REPO_ROOT / "tests/fixtures/bootui/2.3.0/routes.json"),
        help="Path to routes.json.",
    )
    parser.add_argument(
        "--ids",
        default=str(REPO_ROOT / "tests/fixtures/bootui/2.2.0/ids.json"),
        help="Path to ids.json.",
    )
    args = parser.parse_args(argv if argv is not None else sys.argv[1:])

    parsed_base = urlsplit(args.base)
    try:
        loopback = parsed_base.hostname in ("localhost", "127.0.0.1", "::1") or (
            parsed_base.hostname is not None and ipaddress.ip_address(parsed_base.hostname).is_loopback
        )
    except ValueError:
        loopback = False
    if parsed_base.scheme != "http" or not loopback:
        parser.error("--base must use http and a loopback host")

    routes = json.loads(Path(args.routes).read_text(encoding="utf-8"))
    ids = json.loads(Path(args.ids).read_text(encoding="utf-8")) if Path(args.ids).is_file() else {}
    plan = build_plan(routes, ids)
    opener = build_default_opener(args.token_file)
    run(plan, opener, args.raw_out, base_url=args.base)
    return 0


if __name__ == "__main__":
    sys.exit(main())
