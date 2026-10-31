# Installation

sharpit is not on PyPI yet. Install it from git:

```bash
pip install "sharpit @ git+https://github.com/ffroliva/sharpit.git"
# or
uv add "sharpit @ git+https://github.com/ffroliva/sharpit.git"
```

Python 3.12+. Runtime dependencies are only `starlette>=0.44` and `packaging>=23`. Optional extras:

| Extra | Adds | Why |
|---|---|---|
| `sharpit[fastapi]` | `fastapi>=0.115` | the supported host |
| `sharpit[settings]` | `pydantic-settings>=2.4` | the Config panel shows which source each value came from |
