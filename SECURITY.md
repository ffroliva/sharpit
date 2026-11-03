# Security Policy

sharpit takes security and procurement hygiene seriously. As an embedded developer console and automated test gate, sharpit is designed to fail closed and keep application runtime and data local.

## Supported Versions

Security updates are provided only for the latest release on PyPI:

| Version | Supported | Notes |
|---|---|---|
| Latest release on PyPI (0.4.x) | Yes | Verifiable support boundary |
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
- **Fails closed**: If network requests to OSV or EPSS fail or time out, the scan reports the failure gracefully without compromising security or crashing the host application.
