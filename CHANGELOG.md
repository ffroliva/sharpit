# Changelog

All notable changes to sharpit are documented here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)
and the project uses [Semantic Versioning](https://semver.org/).

## [Unreleased]

## [0.1.0] - Unreleased

First release: an embedded, local-only developer console for FastAPI apps, ported from
[BootUI](https://github.com/jdubois/boot-ui) (Julien Dubois, Apache-2.0).

### Added

- `sharpit.install(app, settings=..., **options)` mounts the console at `/sharpit` and a BootUI-compatible JSON API at
  `/sharpit/api`. `settings=` takes pydantic-settings instances so the Config panel can show each value's source.
- Panels: Overview, Configuration (environment, `.env`, pydantic-settings and `os.getenv` keys, masked), Mappings,
  Loggers (runtime level changes), Beans (dependency providers, middleware, lifespan), Vulnerabilities (OSV scan with
  EPSS scores, on explicit request; dismissable rules in `.sharpit/sharpit.yml`), MCP Server and CLI.
- Read-only MCP endpoint (`POST /sharpit/api/mcp`, off by default; `SHARPIT_MCP_ENABLED=ON`) with the tools
  `get_overview`, `get_config`, `get_mappings`, `get_loggers`, `get_beans` and `get_vulnerabilities_report`; the CLI
  HTTP endpoint (`/sharpit/api/cli`) offers the same catalogue plus the vulnerability scan.
- Configuration through `SHARPIT_*` environment variables and `install()` keywords; the environment wins. Invalid values
  fall back to a fail-safe value and record a warning.
- Fail-closed activation: on for `SHARPIT_ENABLED=ON`, a dev profile, `uvicorn --reload` or `fastapi dev`; a `prod`
  profile switches it off. When off, every path under the mount answers the host's own 404.
- Request guard: loopback-only by default, `Host` allow-list, full-origin and `Sec-Fetch-Site` cross-site checks on
  every method, bearer token with `HttpOnly` session cookie for untrusted sources.
- Secret masking of names, values, defaults and errors, including pydantic `SecretStr` and any URL with userinfo.
- Extras `sharpit[fastapi]` and `sharpit[settings]`; typed package (`py.typed`); prebuilt UI in the wheel, so end users
  never need Node.

### Deviations from BootUI

Listed in section 14 of the design spec. The main ones:

- FastAPI only; Django and Flask are out of scope.
- A new Svelte UI instead of BootUI's Vue UI, over the same JSON contract.
- Activation uses profile variables and a dev-server signal read from the command line (no DevTools equivalent);
  `uvicorn.run(..., reload=True)` from a script is not detected.
- The cross-site check applies to every method, compares the full origin, and any forwarded header makes a caller
  untrusted unless a trusted proxy is configured.
- `defaultValue` is masked as well, because Python defaults come from code.
- Beans are dependency providers, middleware and lifespan rather than an IoC container.
- Deferred: config overrides, health, profile diff and the `sharpit` command-line client (the HTTP endpoint ships).

### Known limitations

- State (token, MCP switch, logger levels, scan cache) is per process under `--workers` and `--reload`.
- Behind a TLS-terminating proxy, uvicorn needs `--proxy-headers` for the Origin check to pass.
- Masking is name- and shape-based: vendor-prefixed tokens under harmless names (`sk_live_...`, `ghp_...`) can show.

[Unreleased]: https://github.com/ffroliva/sharpit/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/ffroliva/sharpit/commits/master
