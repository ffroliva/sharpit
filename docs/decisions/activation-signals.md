# Activation signals

## Status

- Activation precedence and FastAPI development signals are implemented.
- Flask CLI reloader recognition is specified, not implemented (planned with the Flask console, [#260](https://github.com/ffroliva/sharpit/issues/260)).

## Decision

Activation evaluates the following signals in order.

1. An invalid `SHARPIT_ENABLED` value disables the console and produces a warning.
1. A disabled profile disables the console unless `SHARPIT_ENABLED=ON` forces it on and produces a warning.
2. `SHARPIT_ENABLED=OFF` disables the console.
3. `SHARPIT_ENABLED=ON` enables the console.
4. An enabled profile enables the console.
5. A recognized reloading development server enables the console.
6. Otherwise, the console stays disabled. All paths under its mount return HTTP 404 while it is inactive.

The FastAPI adapter recognizes `--reload` in the process arguments as `uvicorn --reload`. It recognizes `fastapi dev`
when `dev` is the first argument and the executable is `fastapi`, `fastapi.exe`, or the module entry point for
`python -m fastapi`. Programmatic `uvicorn.run(..., reload=True)` requires explicit activation or an enabled profile.

The specified Flask CLI signal requires all four conditions below.

1. `WERKZEUG_RUN_MAIN` equals the string `true`.
2. The process arguments identify `flask`, `flask.exe`, or `python -m flask`, with `run` as the first positional command.
3. The arguments omit `--no-reload`.
4. An explicit `--reload` enables reloading, or debug mode enables it through `--debug` or a truthy `FLASK_DEBUG`.
   `--no-debug` overrides debug-based reloading.

An explicit reload flag yields the `flask run --reload` signal. Reloading derived from debug mode yields
`flask run --debug`.

## Rationale

Explicit settings and profile restrictions take precedence over development server detection. The Werkzeug reloader
starts a watcher parent and reuses its arguments for the serving child. Werkzeug sets `WERKZEUG_RUN_MAIN` in the
child in `werkzeug/_reloader.py`, and `werkzeug.serving.is_running_from_reloader()` reads it. The Flask command and
reload conditions prevent an inherited value from enabling the console in an unrelated process or a non-reloading run.

## Consequences

Automatic Flask activation is limited to the serving child of a reloading Flask CLI run. A plain `flask run`, the
watcher parent, programmatic `app.run(debug=True)`, and Gunicorn need explicit activation or an enabled profile.

## Enforced by

- `src/sharpit/engine/activation.py` implements the activation order and `tests/engine/test_activation.py` verifies it.
- `src/sharpit/fastapi/signals.py` implements FastAPI signals and `tests/fastapi/test_signals.py` verifies them.
- Section 4 of `docs/superpowers/plans/2026-11-22-sharpit-0.9.0/f0-console-contract.md` specifies the Flask signal.
