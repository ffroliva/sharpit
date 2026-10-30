---
name: live-verify
version: "1.0"
description: >
  Use before claiming a sharpit change to an endpoint, the guard, activation or the UI works: runs a minimal FastAPI app
  with sharpit installed and hits /sharpit/api for real, recording the evidence.
---

# `live-verify`: run a real app and hit the API

Unit tests prove the parts; this proves the installed whole. Evidence goes in the PR, not in the repo.

## 1. The sample app (scratchpad, not the repo)

```python
# <scratchpad>/live_app.py
from fastapi import FastAPI

import sharpit

app = FastAPI()


@app.get("/hello")
def hello() -> dict[str, str]:
    return {"hello": "world"}


handle = sharpit.install(app, enabled="ON")  # or rely on the dev-server signal below
```

## 2. In-process check (always)

```bash
uv run python - <<'EOF'
import sys; sys.path.insert(0, "<scratchpad>")
from starlette.testclient import TestClient
from live_app import app
c = TestClient(app)
for path in ["/sharpit/api/panels", "/sharpit/api/overview", "/sharpit/api/config"]:
    r = c.get(path); print(path, r.status_code, r.text[:200])
EOF
```

Use only routes that exist on the branch (`grep -n "Route(" src/sharpit/fastapi/adapter.py`).

## 3. Real server check (when activation, the guard or the UI changed)

```bash
cd <scratchpad> && uv run --project <repo> fastapi dev live_app.py --port <leased port>   # background it
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:<port>/sharpit/api/panels
curl -s -H "Host: evil.example" -o /dev/null -w "%{http_code}\n" http://127.0.0.1:<port>/sharpit/api/panels
```

Lease the port first when other agents are registered (`multi-agent-dev`). Stop the server by its task id or PID.

## 4. Fail-closed checks (always, both modes)

| Setup | Expected |
|---|---|
| `SHARPIT_ENABLED=OFF` | every `/sharpit/...` path → 404 |
| No dev-server signal, no `SHARPIT_ENABLED=ON`, no enabled profile | 404 |
| Disallowed `Host` header | rejected by the guard, never 200 |
| A secret-looking env var (`DB_PASSWORD=abc123`) | `/sharpit/api/config` shows it masked |
| `SHARPIT_PANELS_CONFIG_ENABLED=false` | the config route refuses, the panel list omits or disables it |

## 5. Evidence

A table `check | command | status | expected | result` pasted into the PR. A row that could not run is "not checked",
never "passed".

Adapted from gflow-cli's `live-verify` (which drove a browser against a remote web service) to sharpit's install-and-hit check.
