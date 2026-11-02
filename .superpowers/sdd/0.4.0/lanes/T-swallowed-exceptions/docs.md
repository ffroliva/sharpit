# User-facing text for G4/docs (T-swallowed-exceptions; O3: this lane does not edit README or skills)

## sharpit.swallowed-exception (pytest `--sharpit`)

During a test, sharpit watches for exceptions that a broad handler in your own code swallows: an `except:`,
`except Exception:` or `except BaseException:` clause whose body neither re-raises nor calls a logger or `warnings`.
The exception may come from anywhere (your code or a library); only the handler has to be yours (not the standard
library, not site-packages, not sharpit).

- A swallowed `AttributeError`, `TypeError`, `NameError`, `ImportError` (and `ModuleNotFoundError`) or
  `UnboundLocalError` fails the test: these are programming errors that the handler turns into a wrong value.
- Any other swallowed exception is recorded as an `INFO` finding (a note) and never fails the test.
- Relax per test with `@pytest.mark.sharpit(allow_swallowed=True)`: every swallow becomes a note.
- `--sharpit-report-only` and baselines apply as for the other gates.
- The finding names the handler (`path:line`, relative to the working directory) and the exception type, never the
  message or a local value.
- It uses `sys.monitoring` tool id 3 or 4 (whichever is free) for the session only. If both are taken, the source
  `swallowed-exceptions` reports `attached: false` and the run is `unknown`.

Static check (rule text new, marked N): `FASTAPI-ERR-001` "Do not swallow exceptions in route handler modules" flags
the same pattern in the files that define the app's route handlers, read and parsed, never imported or called.
