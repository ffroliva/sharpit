---
name: predict
version: "1.0"
description: >
  Use before implementing a high-stakes sharpit change: activation or guard-chain logic, masking, a new endpoint or
  MCP tool, a contract/DTO change, a new collector, a new runtime dependency, or anything that writes, opens a socket
  or changes process state. Five personas review the proposal independently and converge on GO / CAUTION / STOP.
---

# `predict`: pre-implementation five-persona review

The cheapest place to catch a design flaw is before the first commit. Five personas assess the proposal
**independently**, then their findings are reconciled into one verdict with a confidence score.

## When to invoke

- Activation (`engine/activation.py`, `fastapi/signals.py`) or the request guard chain (`engine/guard.py`).
- Masking (`engine/masking.py`) or anything that adds a new output surface (error text, MCP `structuredContent`,
  `description`, `defaultValue`).
- A new or changed endpoint, panel, MCP tool or JSON field (BootUI contract parity).
- A new collector, or a change to how FastAPI/Starlette internals are introspected.
- A new runtime dependency, a write to disk, a network call, a logger change.

Skip for: a bug fix under ~10 lines with a proven cause and no boundary crossed, an already-approved plan task, docs.

## Invocation

```
/sharpit:predict <one-paragraph proposal>
```

## Protocol

### Phase 1: persona briefings (independent)

Each persona reads `AGENTS.md`, the design spec (`docs/superpowers/specs/2026-10-30-sharpit-mvp-design.md`, especially
§4 anti-goals, §7 safety, §14 deviation log), `docs/reference/BOOTUI-CONTRACT-MVP.md` for the touched section, and
the source files involved. With subagents available, dispatch the five in parallel; otherwise write each one out in
turn without reading the others first.

**1. Architect** (engine/adapter seam, dependencies)
- Does framework-neutral logic stay in `engine/` and FastAPI-specific code in `fastapi/`? Does `engine/` import
  FastAPI or pydantic anywhere outside `try/except ImportError`?
- Runtime dependencies stay exactly `starlette` and `packaging`. Anything else is a STOP.
- Does `install()` stay cheap (settings, activation, mounting; median ≤ 50 ms) with expensive work lazy and memoised?
- Will the Django/Flask adapters (next after MVP) be able to reuse this, or does it leak FastAPI types into the engine?

**2. Security** (fail-closed activation, guard chain, masking, side effects)
- Can this make sharpit active in production, e.g. a profile spelled `Production`, ` prod ` or `prod,dev`?
- Does every request under the mount still pass security headers → trusted source → Host allow-list → cross-site →
  token → panel access, in that order? Do forwarded headers ever *grant* trust?
- Can a secret reach any output unmasked: values, `defaultValue`, error messages, MCP results, `q` probing?
- Does any GET or MCP tool now open a socket, write a file, change a logger level or touch `os.environ`?
- Any code-execution surface (`eval`, `exec`, dynamic import from input, shell)? That is a STOP.

**3. Contract parity** (BootUI as the oracle)
- Which contract section does this touch? Is every key emitted (nulls included), camelCase, epoch ms, no envelope?
- Are error bodies and reason strings verbatim from contract §1/§10 with `BootUI`→`sharpit` and
  `bootui.<prop>`→`SHARPIT_<PROP>`?
- Does a golden fixture under `tests/fixtures/bootui/` cover the shape? Are ported tests cited
  (`# ported: <BootUI test>.<case>`)?
- Is any divergence from BootUI logged in spec §14? Unlogged deviations are bugs.

**4. Host-app compatibility** (FastAPI/Starlette reality)
- Which Starlette/FastAPI internals does it read (`app.router.routes`, `dependant`, lifespan, middleware stack)? What
  happens on the floor versions (`fastapi>=0.115`, `starlette>=0.40`) and on the newest release?
- Does it survive a host with `TrustedHostMiddleware`, `CORSMiddleware(allow_origins=["*"])`, auth middleware and an
  SPA catch-all route?
- Large apps: ~300 routes, ~80 getenv keys, ~200 distributions. Do pages stay ≤ 1000 items?
- Windows and POSIX paths; uvicorn `--reload`, `--workers`, `fastapi dev`.

**5. Devil's Advocate** (YAGNI, sequencing)
- Is there a smaller change that gives the same user outcome? Does BootUI already solve it more simply?
- Is it in the MVP's goals (spec §2) or explicitly a non-goal (§3)?
- Does an open issue or a §15 coordinator's call make it risky or premature?
- What is the cheapest experiment (a `/sharpit:spike`) that would prove or kill the core assumption?

Each persona returns findings, a confidence `0–10` and any STOP conditions.

### Phase 2: reconcile

1. A concern raised by two or more personas is a high-confidence risk.
2. Surface conflicts explicitly; never silently drop one view.
3. Confidence = mean of the five, then: any STOP → **STOP**; Devil's Advocate found a simpler path the others missed
   → −2; all five agree → +1.

### Phase 3: verdict

- **GO** (≥ 7, no STOP): proceed to `/sharpit:scenario` or `/sharpit:plan`.
- **CAUTION** (4–6, or one unresolved STOP candidate): proceed, but the plan must carry the named mitigations.
- **STOP** (< 4, or any hard stop): a new runtime dependency; a code-execution surface; a way for sharpit to be active
  in production or reachable cross-site; a secret leaving unmasked; a side effect on GET/MCP; an unlogged BootUI
  deviation; or a simpler approach that makes this one wasteful. State the minimum change that turns it into CAUTION.

## Output

```
# Predict: <title>
## Verdict: <GO | CAUTION | STOP>   Confidence: <N>/10
## Summary (2-3 sentences)
## Persona findings
### Architect: <signal> (<n>/10)
### Security: ...
### Contract parity: ...
### Host-app compatibility: ...
### Devil's Advocate: ...
## High-confidence risks (2+ personas)
## Conflicts resolved
## Required mitigations (CAUTION only)
## Recommended next step (one sentence)
```

## Next step

GO → "Next: `/sharpit:scenario <feature>` then `/sharpit:plan <feature>`." CAUTION → put the mitigations in the plan.
STOP → resolve the blocking concern or run `/sharpit:spike` first.

Ported from gflow-cli's `predict` skill (itself adapted from `vc-predict` in vibecode-pro-max-kit); personas rewritten
for sharpit.
