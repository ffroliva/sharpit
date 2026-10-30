/** Contract DTOs (docs/reference/BOOTUI-CONTRACT-MVP.md), only the fields the views read. */

export interface Panel {
  id: string;
  title: string;
  available: boolean;
  unavailableReason: string | null;
  enabled: boolean;
  readOnly: boolean;
  readOnlyReason: string | null;
}

export interface Overview {
  bootUiVersion: string;
  applicationName: string | null;
  frameworkName: string;
  frameworkVersion: string | null;
  javaVersion: string | null;
  javaVendor: string | null;
  activeProfiles: string[];
  defaultProfiles: string[];
  webApplicationType: string | null;
  serverPort: number | null;
  managementPort: number | null;
  contextPath: string | null;
  startupTimeMillis: number | null;
  activation: { enabled: boolean; localhostOnly: boolean; reason: string; warnings: string[] };
  openApiUrl: string | null;
}

export interface Property {
  name: string;
  value: unknown;
  source: string;
  origin: string | null;
  masked: boolean;
  override: boolean;
  description: string | null;
  defaultValue: unknown;
}

/** A key the app declares or reads but nobody set; `description` is a field's text or the `file.py:line` reading it. */
export interface PropertySuggestion {
  name: string;
  type: string | null;
  description: string | null;
  defaultValue: unknown;
}

export interface Logger {
  name: string;
  configuredLevel: string | null;
  effectiveLevel: string | null;
}

export interface Mapping {
  method: string;
  pattern: string;
  handler: string | null;
  produces: string | null;
  consumes: string | null;
}

export interface BeanRow {
  name: string;
  type: string | null;
  scope: string | null;
  resource: string | null;
  dependencies: string[];
  aliases: string[];
  classification: string;
}

export interface Vulnerability {
  id: string;
  summary: string | null;
  severity: string;
  score: number | null;
  aliases: string[];
  references: string[];
  fixedVersions: string[];
  fixAvailable: boolean;
  dismissed: boolean;
}

export interface Dependency {
  packageName: string;
  version: string;
  vulnerabilityCount: number;
  highestSeverity: string;
  vulnerabilities: Vulnerability[];
}

export interface VulnReport {
  scanningEnabled: boolean;
  total: number;
  vulnerable: number;
  severityCounts: { severity: string; count: number }[];
  scan: {
    scanner: string;
    status: string;
    message: string;
    scannedAt: number | null;
    packagesScanned: number;
    packagesSkipped: number;
    vulnerabilitiesFound: number;
  };
  dependencies: Dependency[];
}

export interface ToolInfo {
  name: string;
  description: string;
  panel: string;
  action: boolean;
  panelEnabled: boolean;
  panelReadOnly: boolean;
  command?: string;
}

/** `McpServerStatus` and `CliServerStatus` share these fields. */
export interface ServerStatus {
  enabled: boolean;
  configuredMode?: string;
  overridden?: boolean;
  serverName: string;
  serverVersion: string;
  endpoint: string;
  protocolVersion?: string;
  maxResults: number;
  callCount: number;
  totalLatencyMillis: number;
  capacityRefusals: number;
  timeouts: number;
  responseLimitRefusals?: number;
  toolCount: number;
  tools: ToolInfo[];
}
