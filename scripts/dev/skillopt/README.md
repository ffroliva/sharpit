# SkillOpt harness for sharpit

Measures how accurately an LLM answers sharpit usage questions when guided only by the user-facing skill
[`skills/sharpit/SKILL.md`](../../../skills/sharpit/SKILL.md). It is the rollout → score half of the
[SkillOpt](https://github.com/microsoft/SkillOpt) loop: measure a baseline, edit the skill, and keep the edit only if
the score goes up. Ported from gflow-cli's harness; the workflow around it is [`/sharpit:optimize`](../../../skills/optimize/SKILL.md).

## Run it

```bash
# Dry run: prompts and scoring specs only. No key, no network.
uv run python scripts/dev/skillopt/harness.py --dry-run

# Live run against any OpenAI-compatible Chat Completions endpoint
SKILLOPT_BASE_URL=https://api.openai.com/v1 SKILLOPT_API_KEY=sk-... SKILLOPT_MODEL=gpt-4o-mini \
  uv run python scripts/dev/skillopt/harness.py

# Local keyless gateway (Ollama, LM Studio): http is accepted on loopback only
SKILLOPT_BASE_URL=http://127.0.0.1:11434/v1 SKILLOPT_MODEL=llama3.2 uv run python scripts/dev/skillopt/harness.py

# Filter by tag, or score a candidate edit against the same tasks
uv run python scripts/dev/skillopt/harness.py --tags activation,safety --dry-run
uv run python scripts/dev/skillopt/harness.py --skill /tmp/SKILL_candidate.md
```

A live run calls a paid or rate-limited API: run it in the background and only when the owner asked for it. The key is
sent only as an `Authorization` header, redirects are refused, and error bodies are not echoed.

## Dataset (`tasks.json`)

16 tasks: `setup` (2), `activation` (4), `config` (6), `panels` (2), `mcp` (2), `safety` (8); tags overlap.

```json
{
  "id": "mcp-001",
  "question": "How do I let my coding agent read sharpit through MCP?",
  "context": "optional",
  "expected": {"must_include": ["SHARPIT_MCP_ENABLED"], "must_not_include": ["stdio"], "partial_credit": ["read-only"]},
  "tags": ["mcp"],
  "notes": "Why agents get this wrong."
}
```

Every expected answer must be derivable from the skill and true in `src/sharpit/`; a task that rewards a wrong
answer trains the skill toward it.

## Scoring

| Field | Effect |
|---|---|
| `must_include` | base = hits / N (1.0 when empty) |
| `must_not_include` | −0.30 per hit, capped at −0.90 |
| `partial_credit` | +0.10 per hit, capped at +0.30 |
| final | `max(0, min(1, base − penalty + bonus))`, rounded to 4 places |

Matching is case-insensitive substring. PASS ≥ 0.80, PARTIAL ≥ 0.40, else FAIL. A rollout that errors (HTTP failure,
empty answer) is reported and excluded from the average: it is missing data, not a zero.

## Tests

`tests/scripts/test_skillopt.py` covers scoring, the dataset's shape and the dry run. No test calls an API.
