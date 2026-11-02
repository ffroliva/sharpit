# Security Policy

sharpit takes security and procurement hygiene seriously. As an embedded developer console and automated test gate, sharpit is designed to fail closed and keep application runtime and data local.

## Supported Versions

Security updates are provided only for the latest release on PyPI:

| Version | Supported | Notes |
|---|---|---|
| Latest release on PyPI (0.3.x) | Yes | Verifiable support boundary |
| Prior versions | No | Unsupported |

## Reporting a Vulnerability

Please report suspected security vulnerabilities privately. **Do not post vulnerability details in public issues or discussions.**

- Once enabled on the repository, report privately via GitHub's "Report a vulnerability" button under the **Security** tab.
- Until private vulnerability reporting is enabled, please open a GitHub issue titled `"Security contact request"` containing **NO details**, and the maintainer will reply with a private channel to share details securely.

## Network Egress and Trust Boundaries

sharpit enforces strict safety invariants:

- **Local read surface**: Ordinary HTTP GET routes (under `/sharpit` and `/sharpit/api`) and Model Context Protocol (MCP) read tools run strictly in-process and locally. They never open network sockets or make external HTTP requests.
- **Vulnerability gatekeepers only**: The only outbound network requests in sharpit originate from dedicated vulnerability clients:
  - The OSV client in `src/sharpit/engine/collectors/vulns/osv.py` (querying `api.osv.dev`);
  - The EPSS client in `src/sharpit/engine/collectors/vulns/epss.py` (querying `api.first.org`).
  All other collectors, advisors, and engine components operate entirely offline without network access.
- **Fails closed**: If network requests to OSV or EPSS fail or time out, the scan reports the failure gracefully without compromising security or crashing the host application.
