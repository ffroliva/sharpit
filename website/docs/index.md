# sharpit

An embedded, local-only developer console for FastAPI apps. One call mounts a web console at `/sharpit` and a
JSON API at `/sharpit/api` inside your own app, so a running service becomes understandable in minutes: its
configuration and where each value came from, every route, the dependency providers, loggers you can retune live,
and a vulnerability scan of the installed packages.

sharpit is a Python/FastAPI port of [BootUI](https://github.com/jdubois/boot-ui) by Julien Dubois (Apache-2.0), the
Spring Boot developer console. It ports BootUI's design goals, JSON contract and test cases; the UI is new.

![sharpit overview](https://raw.githubusercontent.com/ffroliva/sharpit/main/ui/tests/e2e/screenshots/overview-light.png)

> **Status: alpha (0.3.0, FastAPI only).** Django and Flask are not supported. See [CHANGELOG.md](https://github.com/ffroliva/sharpit/blob/main/CHANGELOG.md).

## Start here

1. [Install](installation.md) it from git.
2. Follow the [Quickstart](quickstart.md): one `sharpit.install(app)` call, then run with a dev signal.
3. Read the [Safety model](safety.md) before you expose it beyond localhost.

## License

Apache License 2.0. See [LICENSE](https://github.com/ffroliva/sharpit/blob/main/LICENSE) and [NOTICE](https://github.com/ffroliva/sharpit/blob/main/NOTICE). sharpit is derived from
[BootUI](https://github.com/jdubois/boot-ui), Copyright Julien Dubois.
