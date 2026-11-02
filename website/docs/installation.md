# Installation

Install sharpit from PyPI with the FastAPI host extra:

```bash
pip install "sharpit[fastapi]"
# or
uv add "sharpit[fastapi]"
```

Python 3.12+. Runtime dependencies are only `starlette>=0.44` and `packaging>=23`. Optional extras:

| Extra | Adds | Why |
|---|---|---|
| `sharpit[fastapi]` | `fastapi>=0.115` | the supported host |
| `sharpit[settings]` | `pydantic-settings>=2.4` | the Config panel shows which source each value came from |
