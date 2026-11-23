# WSGI request target validation

## Status

WSGI request target validation is specified, not implemented (planned for 0.9.0). The policy for servers that omit
the original request target is open.

## Decision

The WSGI adapter checks `RAW_URI`, `REQUEST_URI`, and `HTTP_HOST` for active requests under the console mount before
passing them to the console guard. If either raw target is present and uses a form other than origin form, or if
`HTTP_HOST` is missing or blank, the adapter returns HTTP 403 with the disallowed-host error and security headers.

Two options remain open for servers that supply neither a nonempty `RAW_URI` nor a nonempty `REQUEST_URI`.

- Fail closed with HTTP 403 and report that the server does not supply the original target.
- Apply the Host allow-list to the `HTTP_HOST` supplied by the WSGI server.

## Rationale

For an absolute-form request target, Werkzeug can replace `HTTP_HOST` with the authority from the request line.
`RAW_URI` and `REQUEST_URI` let the adapter inspect the original form before relying on the Host header. WSGI's
`PATH_INFO` carries the path alone, so it cannot distinguish an absolute-form target from an origin-form target.

## Consequences

The configured WSGI server determines whether the adapter can validate the original request target. Returning
HTTP 403 without a raw target preserves that requirement and limits server compatibility. Using the Host allow-list
supports servers that omit raw targets and relies on those servers to preserve the authority used for validation.

## Enforced by

- `src/sharpit/engine/guard.py` implements the Host allow-list and `tests/engine/test_guard.py` verifies it.
- Section 3 of `docs/superpowers/plans/2026-11-22-sharpit-0.9.0/f0-console-contract.md` specifies the WSGI request-target checks.
