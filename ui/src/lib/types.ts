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

/** HttpExchangeDto (spec 7.1); `timestamp` is an ISO-8601 string. */
export interface HttpHeader { name: string; values: string[]; masked: boolean }
export interface HttpExchange {
  id: string;
  timestamp: string;
  method: string;
  path: string;
  query: string | null;
  uri: string;
  status: number;
  statusFamily: string;
  durationMs: number;
  responseSizeBytes: number | null;
  remoteAddress: string | null;
  principal: string | null;
  traceId: string | null;
  requestHeaders: HttpHeader[];
  responseHeaders: HttpHeader[];
}

export interface ExceptionGroup {
  id: string;
  exceptionClassName: string;
  message: string | null;
  count: number;
  firstSeen: number;
  lastSeen: number;
  location: string | null;
  applicationException: boolean;
  lastRequestMethod: string | null;
  lastRequestPath: string | null;
  status: 'OPEN' | 'ACKNOWLEDGED' | 'RESOLVED';
  regressionCount: number;
}
export interface ExceptionFrame { declaringClass: string; methodName: string; fileName: string | null; lineNumber: number; applicationFrame: boolean }
export interface ExceptionDetail {
  group: ExceptionGroup;
  frames: ExceptionFrame[];
  causes: { exceptionClassName: string; message: string | null; frames: ExceptionFrame[]; commonFrames: number }[];
  occurrences: { timestamp: number; thread: string | null; requestMethod: string | null; requestPath: string | null; handler: string | null; source: string; traceId: string | null }[];
}

export interface ActivityEntry {
  id: string;
  type: 'REQUEST' | 'SQL' | 'EXCEPTION';
  timestamp: number;
  severity: 'OK' | 'WARN' | 'SLOW' | 'ERROR';
  summary: string;
  detail: string | null;
  durationMs: number | null;
  method: string | null;
  path: string | null;
  status: number | null;
  profileable: boolean;
  sqlNPlusOneSuspected: boolean;
}
export interface ActivityReport {
  available: boolean;
  entries: ActivityEntry[];
  kpis: Record<string, number | string | null>;
  sources: string[];
  warnings: string[];
}
export interface SqlGroup { sql: string; category: string; executions: number; totalDurationMillis: number; maxDurationMillis: number; potentialNPlusOne: boolean; callSites: string[] }
export interface RequestProfile {
  available: boolean;
  unavailableReason: string | null;
  request: ActivityEntry | null;
  sqlGroups: SqlGroup[];
  sqlCorrelationApproximate: boolean;
  exceptions: { exceptionClassName?: string; message?: string | null }[];
  timing: { totalMs: number; sqlMs: number; sqlCount: number; sqlPercent: number | null } | null;
  notes: string[];
}

export interface LogLine { timestamp: number; level: string; logger: string; message: string; thread: string | null }

export interface ThreadRow { id: number; name: string; state: string; daemon: boolean; stackTrace: string[] }
export interface AsyncTask { name: string; coroutine: string | null; state: string; stackTrace: string[]; request: { method: string; path: string; ageMs: number } | null }
export interface ThreadReport {
  stateCounts: { state: string; count: number }[];
  threads: ThreadRow[];
  tasks: AsyncTask[];
  taskCount: number;
  warnings: string[];
}

export interface SetupStep { title: string; description: string; snippets: string[] }
export interface HealthNode {
  name: string;
  status: string;
  details: Record<string, unknown> | null;
  components: HealthNode[];
  available: boolean;
  unavailableReason: string | null;
  guidanceReason: string | null;
  setup: SetupStep[];
}

export interface ProbeResult {
  status: number;
  statusText: string;
  headers: Record<string, string>;
  body: string | null;
  durationMs: number;
  error: string | null;
  truncated: boolean;
}

export interface SqlTraceEntry {
  id: number;
  timestamp: string;
  sql: string;
  statementType: string;
  category: string;
  durationMillis: number;
  success: boolean;
  errorMessage: string | null;
  affectedRows: number | null;
  slow: boolean;
  traceId: string | null;
  callSite: string | null;
}
export interface SqlTraceReport {
  available: boolean;
  unavailableReason: string | null;
  capturing: boolean;
  captureParameters: boolean;
  bufferSize: number;
  totalCaptured: number;
  slowQueryThresholdMillis: number;
  dataSources: string[];
  entries: SqlTraceEntry[];
  topStatements: SqlGroup[];
  warnings: string[];
}

export interface PoolSnapshot { timestamp: number; active: number; idle: number; total: number; pending: number | null }
export interface Pool {
  poolName: string;
  username: string | null;
  driverClassName: string;
  maximumPoolSize: number | null;
  connectionTimeoutMs: number | null;
  maxLifetimeMs: number | null;
  autoCommit: boolean;
  available: boolean;
  unavailableReason: string | null;
  snapshot: PoolSnapshot | null;
}
export interface PoolsReport { hikariPresent: boolean; total: number; pools: Pool[] }

export interface AlembicMigration { version: string; description: string | null; script: string | null; state: string }
export interface AlembicDatabase {
  name: string;
  currentVersion: string | null;
  applied: number;
  pending: number;
  total: number;
  migrations: AlembicMigration[];
  checkedAt: number | null;
  unavailableReason: string | null;
}
export interface AlembicReport { alembicPresent: boolean; configPath: string | null; total: number; heads: string[]; databases: AlembicDatabase[] }

/** `RuleResult` (spec 8); REST API reports list only failing rules, dismissed ones included. */
export interface AdvisorRule {
  id: string;
  name: string;
  category: string;
  severity: string;
  description: string;
  status: string;
  violationCount: number;
  sampleViolations: string[];
  recommendation: string | null;
  learnMoreUrl: string | null;
  dismissed: boolean;
}
/** What every advisor report shares; `results` is absent on Vulnerabilities, whose view lists findings itself. */
export interface AdvisorReport {
  scan: { status: string; message: string; scannedAt: number | null };
  severityCounts: { severity: string; count: number }[];
  evidence?: { usable: boolean; coverageComplete: boolean; limitations: string[] };
  results?: AdvisorRule[];
  violationDetails?: { scanId: string | null };
}
export interface ViolationsPage { violations: string[]; page: { offset: number; returned: number; hasMore: boolean } }
