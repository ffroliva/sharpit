---
name: spike
version: "1.0"
description: >
  Use when a sharpit question can only be answered by trying it: "does FastAPI expose X at runtime?", "can we detect
  hypercorn reload?", "how fast is the OSV batch API?". Time-boxed throwaway code, a written verdict, nothing merged.
---

# `spike`: time-boxed experiment

A spike buys an answer, not code. Its output is a verdict document; the code is thrown away.

## 1. Frame (before any code)

```
Question: <one yes/no or how-much question>
Why it matters: <which decision waits on it: predict verdict, plan task, deviation>
Time box: <30 min / 2 h; default 1 h>
Done when: <the observation that answers it>
```

## 2. Isolate

Work in the session scratchpad or a throwaway worktree (`git worktree add ../sharpit-spike-<slug> -b spike/<slug>`).
Never in the main checkout, never on `master`. Network calls (OSV, PyPI) are allowed in a spike but must be named in
the verdict, because product code must survive their failure.

## 3. Try

The smallest program that produces the observation: a 20-line FastAPI app, a `TestClient` call, a `python -c` that
prints an internal. Pin versions (`uv run --with fastapi==X.Y`) when the question is version-sensitive, and try at least
the lowest supported and the newest version.

## 4. Verdict

Write `docs/superpowers/spikes/<YYYY-MM-DD>-<slug>.md`:

```markdown
# Spike: <question>
**Answer:** yes / no / <number>, confidence high/medium/low
**Evidence:** the command, the versions, the output (trimmed)
**Implication:** what the plan or predict verdict should now say
**Not checked:** what the time box left out
```

Commit only the verdict (`docs: spike <slug>`), then delete the worktree and branch. If the time box expires, write the
verdict anyway with the answer "unknown" and what was learnt.

## 5. Hand back

Feed the answer into `/sharpit:predict` or `/sharpit:plan`. A spike never turns into the implementation by
copy-paste: the real change is written test-first.

Ported from gflow-cli's `spike` skill.
