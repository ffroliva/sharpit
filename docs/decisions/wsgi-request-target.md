# WSGI request target validation

## Status

WSGI request target validation is specified, not implemented (planned with the Flask console, [#260](https://github.com/ffroliva/sharpit/issues/260)).

## Decision

The WSGI adapter checks `RAW_URI`, `REQUEST_URI`, and `HTTP_HOST` for active requests under the console mount before
passing them to the console guard. If either raw target is present and uses a form other than origin form, or if
`HTTP_HOST` is missing or blank, the adapter returns HTTP 403 with the disallowed-host error and security headers.

When the server supplies neither a nonempty `RAW_URI` nor a nonempty `REQUEST_URI`, the adapter fails closed: it
returns HTTP 403 with an availability reason that names the server limitation.

An alternative under review applies the Host allow-list to the `HTTP_HOST` supplied by the WSGI server in that case,
because a client able to send an absolute-form target can also send an allowed `Host` header directly. Adopting it
changes the guard chain and requires the project's safety review.

## Rationale

For an absolute-form request target, Werkzeug can replace `HTTP_HOST` with the authority from the request line.
`RAW_URI` and `REQUEST_URI` let the adapter inspect the original form before relying on the Host header. WSGI's
`PATH_INFO` carries the path alone, so it cannot distinguish an absolute-form target from an origin-form target.

## Consequences

The configured WSGI server determines whether the adapter can validate the original request target. Werkzeug's
development server supplies both keys. A server that supplies neither, such as the
standard library's `wsgiref`, receives HTTP 403 for every console request.

## Enforced by

- `src/sharpit/engine/guard.py` implements the Host allow-list and `tests/engine/test_guard.py` verifies it.
- Section 3 of `docs/superpowers/plans/2026-11-22-sharpit-0.9.0/f0-console-contract.md` specifies the WSGI request-target checks.
