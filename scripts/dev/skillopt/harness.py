#!/usr/bin/env python3
"""SkillOpt harness for sharpit's user-facing skill (ported from gflow-cli's ``scripts/dev/skillopt``).

Scores how accurately an LLM answers sharpit usage questions when the skill document is its only reference: the
rollout -> score half of the SkillOpt loop (https://github.com/microsoft/SkillOpt), so a skill edit can be measured
against a baseline before it is accepted.

    # No key, no network: print every prompt and its scoring spec.
    uv run python scripts/dev/skillopt/harness.py --dry-run

    # Any OpenAI-compatible Chat Completions endpoint (OpenAI, OpenRouter, LiteLLM, local Ollama/LM Studio).
    SKILLOPT_API_KEY=sk-... SKILLOPT_BASE_URL=https://api.openai.com/v1 SKILLOPT_MODEL=gpt-4o-mini \
        uv run python scripts/dev/skillopt/harness.py

Flags: ``--skill PATH`` (a candidate edit), ``--tasks PATH`` (must match ``--skill``), ``--tags a,b``, ``--model ID``.
Configuration is three env vars only: ``SKILLOPT_BASE_URL`` (https, or http on loopback), ``SKILLOPT_API_KEY``
(optional for a local gateway, sent only as a header) and ``SKILLOPT_MODEL`` (optional).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[3]
TASKS_PATH = Path(__file__).parent / "tasks.json"
DEFAULT_SKILL_PATH = REPO_ROOT / "skills" / "sharpit" / "SKILL.md"
PASS_THRESHOLD = 0.8
_MAX_ATTEMPTS = 4
_RETRYABLE = {429, 500, 502, 503, 504}
_TIMEOUT = 60.0

SYSTEM_TEMPLATE = """\
You are an assistant helping a Python developer use sharpit, an embedded, local-only developer console for FastAPI
apps (a port of BootUI).

Answer with the exact code, environment variables, URLs or commands the developer needs, plus at most two short
sentences of explanation. Use the skill reference below as your only authoritative source; if it does not say, say so.

=== SKILL REFERENCE (sharpit skill v{version}, epoch {epoch}) ===
{skill_body}
=== END SKILL REFERENCE ==="""


class RolloutError(RuntimeError):
    """One task's rollout could not be completed. The suite records it and carries on."""


def load_tasks(path: Path, tags: list[str] | None = None) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = json.loads(path.read_text(encoding="utf-8"))
    if tags:
        wanted = set(tags)
        items = [t for t in items if wanted.intersection(t.get("tags", []))]
    return items


def load_skill(path: Path) -> tuple[str, str, int]:
    """Return (full_text, version, skillopt_epoch) from the skill file's frontmatter."""
    text = path.read_text(encoding="utf-8")
    version, epoch = "unknown", 0
    for line in text.splitlines():
        if line.startswith("version:"):
            version = line.split(":", 1)[1].strip().strip('"')
        elif line.startswith("skillopt_epoch:") and line.split(":", 1)[1].strip().isdigit():
            epoch = int(line.split(":", 1)[1].strip())
    return text, version, epoch


def score_response(response: str, expected: dict[str, Any]) -> tuple[float, list[str]]:
    """Score one answer: (score 0.0-1.0, reasons). Matching is case-insensitive substring."""
    low = response.lower()
    must: list[str] = expected.get("must_include", [])
    forbidden: list[str] = expected.get("must_not_include", [])
    partial: list[str] = expected.get("partial_credit", [])

    misses = [m for m in must if m.lower() not in low]
    base = (len(must) - len(misses)) / len(must) if must else 1.0
    forbidden_hits = [f for f in forbidden if f.lower() in low]
    bonus_hits = [p for p in partial if p.lower() in low]
    penalty = min(len(forbidden_hits) * 0.3, 0.9)
    bonus = min(len(bonus_hits) * 0.1, 0.3)
    # Rounded: 1.0 - 0.3 + 0.1 is 0.7999999999999999 in binary float, which would grade a printed "0.80" PARTIAL.
    score = round(max(0.0, min(1.0, base - penalty + bonus)), 4)

    reasons: list[str] = []
    if misses:
        reasons.append(f"MISS: {misses}")
    if forbidden_hits:
        reasons.append(f"FORBIDDEN hit: {forbidden_hits}")
    if bonus_hits:
        reasons.append(f"BONUS: {bonus_hits}")
    return score, reasons


def grade(score: float) -> str:
    return "PASS" if score >= PASS_THRESHOLD else ("PARTIAL" if score >= 0.4 else "FAIL")


def format_prompt(skill_text: str, version: str, epoch: int, task: dict[str, Any]) -> tuple[str, str]:
    system = SYSTEM_TEMPLATE.format(version=version, epoch=epoch, skill_body=skill_text)
    context = task.get("context")
    user = f"Context: {context}\n\n{task['question']}" if context else task["question"]
    return system, user


def run_dry(tasks: list[dict[str, Any]], skill_text: str, version: str, epoch: int) -> None:
    print(f"=== DRY RUN - {len(tasks)} task(s) - skill v{version} epoch {epoch} ===\n")
    for task in tasks:
        _, user = format_prompt(skill_text, version, epoch, task)
        print(f"--- [{task['id']}] {task['question'][:80]} ---")
        print(f"USER PROMPT:\n{user}\n")
        print(f"SCORING: {task['expected']}\n")
        print(f"NOTES: {task.get('notes', '')}\n")


def check_base_url(url: str) -> str:
    """Accept https, or http only on loopback, so a key is never sent in clear text over a network."""
    parts = urllib.parse.urlsplit(url)
    if parts.scheme == "https" or (parts.scheme == "http" and parts.hostname in ("127.0.0.1", "localhost", "::1")):
        return url.rstrip("/")
    raise SystemExit(f"SKILLOPT_BASE_URL must be https (or http on loopback), got {url!r}")


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args: Any, **kwargs: Any) -> None:  # a redirect could carry the key elsewhere
        return None


def _call_llm(system: str, user: str, model: str | None, base_url: str, key: str | None) -> str:
    payload: dict[str, object] = {
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        "temperature": 0.0,
        "max_tokens": 512,
    }
    if model:
        payload["model"] = model
    headers = {"Content-Type": "application/json"}
    if key:
        headers["Authorization"] = f"Bearer {key}"
    opener = urllib.request.build_opener(_NoRedirect)
    for attempt in range(_MAX_ATTEMPTS):
        req = urllib.request.Request(
            f"{base_url}/chat/completions", json.dumps(payload).encode(), headers, method="POST"
        )
        try:
            with opener.open(req, timeout=_TIMEOUT) as resp:
                node = json.loads(resp.read())
            break
        except urllib.error.HTTPError as exc:
            if exc.code not in _RETRYABLE or attempt == _MAX_ATTEMPTS - 1:
                raise RolloutError(f"HTTP {exc.code}") from exc  # body not echoed: gateways may echo the key
            delay = 30 * (attempt + 1) if exc.code == 429 else 2**attempt  # free tiers meter per minute
            print(f"  (HTTP {exc.code} - retrying in {delay}s)")
            time.sleep(delay)
        except (OSError, ValueError) as exc:
            raise RolloutError(type(exc).__name__) from exc
    else:  # pragma: no cover - the loop always breaks or raises
        raise RolloutError("exhausted retries")
    try:
        content = node["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise RolloutError("unexpected response shape") from exc
    if not isinstance(content, str) or not content.strip():
        raise RolloutError("response carried no assistant text (refusal or unexpected shape)")
    return content.strip()


def summarise(results: list[dict[str, Any]]) -> str:
    """Errored rollouts are missing data, not zeros: they are named and kept out of the average."""
    if not results:
        return "No results."
    errored = [r for r in results if r["status"] == "ERROR"]
    scored = [r for r in results if r["status"] != "ERROR"]
    out = ["=" * 60]
    if scored:
        passed = sum(1 for r in scored if r["status"] == "PASS")
        avg = sum(r["score"] for r in scored) / len(scored)
        out.append(f"SUMMARY: {passed}/{len(scored)} passed  avg score {avg:.3f}")
    else:
        out.append("SUMMARY: no task completed a rollout")
    if errored:
        out.append(f"  {len(errored)} of {len(results)} task(s) did not complete and are excluded:")
        out += [f"    {r['id']}: {r['reasons'][0]}" for r in errored]
    failed = [r for r in scored if r["status"] == "FAIL"]
    if failed:
        out.append(f"Failed tasks ({len(failed)}):")
        out += [f"  {r['id']}: {r['reasons']}" for r in failed]
    by_tag: dict[str, list[float]] = {}
    for r in scored:
        for tag in r.get("tags", []):
            by_tag.setdefault(tag, []).append(r["score"])
    if by_tag:
        out.append("Per-tag averages:")
        out += [f"  {t:<20} {sum(s) / len(s):.3f}  (n={len(s)})" for t, s in sorted(by_tag.items())]
    out.append("=" * 60)
    return "\n".join(out)


def run_live(
    tasks: list[dict[str, Any]],
    skill_text: str,
    version: str,
    epoch: int,
    model: str | None,
    base_url: str,
    key: str | None,
) -> list[dict[str, Any]]:
    print(f"=== LIVE RUN - {len(tasks)} task(s) - skill v{version} epoch {epoch} - model {model or '(default)'} ===\n")
    results: list[dict[str, Any]] = []
    for i, task in enumerate(tasks, 1):
        system, user = format_prompt(skill_text, version, epoch, task)
        print(f"[{i}/{len(tasks)}] {task['id']}: {task['question'][:70]}")
        row: dict[str, Any] = {"id": task["id"], "tags": task.get("tags", [])}
        try:
            response = _call_llm(system, user, model, base_url, key)
        except RolloutError as exc:  # keep going: completed rollouts are the expensive half of the run
            print(f"  ERROR: {exc}")
            results.append({**row, "score": 0.0, "status": "ERROR", "reasons": [f"ERROR: {exc}"]})
            continue
        score, reasons = score_response(response, task["expected"])
        print(f"  Score: {score:.2f} [{grade(score)}]  {' | '.join(reasons) or 'OK'}")
        results.append({**row, "score": score, "status": grade(score), "reasons": reasons})
    print(summarise(results))
    return results


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="SkillOpt harness for skills/sharpit/SKILL.md")
    parser.add_argument("--skill", type=Path, default=DEFAULT_SKILL_PATH)
    parser.add_argument("--tasks", type=Path, default=TASKS_PATH)
    parser.add_argument("--tags", default=None, help="comma-separated tag filter")
    parser.add_argument("--model", default=None, help="overrides SKILLOPT_MODEL")
    parser.add_argument("--dry-run", action="store_true", help="print prompts and scoring specs; no network")
    args = parser.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
    for path in (args.skill, args.tasks):
        if not path.is_file():
            print(f"Not found: {path}", file=sys.stderr)
            return 2
    tags = [t.strip() for t in args.tags.split(",")] if args.tags else None
    tasks = load_tasks(args.tasks, tags)
    if not tasks:
        print("No tasks matched the given filter.", file=sys.stderr)
        return 2
    skill_text, version, epoch = load_skill(args.skill)
    if args.dry_run:
        run_dry(tasks, skill_text, version, epoch)
        return 0
    base = os.environ.get("SKILLOPT_BASE_URL")
    if not base:
        print("Set SKILLOPT_BASE_URL (plus SKILLOPT_API_KEY / SKILLOPT_MODEL), or use --dry-run.", file=sys.stderr)
        return 2
    model = args.model or os.environ.get("SKILLOPT_MODEL") or None
    run_live(tasks, skill_text, version, epoch, model, check_base_url(base), os.environ.get("SKILLOPT_API_KEY") or None)
    return 0


if __name__ == "__main__":
    sys.exit(main())
