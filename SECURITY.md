# Security Policy

sharpit takes security and procurement hygiene seriously. As an embedded developer console and automated test gate, sharpit is designed to fail closed and keep application runtime and data local.

## Supported Versions

Only the current active release line receives security updates:

| Version | Supported | Notes |
|---|---|---|
| 0.3.x (0.3.0) | Yes | Current active release |
| < 0.3.0 | No | Unsupported |

## Reporting a Vulnerability

Please report suspected security vulnerabilities privately. **Never report security vulnerabilities through public discussions or bug trackers.**

To report a vulnerability:
1. Use GitHub's private vulnerability reporting feature via [Security Advisories](https://github.com/ffroliva/sharpit/security/advisories/new).
2. Provide a clear description, reproduction steps, affected versions, and potential impact.
3. The maintainer will acknowledge receipt within 48 hours and provide updates through the private advisory channel.

## Network Egress and Trust Boundaries

sharpit enforces strict safety invariants:

- **Local read surface**: Ordinary HTTP GET routes (under `/sharpit` and `/sharpit/api`) and Model Context Protocol (MCP) read tools run strictly in-process and locally. They never open network sockets or make external HTTP requests.
- **Vulnerability gatekeepers only**: The only outbound network requests in sharpit originate from dedicated vulnerability clients:
  - The OSV client in `src/sharpit/engine/collectors/vulns/osv.py` (querying `api.osv.dev`);
  - The EPSS client in `src/sharpit/engine/collectors/vulns/epss.py` (querying `api.first.org`).
  All other collectors, advisors, and engine components operate entirely offline without network access.
- **Fails closed**: If network requests to OSV or EPSS fail or time out, the scan reports the failure gracefully without compromising security or crashing the host application.
