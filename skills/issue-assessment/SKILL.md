---
name: issue-assessment
version: "1.0"
description: >
  Use when asked to assess, triage or size a sharpit GitHub issue before deciding whether to fix it. Read-only: it
  reproduces, classifies and recommends; it never edits code or opens a PR.
---

# `issue-assessment`: read-only triage

## 1. Read the issue

```bash
gh issue view <N> --comments
```

Extract: the symptom, the host app (FastAPI version, Starlette version, server: uvicorn/hypercorn/gunicorn), how it is
started (`fastapi dev`, `uvicorn --reload`, programmatic), the sharpit settings in play, and the expected behaviour.

## 2. Classify the surface

| Class | Signals | Severity floor |
|---|---|---|
| **Safety: fails open** | Panel reachable when it should 404; activation on in prod; guard bypassed; a secret shown unmasked | Critical |
| **Side effect** | A GET or MCP call wrote a file, opened a socket, changed a logger or `os.environ` | High |
| **Contract drift** | JSON shape differs from BootUI's contract or golden fixture; wrong error string | High |
| **Introspection drift** | A FastAPI/Starlette version changed route, dependency or middleware internals | Medium |
| **OSV / network** | Vulnerability scan timeout, offline failure mode, wrong EPSS data | Medium |
| **Host integration** | Mount order, root_path, sub-apps, lifespan, ASGI middleware interaction | Medium |
| **UI** | Rendering or state issue in the bundled UI | Low |

Anything that could fail open is Critical regardless of how rare.

## 3. Reproduce (read-only)

Write a throwaway reproduction in the session scratchpad, never in the repo: a minimal FastAPI app,
`sharpit.install(app, ...)`, and a Starlette `TestClient` hitting the reported path. Record the exact output. If it
does not reproduce, say what you tried.

## 4. Locate the cause

Name the module and function (`engine/activation.py`, `engine/guard.py`, `engine/masking.py`, `fastapi/introspect*.py`,
`fastapi/adapter.py`) and the BootUI counterpart it ports, if any. Check `/sharpit:known-issues` and the spec §14 for an
existing deviation that explains it.

## 5. Report

```
Issue #N: <title>
Class / severity: ...
Reproduced: yes / no (how)
Cause: <file:function>, evidence ...
Fix size: XS (<10 lines) / S / M / L (needs /sharpit:predict and a plan)
Recommendation: /sharpit:issue-resolve N | needs a plan | won't fix (why) | needs info (questions)
```

Never comment on the issue or change labels unless asked.

Ported from gflow-cli's `issue-assessment`; classes replaced with sharpit's failure surfaces.
