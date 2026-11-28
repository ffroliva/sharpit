# Security Policy

sharpit takes security and procurement hygiene seriously. As an embedded developer console and automated test gate, sharpit is designed to fail closed and keep application runtime and data local.

## Supported Versions

Security updates are provided only for the latest release on PyPI:

| Version | Supported | Notes |
|---|---|---|
| Latest release on PyPI (0.10.x) | Yes | Verifiable support boundary |
| Prior versions | No | Unsupported |

## Reporting a Vulnerability

Please report suspected security vulnerabilities privately. **Do not post vulnerability details in public issues or discussions.**

- Once enabled on the repository, report privately via GitHub's "Report a vulnerability" button under the **Security** tab.
- Until private vulnerability reporting is enabled, please open a GitHub issue titled `"Security contact request"` containing **NO details**, and the maintainer will reply with a private channel to share details securely.

## Network Egress and Trust Boundaries

sharpit enforces strict safety invariants:

- **Local read surface**: HTTP GET routes (under `/sharpit` and `/sharpit/api`) and Model Context Protocol (MCP) read tools open no sockets.
- **Database panels and health checks**:
  - The health check (POST) pings configured database engines and runs user health callables.
  - Database panels run read-only SQL through the app's own engines.
- **Vulnerability scan network egress**: Outbound network requests occur only during an explicit vulnerability scan (POST), which sends installed package names and versions (up to 500) to OSV and CVE IDs to FIRST EPSS:
  - The OSV client in `src/sharpit/engine/collectors/vulns/osv.py` queries OSV;
  - The EPSS client in `src/sharpit/engine/collectors/vulns/epss.py` queries FIRST EPSS.
  - Destinations are configurable via `SHARPIT_VULNERABILITIES_OSV_BASE_URI` and `SHARPIT_VULNERABILITIES_EPSS_BASE_URI`.
  - Network vulnerability scans can be disabled via `SHARPIT_VULNERABILITIES_OSV_ENABLED=false` and `SHARPIT_VULNERABILITIES_EPSS_ENABLED=false`.
- Whole scans have a 60-second default deadline (`SHARPIT_VULNERABILITIES_SCAN_TIMEOUT`); each network request is capped by the remaining scan time.
- **Fails closed**: If network requests to OSV or EPSS fail or time out, the scan reports the failure gracefully without compromising security or crashing the host application.
- **Client address**: The trusted-source decision rests on the ASGI client address and the request's forwarding and client-address headers; the ASGI client address must be the real peer.

### Request input reaching commands and file paths

The opt-in security-sinks sensor (`SHARPIT_AGENT_SECURITY_SINKS_REQUEST_VALUES=true`) holds eligible query and path parameter values in memory only while their request is live, for at most 60 seconds. It compares sink text verbatim; it does not track taint or transformations. A match redacts the value from the process or file row and can produce a Side Effects row. Redaction applies only to checks made while the request is live. A “no finding” result does not mean the application is safe: work after the endpoint returns, such as a `FileResponse` opening a file in a worker thread, is not owned by the request. With two sharpit installs in one process, each install's matcher redacts only the requests of its own install. Work handed to `loop.run_in_executor` or to a raw thread carries no request context, so its rows are recorded without request-value matching. Side Effects rows hold no request value; hashes remain in memory inside the store and never leave it in output. Secret-looking parameter names and path segments are masked at every exposure. When a request has no route template, its attribution uses the path already reduced by capture (for example, `/static/{value}`), then masks it per segment. SQL statements and outbound URLs are not checked in this release.
