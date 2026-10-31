# BootUI JSON contract — MVP extract for sharpit

Source: `C:\development\github\boot-ui` (branch `ffroliva/1067-claude-code-plugin`, read 2026-10-30). Paths below are relative to that root.
Abbreviations: `DTO/` = `bootui-core/src/main/java/io/github/jdubois/bootui/core/dto/`, `ENG/` = `bootui-engine/src/main/java/io/github/jdubois/bootui/engine/`, `AC/` = `bootui-spring-autoconfigure/src/main/java/io/github/jdubois/bootui/autoconfigure/`, `UI/` = `bootui-ui/src/main/frontend/src/`, `CONF/` = `bootui-conformance/src/main/java/io/github/jdubois/bootui/conformance/`.

Legend: **[JVM]** = Spring/JVM-specific, drop or replace in Python. **[AMBIG]** = not settled by the source; decide deliberately.

---

## 1. Envelope and conventions

### Base paths
- UI shell: `bootui.path`, default `/bootui`. API: `bootui.api-path`, default `<bootui.path>/api` = `/bootui/api`. Both are relative to the app context path. Every controller is `@RequestMapping("${bootui.api-path:${bootui.path:/bootui}/api}/<x>")`.
- The UI calls relative URLs (`api/overview`, `api/panels`, …) from the shell page, so the API must sit at `<ui>/api`. Source: `UI/api.js`.
- sharpit: keep `/bootui/api` (or `/sharpit/api`) with the same suffixes, so the shapes stay unchanged.

### Content type and body conventions
- JSON (`application/json`). Responses are Java records serialized by Jackson, so field names are the record component names in camelCase and null fields are emitted as `null`, not omitted. [AMBIG] Jackson inclusion could be configured globally; nothing I read sets NON_NULL for BootUI DTOs, so emit nulls.
- There is no envelope wrapper: each endpoint returns its DTO at the root.
- There is no API versioning: no version prefix or header. The only versioned thing is MCP (`MCP-Protocol-Version`, see §9).
- Epoch timestamps are in milliseconds (`Long`), e.g. `scan.scannedAt`, `startupTimeMillis`.

### Paging (shared by config, loggers, beans, mappings)
- Query params are `q`, `offset` and `limit`. `PagedList` (`ENG/support/PagedList.java`):
  - `q` is trimmed and lowercased, then matched as a case-insensitive substring. Blank means no filter.
  - `offset`: null or negative becomes 0.
  - `limit`: null means all matched items; otherwise it is clamped to 1..1000 (`MAX_LIMIT=1000`).
- `page` = `PageMetadata(int total, int matched, int offset, int limit, int returned, boolean hasMore)` (`DTO/PageMetadata.java`):
  - `total` is the unfiltered count and `matched` is the count after filtering.
  - `offset` is the effective start index and `limit` is the effective limit (= matched when unbounded).
  - `hasMore` = `offset+returned < matched`.
- The UI requests pages of 200 (`UI/utils/useServerPagedList.js`, `SERVER_PAGE_SIZE=200`) and reads `page.matched` and `page.total`.

```json
"page": {"total": 412, "matched": 37, "offset": 0, "limit": 200, "returned": 37, "hasMore": false}
```

### Error bodies (every shape found)

| Situation | Status | Body |
|---|---|---|
| Guard: non-loopback, bad Host, cross-site write | 403 | `{"error":"<message>"}` (`ENG/safety/LocalhostGuard`, `AC/web/LocalhostOnlyFilter`) |
| Missing or invalid token | 401 | `{"error":"BootUI authentication required"}` plus `WWW-Authenticate: Bearer realm="BootUI"` and `Cache-Control: no-store` |
| Panel disabled or read-only | 403 | `{"error":"BootUI panel access denied","panel":"<id>","reason":"<reason>"}` |
| Generic filter block | 403 | `{"error":"BootUI access denied","reason":"..."}` (`AC/web/AbstractBootUiFilter`) |
| Single-flight action busy | 409 | `ActionBusyResult {"error":"BootUI action already in progress","operation":"<op>","activeOperation":"<op>","message":"Operation '<op>' cannot start while '<active>' is in progress."}` (`AC/web/ActionBusyExceptionHandler`, `ENG/action/SingleFlightAction`) |
| Controller-local validation (loggers etc.) | 400 | `{"error":"<message>"}` |
| BootUI inactive | 404 | anything under the BootUI mounts (`AC/.../BootUiShellGuardFilter`) |

- Reason strings: `"Panel is disabled via bootui.panels.<id>.enabled=false"`, `"BootUI is read-only via bootui.read-only=true"`, `"Panel is read-only via bootui.panels.<id>.read-only=true"` (`AC/BootUiProperties.java:382-389`).
- The UI's `ApiError(status, body)` treats a 409 whose `body.error === "BootUI action already in progress"` as busy and shows `body.message` (`UI/api.js`).
- [AMBIG] `IllegalArgumentException` raised in controllers that have no local `@ExceptionHandler` (e.g. `ConfigController` "'name' must be provided") falls through to the host app's default error handling, which is a Spring 500 / whitelabel response. sharpit should return `400 {"error": msg}` everywhere for consistency.

### Security headers (every BootUI response) — `ENG/safety/BootUiSecurityHeaders`
- `Content-Security-Policy: default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; font-src 'self' data:; connect-src 'self'; object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'`
- `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: strict-origin-when-cross-origin`
- `Permissions-Policy: accelerometer=(), camera=(), geolocation=(), gyroscope=(), magnetometer=(), microphone=(), payment=(), usb=()`
- Caching:
  - API responses: `Cache-Control: no-store, must-revalidate` and `Pragma: no-cache`.
  - Hashed static assets: `public, max-age=31536000, immutable`.
  - Everything else (shell HTML): `no-cache`.

### Panel registry — `GET /bootui/api/panels`
Sources: `AC/web/PanelsController.java`, `ENG/panel/BootUiPanels.java`, `DTO/PanelsReport.java`, `DTO/PanelDto.java`.

```
PanelsReport { platform: "spring-boot" | "spring-boot-reactive" | "quarkus", panels: PanelDto[] }
PanelDto { id: str, title: str, available: bool, unavailableReason: str|null,
           enabled: bool, readOnly: bool, readOnlyReason: str|null }
```

- `available`: whether the backing capability exists. [JVM] Spring decides by bean or class presence. `unavailableReason` is null when `available` is true. An unknown id gives `available=false` with reason `"Unknown BootUI panel"`.
- `enabled` = `bootui.panels.<id>.enabled` (default true).
- `readOnly` = `panel.actionCapable && isPanelReadOnly(id)`, where read-only is global `bootui.read-only` or `bootui.panels.<id>.read-only`. `readOnlyReason` is null when `readOnly` is false.
- MVP panel table (registry `Panel(id, title, actionCapable, apiPrefixes)`):

| id | title | actionCapable | API prefix | availability (Spring) |
|---|---|---|---|---|
| overview | Overview | – | none (never gated) | always |
| health | Health | false | /health | actuator health endpoint bean |
| config | Configuration | true | /config | always |
| profile-diff | Profile Diff | false | /profile-diff | active profiles or an `application-<p>.(properties\|yml\|yaml)` source |
| loggers | Loggers | true | /loggers | actuator loggers bean |
| beans | Beans | false | /beans | actuator beans bean |
| mappings | Mappings | false | /mappings | actuator mappings bean |
| vulnerabilities | Vulnerabilities | true | /vulnerabilities | always |
| mcp-server | MCP Server | true | /mcp-server | always |
| cli | CLI | – | none (never gated) | always |

- Prefix matching is `path == prefix || path.startsWith(prefix + "/")` (`BootUiPanels.matchesApiPath`). Consequently `/mcp` is **not** under the `/mcp-server` prefix and is not panel-gated; it has its own enable switch (§9).
- Full upstream id list, for forward compatibility only:
  - overview, health, http-sessions, metrics, live-memory, jvm-tuning, heap-dump, threads, memory, startup
  - graalvm, scheduled, config, profile-diff, loggers, beans, conditions, mappings, data
  - flyway, liquibase, database-connection-pools, hibernate, hibernate-statistics, database-advisor, postgresql, mysql
  - cache, spring-security, security, security-logs, ai, traces, log-tail, exceptions
  - http-exchanges, http-probe, architecture, rest-api, pentesting, vulnerabilities, devtools, dev-services
  - copilot, claude-code, github, spring, crac, sql-trace, transactions, rest-client-trace
  - mcp-server, cli, activity, email, kafka, rabbitmq, jms, fault-tolerance, websockets
- UI discovery (`UI/App.vue`): on startup it does `GET api/overview` and `GET api/panels`, then builds the navigation from `panels[]`. Panels that are `available=false` or `enabled=false` are hidden or shown as unavailable. When `readOnly` is true, the action buttons are disabled and `readOnlyReason` is shown.
- Overview scanner rule (`UI/views/Overview.vue`): `refreshScanner` issues only GETs, and only for panels present in the manifest. POST `api/<x>/scan` happens only in `runScanner`, which is user-triggered.

```json
{"platform":"spring-boot","panels":[
 {"id":"loggers","title":"Loggers","available":true,"unavailableReason":null,"enabled":true,"readOnly":false,"readOnlyReason":null},
 {"id":"health","title":"Health","available":false,"unavailableReason":"<reason>","enabled":true,"readOnly":false,"readOnlyReason":null}]}
```

---

## 2. Overview — `GET /bootui/api/overview`
Sources: `AC/web/OverviewController.java`, `DTO/OverviewDto.java`, `DTO/ActivationStatus.java`. Conformance requires `applicationName` (str), `frameworkName` (str), `frameworkVersion` (str|null), `javaVersion` (str), `activeProfiles` (array) and `activation` (object) (`CONF/BootUiApiContractCatalog.java:24`).

```
OverviewDto {
  bootUiVersion: str, applicationName: str, frameworkName: str, frameworkVersion: str|null,
  javaVersion: str, javaVendor: str,
  activeProfiles: str[], defaultProfiles: str[],
  webApplicationType: "SERVLET" | "REACTIVE",
  serverPort: int|null, managementPort: int|null, contextPath: str|null,
  startupTimeMillis: long|null,
  activation: ActivationStatus { enabled: bool, localhostOnly: bool, reason: str, warnings: str[] },
  openApiUrl: str|null
}
```

- `applicationName` comes from `spring.application.name`, default `"application"`.
- `serverPort` comes from `local.server.port`, then `server.port`, default 8080.
- `contextPath` comes from `server.servlet.context-path`.
- `startupTimeMillis` comes from `spring.boot.application.startup.time`.
- `activation.localhostOnly` = `!bootui.allow-non-localhost`. sharpit: false whenever any remote access is configured
  (`allow_non_localhost`, `trusted_proxies` or container gateway trust), see spec §14.
- `openApiUrl` is the springdoc path (default `/swagger-ui/index.html`) when springdoc is present, otherwise null.
- Python mapping:
  - [JVM] `javaVersion` and `javaVendor` become the Python version and implementation, and `frameworkName` becomes "Django", "FastAPI" or "Flask".
  - [JVM] `webApplicationType` maps to WSGI or ASGI. The values are not consumed by logic; I saw the UI only display them.
  - Conformance requires `javaVersion` to be a string, so keep the key name if you reuse the conformance suite.

```json
{"bootUiVersion":"1.17.0","applicationName":"petclinic","frameworkName":"Spring Boot","frameworkVersion":"3.5.0",
 "javaVersion":"21.0.4","javaVendor":"Eclipse Adoptium","activeProfiles":["dev"],"defaultProfiles":["default"],
 "webApplicationType":"SERVLET","serverPort":8080,"managementPort":null,"contextPath":null,"startupTimeMillis":2310,
 "activation":{"enabled":true,"localhostOnly":true,"reason":"Enabled by active profile 'dev'","warnings":[]},
 "openApiUrl":null}
```

The overview is the first GET the UI makes. The UI also uses it to prime the `XSRF-TOKEN` cookie (§10).

---

## 3. Config

### `GET /bootui/api/config?q=&source=&overridesOnly=false&offset=&limit=`
Sources: `AC/web/ConfigController.java`, `ENG/config/ConfigService.java`, `DTO/ConfigReport.java`, `DTO/ConfigPropertyDto.java`, `DTO/ConfigPropertySuggestionDto.java`.

```
ConfigReport {
  activeProfiles: str[], sources: str[] /* property-source names, precedence order */,
  properties: ConfigPropertyDto[], propertySuggestions: ConfigPropertySuggestionDto[],
  page: PageMetadata, overrideCount: int
}
ConfigPropertyDto { name: str, value: any|null, source: str, origin: str|null /* always null */,
                    masked: bool, override: bool, description: str|null, defaultValue: any|null }
ConfigPropertySuggestionDto { name: str, type: str|null, description: str|null, defaultValue: any|null }
```

Provenance:
- Sources are walked in precedence order. The **first** source that defines a key wins, and `source` = that source's name (e.g. `"Config resource 'class path resource [application.yml]'"`, `"systemEnvironment"`, `"bootui-overrides"`).
- The override source is inserted first, so it always wins.
- `override` = true when the winning source is the BootUI override file.
- Properties are sorted by name.

Filters:
- `source` is an exact source-name match.
- `overridesOnly` keeps only overrides.
- `q` matches the relaxed-canonical name (`RelaxedNames.canonicalize`: `MY_PROP`, `my-prop` and `myProp` all match) or the text of the value, description or defaultValue.
- `overrideCount` is computed over **all** properties, before filtering.

- `description` and `defaultValue` come from configuration metadata. [JVM] Spring `spring-configuration-metadata.json` has no direct Python equivalent; pydantic `Field(description=...)` defaults are the nearest. `propertySuggestions` lists known-but-unset keys from that metadata.

Masking (`bootui-core .../KeywordPatternMasker`, `.../SecretValueDetector`, `ENG/config/ConfigService`, `AC/config/BootUiExposure`):
- The exposure mode is `bootui.expose-values`, an enum `ValueExposure`:
  - `MASKED` (default): masked values become `"******"` with `masked=true`.
  - `METADATA_ONLY`: every `value` is null.
  - `FULL`: no masking.
- Masking applies only when `bootui.mask-secrets=true` (default).
- A value is masked if its **name** matches or its **value** looks secret.
- Name patterns (case-insensitive substring):
  - password, passwd, passphrase, pwd, secret, token, key, credential, credentials, private
  - apikey, api-key, client-secret, client_secret, auth, authorization, session-id, session_id
  - Note that `key` and `auth` are broad: `cache.key-prefix` and `author` get masked. That is deliberate fail-safe behaviour.
- Value detectors (masked even when the name is harmless):
  - JWT: `^eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]+$`
  - PEM private key: `BEGIN[A-Z0-9 ]*PRIVATE KEY`
  - AWS key id: `\b(?:AKIA|ASIA)[A-Z0-9]{16}\b`
  - URL with userinfo: `://[^/?#\s:@]+:[^/?#\s@]+@`
  - URL query credential params: access/refresh/id/auth/session token, client secret, secret key, api key, access key, password, passwd, passphrase, pwd, secret, token, credential
- Sensitive header names, used elsewhere: authorization, proxy-authorization, cookie, set-cookie, x-xsrf-token, x-csrf-token (`ENG/support/SensitiveNames`).
- URL redaction helpers: `ENG/support/UriMasking`, `ENG/support/CredentialRedaction`.

```json
{"activeProfiles":["dev"],"sources":["bootui-overrides","systemEnvironment","Config resource 'class path resource [application.yml]'"],
 "properties":[
  {"name":"spring.datasource.password","value":"******","source":"Config resource 'class path resource [application.yml]'","origin":null,"masked":true,"override":false,"description":"Login password of the database.","defaultValue":null},
  {"name":"server.port","value":"8081","source":"bootui-overrides","origin":null,"masked":false,"override":true,"description":"Server HTTP port.","defaultValue":8080}],
 "propertySuggestions":[{"name":"server.address","type":"java.net.InetAddress","description":"Network address...","defaultValue":null}],
 "page":{"total":412,"matched":2,"offset":0,"limit":200,"returned":2,"hasMore":false},"overrideCount":1}
```

### Overrides (actions; panel `config` is action-capable)
Source: `AC/config/ConfigOverrideService.java`.
- `POST /bootui/api/config/overrides`
  - Body: `ConfigOverrideRequest {name: str, value: str, persist?: bool}`. The UI sends `{name, value}`.
  - Returns `ConfigOverrideResult {name, value /* masked like reads */, previousValue /* masked */, persisted: bool /* always true */, message: str}`.
  - Message: `"Override stored at <file>. Already-bound @ConfigurationProperties beans may keep their previous value until restart."`
- `DELETE /bootui/api/config/overrides/{name}` removes the override and returns a `ConfigOverrideResult` (confirmed in `ConfigController.java:55`).
- Errors:
  - A missing `name` raises `IllegalArgumentException("'name' must be provided")`.
  - A blank name raises "Property name must not be blank".
  - Both have no local handler (status [AMBIG], see §1).
- Storage: `bootui.overrides-file`, default `.bootui/application-bootui.properties`, a properties file relative to the working dir.
- Blocked by read-only via PanelAccessFilter (403).
- [JVM] Conformance marks override actions as Spring-only, because Quarkus config is read-only. A Python port can choose read-only config for the MVP, since live config mutation rarely maps cleanly to Python settings objects.

### Profile diff (brief) — `GET /bootui/api/profile-diff`
Sources: `AC/web/ProfileDiffController.java`, `ConfigService.profiles()`.

```
ProfilesReport { activeProfiles: str[], profileSources: ProfileSourceDto[] }
ProfileSourceDto { sourceName: str, profile: str, properties: ConfigPropertyDto[] /* masked, override=false */ }
```

- There is one entry per `application-<profile>` source, and empty sources are dropped.
- The diff itself is computed client-side.
- Python mapping: per-environment settings files (`.env.dev`, `settings/dev.py`) are the nearest equivalent. [JVM] for the naming convention.

---

## 4. Mappings — `GET /bootui/api/mappings/flat?q=&offset=&limit=`
Sources: `AC/web/MappingsController.java`, `ENG/mappings/MappingsService.java`, `AC/.../SpringMappingProvider`, `DTO/MappingsReport.java`, `DTO/MappingDto.java`.

```
MappingsReport { total: int, mappings: MappingDto[], page: PageMetadata }
MappingDto { method: str, pattern: str, handler: str, produces: str|null, consumes: str|null }
```

- There is one row per (pattern × method).
- An empty method set becomes `"ANY"`. An empty pattern falls back to the predicate string or `"(any)"`.
- `produces` and `consumes` are a comma-joined sorted list; a negated media type is prefixed `!`.
- Rows are sorted by pattern, then method, then handler.
- `q` matches method, pattern, handler, produces or consumes.
- `total` is the unfiltered row count.
- `handler` is a free-form string (Spring: `com.x.OwnerController#show(Integer)`). In Python use `module.func` / `Class.method`.
- [JVM] `GET /bootui/api/mappings` (no `/flat`) returns the raw Spring Actuator descriptor, or 204 when there is none (`AC/web/ActuatorMappingsController`). Drop it.

```json
{"total":58,"mappings":[{"method":"GET","pattern":"/owners/{ownerId}","handler":"org.sp.petclinic.owner.OwnerController#showOwner(int)","produces":null,"consumes":null}],
 "page":{"total":58,"matched":1,"offset":0,"limit":200,"returned":1,"hasMore":false}}
```

---

## 5. Loggers
Sources: `AC/web/LoggersController.java`, `ENG/loggers/LoggersService.java`, `DTO/LoggersReport.java`, `DTO/LoggerDto.java`, `UI/views/Loggers.vue`.

### `GET /bootui/api/loggers?q=&offset=&limit=`

```
LoggersReport { availableLevels: str[], loggers: LoggerDto[], page: PageMetadata }
LoggerDto { name: str, configuredLevel: str|null, effectiveLevel: str|null }
```

- `availableLevels` comes from the logging backend. Spring `LogLevel` is `TRACE, DEBUG, INFO, WARN, ERROR, FATAL, OFF`. Python has `NOTSET, DEBUG, INFO, WARNING, ERROR, CRITICAL`; send those names, since the UI renders whatever is listed.
- Loggers are sorted by name. The root logger is `"ROOT"` in Spring.
- Loggers that are not read-visible (BootUI-internal) are filtered out.

### `POST /bootui/api/loggers/{name}` — body `{"level": "DEBUG"}`
- The UI URL-encodes the name: `encodeURIComponent(name)`.
- A null or blank `level` **resets** the logger (configured level becomes null, so it inherits).
- Returns the updated `LoggerDto`.
- Validation errors are 400 `{"error": msg}` via the local `@ExceptionHandler(IllegalArgumentException)`:
  - An invalid level fails in `LogLevel.valueOf`, giving the Java enum message. sharpit should say something like `"Unknown level 'X'"`.
  - Changing BootUI's own logger gives: `"Refusing to change the level of BootUI's own logger '<name>'."`
- No backend: `IllegalStateException("No logger backend is available")`, which is unhandled (likely 500). [AMBIG] Prefer 503 or 400 in sharpit.
- Blocked by read-only via PanelAccessFilter (403). Panel `loggers` is action-capable.

```json
{"availableLevels":["OFF","ERROR","WARN","INFO","DEBUG","TRACE"],
 "loggers":[{"name":"ROOT","configuredLevel":"INFO","effectiveLevel":"INFO"},{"name":"org.hibernate.SQL","configuredLevel":null,"effectiveLevel":"INFO"}],
 "page":{"total":610,"matched":2,"offset":0,"limit":200,"returned":2,"hasMore":true}}
```

---

## 6. Beans (and dependency-graph mode)
Sources: `AC/web/BeansController.java`, `ENG/beans/BeansService.java`, `DTO/BeanList.java`, `DTO/BeanSummary.java`, `UI/views/Beans.vue`, `UI/views/BeansGraphMode.vue`, `UI/utils/useBeanGraph.js`.

### `GET /bootui/api/beans?q=&classification=&offset=&limit=`

```
BeanList { total: int /* full bean count */, beans: BeanSummary[], page: PageMetadata }
BeanSummary { name: str, type: str|null, scope: str|null, resource: str|null,
              dependencies: str[] /* bean names */, aliases: str[],
              classification: "BOOTUI"|"FRAMEWORK"|"PLATFORM"|"APPLICATION"|"OTHER" }
```

- Classification rules:
  - `BOOTUI`: the bean belongs to BootUI itself.
  - `FRAMEWORK`: `org.springframework.*`.
  - `PLATFORM`: `java.*` or `jakarta.*`.
  - `OTHER`: type is null.
  - `APPLICATION`: everything else.
- Filters: `q` matches name or type. `classification` is an exact uppercase match.
- Beans are sorted by name.
- [JVM] The whole concept is the Spring IoC container. In Python, "beans" map to DI-container providers (FastAPI `Depends` graph, `dependency-injector`, Django apps/middleware/installed services). Keep the shape; set `scope` to `"singleton"`, `"request"` or similar, and `resource` to the file or module that defined it.
- Graph mode is **client-side only**. There is no graph endpoint.
  - It pages through `GET api/beans?offset=N&limit=…` in pages of `GRAPH_LOAD_PAGE_SIZE=1000`, up to `MAX_GRAPH_LOAD=2000` beans.
  - It builds a forward index from `dependencies` and a reverse index from that.
  - It does a BFS from a focus bean, defaulting to the most-connected `APPLICATION` bean. Limits are `MAX_GRAPH_NODES=60` and `MAX_GRAPH_DEPTH=3`.
  - Node roles: `focus`, `dep`, `rdep`, `both`, `deep`.
  - The UI shows "Loaded the first N of total beans".
  - Graph mode is the default view. The UI probes `api/beans?classification=BOOTUI&offset=0&limit=1`, and also calls `api/conditions` (Spring autoconfig report, [JVM]; drop it or return 404).
- Requirement for sharpit: `dependencies` must contain **names that exist as `name` of other beans**, or edges dangle.

```json
{"total":312,"beans":[{"name":"ownerController","type":"org.sp.petclinic.owner.OwnerController","scope":"singleton","resource":"file [.../OwnerController.class]","dependencies":["ownerRepository"],"aliases":[],"classification":"APPLICATION"}],
 "page":{"total":312,"matched":1,"offset":0,"limit":1,"returned":1,"hasMore":true}}
```

---

## 7. Health (brief) — `GET /bootui/api/health`
Sources: `AC/web/HealthController.java`, `ENG/health/HealthService.java`, `DTO/HealthNodeDto.java`, `DTO/HealthSetupStepDto.java`. Conformance requires `status` (str), `components` (array), `available` (bool), `unavailableReason` (str|null) and `setup` (array).

```
HealthNodeDto { name: str, status: str /* UP|DOWN|OUT_OF_SERVICE|UNKNOWN|DISABLED */, details: object|null,
                components: HealthNodeDto[] /* recursive */, available: bool, unavailableReason: str|null,
                guidanceReason: str|null, setup: HealthSetupStepDto[] }
HealthSetupStepDto { title: str, description: str, snippets: str[] }
```

- With no health provider: `{name:"application", status:"DISABLED", available:false, unavailableReason:"...", setup:[...]}`.
- When only default contributors exist and all are UP or UNKNOWN, the response adds `guidanceReason` and `setup` steps that nudge the user to add real checks.
- `details` must already be masked: apply the config masker to keys and values.

```json
{"name":"application","status":"UP","details":null,"available":true,"unavailableReason":null,"guidanceReason":null,"setup":[],
 "components":[{"name":"db","status":"UP","details":{"database":"PostgreSQL"},"components":[],"available":true,"unavailableReason":null,"guidanceReason":null,"setup":[]}]}
```

---

## 8. Vulnerabilities
Sources:
- Controller: `AC/web/VulnerabilitiesController.java`, `AC/web/OsvVulnerabilityScanner.java`
- Engine: `ENG/vulnerabilities/OsvAdvisoryInterpreter.java`, `ENG/vulnerabilities/DependencyReports.java`, `ENG/vulnerabilities/CvssV3BaseScore.java`, `ENG/advisor/DismissedRulesStore.java`
- DTOs: `DTO/Dependencies*.java`, `DTO/Dependency*.java`
- UI: `UI/views/Vulnerabilities.vue`

### Explicit-user-action rule (hard requirement)
- `GET /bootui/api/vulnerabilities` **never touches the network**:
  - When a scan has been cached in memory (`lastScanReport`), it returns that report.
  - Otherwise it returns an inventory-only report with `scan.status="NOT_SCANNED"` and message `"Dependency inventory loaded. Click Scan with OSV.dev to check for known vulnerabilities."`.
  - Dismissals are applied in both cases.
- `POST /bootui/api/vulnerabilities/scan` is the only path to OSV and EPSS. The UI calls it only from the Scan button. MCP `vulnerabilities_scan` is an action tool (read-only-gated).
- The scan is single-flight (`ActionOperations.VULNERABILITIES_SCAN`); a concurrent scan returns 409 `ActionBusyResult`.
- If `bootui.vulnerabilities.osv-enabled=false`, it returns a report with `scan.status="DISABLED"` and message `"OSV scanning is disabled. Set bootui.vulnerabilities.osv-enabled=true to allow on-demand scans."`. This report is **not cached**.
- Cache: the last successful scan report lives in memory for the process lifetime. There is no TTL and no disk persistence; a new POST replaces it.

### Response shape (GET and POST return the same DTO)

```
DependenciesReport {
  scanningEnabled: bool, total: int, vulnerable: int /* deps with >=1 active vuln */,
  severityCounts: [{severity: str, count: int}] /* always 6, order CRITICAL,HIGH,MEDIUM,LOW,UNKNOWN,NONE; dismissed excluded */,
  scan: DependencyScanStatusDto, coverage: DependencyCoverageDto, dependencies: DependencyDto[], evidence: AdvisorEvidenceDto
}
DependencyScanStatusDto { scanner: "OSV.dev", status: "NOT_SCANNED"|"SCANNED"|"PARTIAL"|"ERROR"|"DISABLED",
  message: str, scannedAt: long|null /* epoch ms */, packagesScanned: int, packagesSkipped: int, vulnerabilitiesFound: int }
DependencyCoverageDto { status: "UNAVAILABLE"|"COMPLETE"|"INCOMPLETE", archivesFound: int, archivesIdentified: int,
  archivesUnidentified: int, unidentifiedArchives: str[], unidentifiedArchivesTruncated: bool }
DependencyDto { groupId: str, artifactId: str, version: str, packageName: str /* "groupId:artifactId" */, source: str,
  vulnerabilityCount: int /* active only */, highestSeverity: str /* active only; "NONE" if none */,
  vulnerabilities: DependencyVulnerabilityDto[], assessment: {queryComplete: bool, detailAssessmentComplete: bool} }
DependencyVulnerabilityDto { id: str, summary: str|null, details: str|null, severity: str, score: float|null,
  aliases: str[] /* <=20 */, references: str[] /* <=20, ADVISORY then FIX types first */,
  fixedVersions: str[] /* <=10 */, fixAvailable: bool, epssScore: float|null /* 0..1 */, epssPercentile: float|null /* 0..1 */,
  dismissed: bool }
AdvisorEvidenceDto { usable: bool, coverageComplete: bool, limitations: str[] }
```

- Conformance requires `scanningEnabled`, `total`, `vulnerable`, `severityCounts`, `scan` and `dependencies`.
- `AdvisorEvidenceDto` is defined in `DTO/AdvisorEvidenceDto.java`. `unknown()` is used when status is not SCANNED or PARTIAL.
- [AMBIG] `DependenciesReport.status()` is a derived accessor, not a record component, so Jackson probably does **not** emit a top-level `status`. Use `scan.status`.
- `assessment.detailAssessmentComplete` implies `queryComplete`. The default is `(false,false)`.
- Python mapping:
  - [JVM] `groupId`/`artifactId`/`packageName "g:a"` and `ecosystem: "Maven"` become PyPI. Set `groupId` = `""` or `"pypi"`, `artifactId` = the normalized dist name, and `packageName` = the dist name. Keep the field names so the UI does not change.
  - `coverage.archives*` (jar identification) becomes "installed distributions with/without metadata". [JVM]
  - `source` holds the inventory origin, e.g. `"classpath"`; in Python use `"importlib.metadata"` or a lockfile name.

### OSV querying
- Inventory: de-duplicate by `packageName:version` and cap at `bootui.vulnerabilities.max-packages` (500). The overflow count goes to `scan.packagesSkipped`. An empty inventory gives `SCANNED` with `"No Maven dependencies were discovered to scan."`.
- Batch request: `POST {osv-base-uri}/v1/querybatch` with this body (use `"PyPI"` as the ecosystem for Python):
  ```json
  {"queries":[{"package":{"ecosystem":"Maven","name":"g:a"},"version":"1.2.3"}]}
  ```
  - Requests are chunked at 1000 queries.
  - A per-query `next_page_token` is resent as `page_token` inside that query, for at most 20 pages; beyond that the scan is marked truncated.
  - The response must have `results[]` with the same length as the request, object results, and non-blank ids. The body size is bounded, and any validation failure counts that package as failed.
- Detail fetch: `GET {osv-base-uri}/v1/vulns/{urlencoded id}`
  - Ids are sorted and unique, capped at `bootui.vulnerabilities.max-advisories` (200), with 10 concurrent fetches.
  - The per-request timeout is `bootui.vulnerabilities.request-timeout` (10s).
  - Advisories with a valid ISO `withdrawn` timestamp are dropped.
  - If the returned `id` does not match the requested id, the fetch counts as failed.
- Interpretation:
  - Only `affected[]` entries whose `package.ecosystem` matches and whose `package.name` equals the package (or `"*"`) count.
  - `ECOSYSTEM` ranges are evaluated with `introduced`, `fixed`, `last_affected` and `limit` events, using ecosystem version ordering. [JVM] For Python, use `packaging.version`.
- Severity:
  - Take the max CVSS_V3 base score computed from the vector (`CvssV3BaseScore`). Look first at package-level `severity[]`, then top-level `severity[]`, then `database_specific.severity` text.
  - Score buckets: ≥9.0 CRITICAL, ≥7.0 HIGH, ≥4.0 MEDIUM, >0 LOW, 0 NONE. An invalid score gives UNKNOWN.
  - Text severity: `MODERATE` becomes MEDIUM. Unknown text becomes UNKNOWN.
- Fix availability:
  - `fixedVersions` = the `fixed` events that close the range containing the installed version, verified unaffected, ordered by version, max 10.
  - `fixAvailable` = any fixed version is greater than the installed version.
- Status:
  - `SCANNED` when complete.
  - `PARTIAL` when any of these applies: limits hit, pagination truncated, failed package queries, failed detail fetches, or unresolved interpretation.
  - `ERROR` on total failure.
- Message: `"Scan completed against OSV.dev."` or `"Scan completed against OSV.dev, but <reasons>."`, followed by the EPSS note.
- Evidence limitation strings:
  - "Some dependency queries were not completed."
  - "Some advisory details were unavailable or could not be fully interpreted."
  - "Dependency inventory coverage is incomplete or unavailable."
  - "Some inventory packages were excluded by the scan limit."
  - "Findings with unknown severity are excluded from score penalties."

### EPSS enrichment (during the POST only; failure never discards OSV results)
- Enabled by `bootui.vulnerabilities.epss-enabled` (true).
- CVE ids are canonicalized (`CVE-\d{4}-\d{4,}`) from the vuln id and its aliases.
- Request: `GET {epss-base-uri}/data/v1/epss?cve=CVE-a,CVE-b&limit=n&offset=o`.
  - Chunks keep the comma-joined `cve` parameter at ≤2000 chars.
  - The response pagination fields (`total`, `offset`, `limit`) are validated.
  - Values outside 0..1 are rejected.
- Per vuln, the alias with the highest EPSS probability wins; ties go to the lowest CVE id.
- The message gets the suffix `" EPSS: X of Y requested CVEs have scores; ..."`.

### Ordering
- Dependencies: severity rank (CRITICAL 0, HIGH 1, MEDIUM 2, LOW 3, UNKNOWN 4, NONE 5, other 6), then packageName case-insensitive, then version.
- Vulnerabilities: non-dismissed first, then severity rank, then id.

### Dismissal
Source: `AC/web/DismissedRulesController.java`.
- `GET /bootui/api/dismissed-rules` returns `{"dismissed": ["<ruleId>", ...]}`.
- `POST /bootui/api/dismissed-rules/{ruleId}` dismisses and `DELETE /bootui/api/dismissed-rules/{ruleId}` restores. Both return the updated `{"dismissed":[...]}`.
- The vulnerability rule id is `"<vulnId>::<groupId:artifactId>"`, e.g. `GHSA-xxxx-yyyy-zzzz::org.yaml:snakeyaml`. URL-encode it in the path.
- Applying dismissals sets `dismissed=true` and recomputes `vulnerabilityCount`, `highestSeverity`, `vulnerable`, `severityCounts` and `scan.vulnerabilitiesFound` from active findings only.
- Global `bootui.read-only=true` blocks writes to `/dismissed-rules` with a 403 (`BootUiGlobalWritePolicy`, subject "dismissed-rules"). It is not a panel, so panel flags don't apply.
- Store (`ENG/advisor/DismissedRulesStore`):
  - File `boot-ui.yml` in the same directory as `bootui.overrides-file`, i.e. `.bootui/boot-ui.yml` (docs/PROPERTIES.md:64,106).
  - Format: header `# BootUI configuration (developer-local; safe to delete).`, then a `dismissedRules:` section with `  - <id>` lines.
  - Other lines are preserved, and the write is atomic.

```json
{"scanningEnabled":true,"total":143,"vulnerable":1,
 "severityCounts":[{"severity":"CRITICAL","count":0},{"severity":"HIGH","count":1},{"severity":"MEDIUM","count":0},{"severity":"LOW","count":0},{"severity":"UNKNOWN","count":0},{"severity":"NONE","count":0}],
 "scan":{"scanner":"OSV.dev","status":"SCANNED","message":"Scan completed against OSV.dev. EPSS: 1 of 1 requested CVEs have scores.","scannedAt":1761811200000,"packagesScanned":143,"packagesSkipped":0,"vulnerabilitiesFound":1},
 "coverage":{"status":"COMPLETE","archivesFound":143,"archivesIdentified":143,"archivesUnidentified":0,"unidentifiedArchives":[],"unidentifiedArchivesTruncated":false},
 "dependencies":[{"groupId":"org.yaml","artifactId":"snakeyaml","version":"1.33","packageName":"org.yaml:snakeyaml","source":"classpath","vulnerabilityCount":1,"highestSeverity":"HIGH",
   "vulnerabilities":[{"id":"GHSA-mjmj-j48q-9wg2","summary":"SnakeYaml Constructor Deserialization RCE","details":"...","severity":"HIGH","score":8.3,"aliases":["CVE-2022-1471"],"references":["https://..."],"fixedVersions":["2.0"],"fixAvailable":true,"epssScore":0.94,"epssPercentile":0.99,"dismissed":false}],
   "assessment":{"queryComplete":true,"detailAssessmentComplete":true}}],
 "evidence":{"usable":true,"coverageComplete":true,"limitations":[]}}
```

---

## 9. MCP server
Sources:
- Controllers and service: `AC/mcp/BootUiMcpController.java`, `AC/mcp/BootUiMcpService.java`, `AC/mcp/BootUiMcpTools.java`, `AC/mcp/McpServerState.java`, `AC/mcp/McpServerController.java`
- Engine: `ENG/mcp/McpProtocol.java`, `ENG/mcp/McpDispatcher.java`, `ENG/mcp/McpToolCatalog.java`, `ENG/mcp/McpToolSchema.java`, `ENG/mcp/McpArguments.java`
- Conformance: `CONF/AbstractMcpConformanceTest.java`

### Transport and path
- MCP "Streamable HTTP" with **POST only**, no SSE: `POST /bootui/api/mcp` with `Content-Type: application/json` and a single JSON-RPC 2.0 object. `GET /bootui/api/mcp` returns 405.
- Protocol version is `"2025-06-18"`, the only known version.
- Server name is `"bootui"`; the version is the BootUI version, or `"dev"`.
- The `MCP-Protocol-Version` request header, when present, must be a known version; otherwise the response is HTTP 400 with `INVALID_REQUEST "Unsupported MCP-Protocol-Version"`.
- `initialize` negotiates: a requested `params.protocolVersion` that is known is echoed back; anything else gets the default.
- It sits behind the same filter chain as the rest of the API (loopback/Host/cross-site, token). It is **not** panel-gated, because the `/mcp` path does not match the `/mcp-server` prefix.

### Opt-in
- `bootui.mcp.enabled` is `OFF` (default), `AUTO` or `ON`. Only `ON` enables it; `AUTO` is treated as off "so it is never silently exposed" (`McpServerState`: enabled = `configuredMode == ON`).
- Runtime toggle:
  - `POST /bootui/api/mcp-server/toggle` with body `{"enabled": bool}` sets the state; with no body or a null `enabled`, it flips the state.
  - It returns `McpServerStatus`, is in memory only, and sets `overridden = enabled != configuredEnabled`.
  - It is gated as an action of panel `mcp-server` (read-only gives 403).
- When disabled:
  - A request with an id gets HTTP 200 with `error {code:-32000, message:"BootUI MCP server is disabled. Enable it from the MCP Server panel or set bootui.mcp.enabled=ON."}`.
  - A notification gets 202.

### HTTP-level responses
- Notifications (no `id`, or `id:null`) get 202 with an empty body.
- A body over `bootui.mcp.max-payload-bytes` (1 MiB) gets 413 with `PARSE_ERROR "Request payload exceeds limit"`. The size is checked before parsing.
- Unparseable JSON gets 400 `PARSE_ERROR`. A JSON array (batch) gets 400 `INVALID_REQUEST "JSON-RPC batch requests are not supported by MCP Streamable HTTP transport"`.
- Request validation returns HTTP 200 with a JSON-RPC error:
  - A non-object body: `-32600 "Request must be a JSON-RPC object"`.
  - Missing or wrong `jsonrpc`: `-32600 'Request must include jsonrpc: "2.0"'`.
  - An id that is not a string, number or null: `-32600 "Request id must be a string, number, or null"`, with id null.
  - Non-object `params`: `-32602 "Request params must be an object"`.
  - Missing method: `-32602 "Missing 'method'"`.
- A rendered response over `bootui.mcp.max-response-bytes` (4 MiB) is replaced by `-32003 "MCP response exceeds configured byte limit"`.
- Error envelope: `{"jsonrpc":"2.0","id":<id|null>,"error":{"code":int,"message":str}}`.
- Codes:

| Code | Name |
|---|---|
| -32700 | PARSE_ERROR |
| -32600 | INVALID_REQUEST |
| -32601 | METHOD_NOT_FOUND (`"Unknown method: <m>"`) |
| -32602 | INVALID_PARAMS |
| -32603 | INTERNAL_ERROR (`"Internal error"`) |
| -32000 | SERVER_DISABLED |
| -32001 | SERVER_AT_CAPACITY (`"MCP server is at capacity; try again shortly."`) |
| -32002 | TOOL_TIMEOUT (`"MCP tool execution timed out"`) |
| -32003 | RESPONSE_TOO_LARGE |

### Methods
- `initialize` returns:
  ```json
  {"protocolVersion":"2025-06-18","capabilities":{"tools":{"listChanged":false},"prompts":{"listChanged":false}},"serverInfo":{"name":"bootui","version":"1.17.0"},"instructions":"<McpGuidance text>"}
  ```
- `ping` returns `{}`.
- `tools/list` returns `{"tools":[{"name","description","inputSchema",outputSchema:{"type","description"}}]}`. Only tools whose backing component exists are listed; panel enabled state is checked at call time, not list time.
- `tools/call` with params `{"name": str, "arguments"?: object}`.
- `prompts/list` returns `{"prompts":[{"name","description","arguments":[]}]}`. `prompts/get` with `{"name"}` returns `{"description","messages":[{"role":"user","content":{"type":"text","text":...}}]}`. Unknown name: `-32602 "Unknown prompt: <n>"`.

### tools/call pipeline (order matters; `McpDispatcher.callTool`)
1. A missing name gives `-32602 "Missing tool name"`. An unknown name gives `-32602 "Unknown tool: <n>"`.
2. Argument type errors give -32602:
   - `"Tool arguments must be an object"`
   - `"Argument 'query' must be a string"`
   - `"Argument 'id' must be a string"`
   - `"Argument 'limit' must be an integer"` and `"Argument 'limit' must be at least 1"`
   - The same pair for `offset` (minimum 0).
   - `scanId` must be a string.
3. Arguments not declared in the tool's schema give `-32602 "Unexpected tool argument(s): a, b"` (sorted).
4. A disabled panel gives a **tool error** (not a protocol error): `result {"content":[{"type":"text","text":"Panel is disabled via ..."}],"isError":true}`.
5. An action tool on a read-only panel gives a tool error with the read-only reason.
6. A missing required `id` gives `-32602 "Missing required argument: id"`. A missing `scanId` gives `"Missing required argument: scanId"`.
7. If the concurrency semaphore (`bootui.mcp.max-concurrent-calls`, 20) is full, the result is -32001.
8. The tool runs with timeout `bootui.mcp.execution-timeout` (30s), giving -32002 on timeout.
   - `ActionBusyException` becomes a tool error carrying the busy message.
   - A client-error exception becomes a tool error.
   - Anything else becomes -32603.
9. Success:
   ```json
   {"content":[{"type":"text","text":"<JSON of payload>"}],"structuredContent":<payload>,"isError":false}
   ```
   The payload is the **same DTO the REST endpoint returns**.

### Input schemas (`McpToolSchema`, rendered in `BootUiMcpService.schema`)
All schemas are `{"type":"object","properties":{...},"additionalProperties":false}`.
- `NONE`: `properties:{}`.
- `LIMIT`: `limit: {type:integer, minimum:1, description:"Optional maximum number of items to return. Capped by the bootui.mcp.max-results server limit."}`.
- `QUERY_LIMIT`: `query: {type:string, description:"Optional case-insensitive filter applied to the results."}` plus `limit` as above.
- `ID`: `id: {type:string, description:"Exact identifier of the resource to fetch."}`, with `required:["id"]`.
- `RULE_VIOLATIONS`: properties `id` (minLength 1), `scanId` (string, minLength 1, "The cached report's violationDetails.scanId. Never starts a scan."), `offset` (integer, min 0, default 0) and `limit` (default 100, capped at min(1000, max-results)), with `required:["id","scanId"]`.

Argument normalization:
- `query` and `id` are trimmed; blank becomes null.
- `limit` defaults to `bootui.mcp.max-results` (200) and is capped at that.

### MVP tool set (name → schema, panel, action?, what it returns)

| Tool | Schema | Panel | Action | Handler / returns |
|---|---|---|---|---|
| get_overview | NONE | overview | no | `OverviewDto` |
| get_health | NONE | health | no | `HealthNodeDto` |
| get_config | QUERY_LIMIT | config | no | `ConfigReport` = `config.list(query, source=null, overridesOnly=false, offset=null, limit)` (masked) |
| get_profile_diff | NONE | profile-diff | no | `ProfilesReport` |
| get_beans | QUERY_LIMIT | beans | no | `BeanList` = `beans(query, classification=null, offset=null, limit)` |
| get_mappings | QUERY_LIMIT | mappings | no | `MappingsReport` (flat) |
| get_loggers | QUERY_LIMIT | loggers | no | `LoggersReport` |
| get_vulnerabilities_report | NONE | vulnerabilities | no | `DependenciesReport` (cached or inventory; no network) |
| vulnerabilities_scan | NONE | vulnerabilities | **yes** | runs the OSV scan (same as REST POST), returns `DependenciesReport` |

Upstream has 89 tools in `ENG/McpToolCatalog.java`; 15 are Spring-only (graalvm, crac, transactions, conditions, startup, data, spring-security, jms, devtools, http-sessions).

Read-only guarantees:
- There is **no MCP tool that changes config, logger levels or dismissals**. Logger changes and config overrides exist only as REST actions.
- Every `action=true` tool references an action-capable panel (enforced in the `McpTool` constructor), and it is refused when that panel is read-only, including under global `bootui.read-only`.
- Disabled panels refuse all their tools.
- `get_*_rule_violations` "never starts a scan".

### `GET /bootui/api/mcp-server` (status panel)

```
McpServerStatus { enabled: bool, configuredMode: "OFF"|"AUTO"|"ON", overridden: bool, serverName: "bootui", serverVersion: str,
  transport: "http", endpoint: str /* "<apiPath>/mcp" */, protocolVersion: "2025-06-18", maxResults: int,
  callCount: long, totalLatencyMillis: long, capacityRefusals: long, timeouts: long, responseLimitRefusals: long,
  toolCount: int, tools: McpToolInfo[] }
McpToolInfo { name: str, description: str, panel: str, action: bool, panelEnabled: bool, panelReadOnly: bool }
```

---

## 10. Activation and safe mode

### Activation decision (`AC/BootUiActivationCondition.resolve`, defaults in `BootUiDefaults`)
- `bootui.enabled` (default `AUTO`):
  - `ON`, `TRUE` and `YES` mean ON; `OFF`, `FALSE` and `NO` mean OFF (YAML booleans).
  - Any other value means **disabled**, with reason `"Disabled: invalid bootui.enabled value '<raw>'"`.
- Order of evaluation, where the first match wins:
  1. An active profile is in `bootui.disabled-profiles` (default `prod,production`):
     - Mode ON: enabled with a **warning**, `"Explicitly enabled (bootui.enabled=ON) despite disabled profile '<p>'"`.
     - Otherwise: disabled, `"Disabled because active profile '<p>' is in bootui.disabled-profiles"`.
  2. Mode OFF: disabled, `"Disabled by bootui.enabled=OFF"`.
  3. Mode ON: enabled, `"Enabled by bootui.enabled=ON"`.
  4. An active profile is in `bootui.enabled-profiles` (default `dev,local`): enabled, `"Enabled by active profile '<p>'"`.
  5. [JVM] The DevTools class `org.springframework.boot.devtools.restart.RestartScope` is on the classpath: enabled, `"Enabled because spring-boot-devtools is on the classpath"`. The Python equivalent is a dev-server signal such as Django `DEBUG=True` with runserver, `uvicorn --reload`, or `FLASK_DEBUG=1`.
  6. Otherwise: disabled, `"Disabled: no enabled profile and devtools is not on the classpath"`.
- The result is surfaced as `overview.activation {enabled, localhostOnly, reason, warnings}`.
- When inactive, every request under the BootUI mounts gets a 404 (`BootUiShellGuardFilter`), so nothing reveals that BootUI exists.
- [JVM] On Quarkus, activation is by build-time launch mode instead of these properties.
- "Profiles" in Python map to an env var (e.g. `SHARPIT_PROFILES` or `APP_ENV`).

### Request guard chain (only on BootUI paths; order)
1. Security headers and legacy-path redirect.
2. `LocalhostOnlyFilter` runs `ENG/safety/LocalhostGuard.decide`:
   - **Source check** (skipped when `allow-non-localhost=true`). `remoteAddr` must be one of:
     - loopback
     - inside a `bootui.trusted-proxies` CIDR
     - the auto-detected container gateway, when `trust-container-gateway` is `AUTO` and running in a container, or when it is `ON`
     - Otherwise: 403 `"BootUI is restricted to loopback requests. Set bootui.allow-non-localhost=true to override, add a trusted source range to bootui.trusted-proxies, or (when running in a container) set bootui.trust-container-gateway=AUTO to trust the auto-detected container gateway."`
   - **Host check** (always on, against DNS rebinding). If a `Host` header is present, its parsed host must be in {`localhost`, `127.0.0.1`, `::1`, `0:0:0:0:0:0:0:1`} or `bootui.allowed-hosts`. An unparseable Host is rejected. Message: `"BootUI rejected an unrecognized Host header. Add it to bootui.allowed-hosts to allow this hostname."`
   - **Cross-site write check** (always on). For methods other than GET, HEAD and OPTIONS, either of these gives a 403 `"BootUI rejected a cross-site request to a state-changing endpoint."`:
     - `Sec-Fetch-Site: cross-site`
     - an `Origin` whose host differs from the `Host` header (`Origin: null` counts as a mismatch)
   - Reject body: `{"error":"<message>"}`.
3. `ApiAuthenticationFilter` (API paths only, always registered):
   - A trusted source (passed the loopback/proxy/gateway test) needs **no token**.
   - Otherwise the request needs `Authorization: Bearer <token>` or the cookie `BOOTUI_SESSION=<token>`, compared in constant time.
   - Failure: 401 (see §1).
   - `POST <apiPath>/auth/session` with a bearer header returns 204. For an untrusted source it sets `BOOTUI_SESSION=<token>; Path=<ctx><apiPath>; HttpOnly; SameSite=Strict[; Secure]`. The UI's token prompt calls this (`UI/App.vue:502`).
   - The token is `bootui.authentication.token`. If blank and remote access is configured (`allow-non-localhost`, `trusted-proxies` non-empty, or gateway trust not OFF), a 256-bit random base64url token is generated and logged once at startup. Configured tokens are never logged.
4. `PanelAccessFilter` (API paths only):
   - Global `bootui.read-only` gives 403 for unsafe methods on `/dismissed-rules`.
   - A disabled panel gives 403 for **all** methods on its prefix.
   - An action-capable panel that is read-only gives 403 for unsafe methods (POST, PUT, PATCH, DELETE).
   - Body: `{"error":"BootUI panel access denied","panel":...,"reason":...}`.
5. Console-activity tracking for `free-on-idle`. [JVM] Optional.

### CSRF token
- `UI/api.js`: for non-safe methods the client sends `X-XSRF-TOKEN` from the `XSRF-TOKEN` cookie. If the cookie is missing, it primes it with `GET api/overview` first.
- This exists for host apps running **Spring Security's** CsrfFilter. BootUI's own protection is the Origin/Sec-Fetch-Site check above. [JVM]
- sharpit can drop the XSRF cookie if its UI does not need it. Keep the Origin/Sec-Fetch-Site check.

### Never network or mutate on render (rule)
- Every GET is read-only and local:
  - `GET /vulnerabilities` returns the cached scan or the inventory, never OSV.
  - The Overview refresh issues GETs only, and only for manifest panels.
  - The MCP `get_*` tools never start scans.
- Outbound network calls (OSV, EPSS) and mutations (overrides, logger level, dismissals, MCP toggle) happen **only** on an explicit POST/DELETE from a user click or an MCP action tool. Each one is gated by panel read-only, global read-only and single-flight.

### Properties relevant to the MVP (`docs/PROPERTIES.md`)

| Property | Default | Meaning |
|---|---|---|
| `bootui.enabled` | `AUTO` | `AUTO` = only for enabled profiles or DevTools; `ON` forces on; `OFF` forces off. YAML true/yes and false/no are accepted. [JVM: Spring only] |
| `bootui.enabled-profiles` | `dev,local` | Profiles that activate under AUTO. |
| `bootui.disabled-profiles` | `prod,production` | Profiles that force off unless `enabled=ON`. |
| `bootui.path` | `/bootui` | UI base path (app-relative). |
| `bootui.api-path` | `<bootui.path>/api` | API base path (also MCP, CLI). |
| `bootui.allow-non-localhost` | `false` | Relaxes **only** the source-address check; Host, cross-site and token checks stay. |
| `bootui.allowed-hosts` | empty | Extra accepted Host values; entries must be valid hostnames or IP literals. |
| `bootui.trusted-proxies` | empty | CIDRs trusted like loopback (Docker bridge). Source check only. |
| `bootui.trust-container-gateway` | `OFF` | `OFF` never; `AUTO` trusts the detected gateway /32 when in a container; `ON` trusts a detected gateway even if container detection is inconclusive. Detection: `/proc/net/route` default gateway, or `gateway.docker.internal`. |
| `bootui.authentication.token` | generated | Token for non-trusted API callers; generated and logged once if blank and remote access is configured. |
| `bootui.read-only` | `false` | Disables every browser-triggered action; data stays visible. |
| `bootui.panels.<id>.enabled` | `true` | Hide the panel and 403 its API. |
| `bootui.panels.<id>.read-only` | `false` | 403 unsafe methods for action-capable panels; refuses MCP action tools. |
| `bootui.expose-values` | `MASKED` | `MASKED` / `METADATA_ONLY` / `FULL` (FULL can disclose secrets). |
| `bootui.mask-secrets` | `true` | Enables secret masking. |
| `bootui.overrides-file` | `.bootui/application-bootui.properties` | Config-override persistence; `boot-ui.yml` (dismissals) is resolved in the same dir. Set from env, not from app config. |
| `bootui.show-banner` | `true` | Print the URL at startup. |
| `bootui.vulnerabilities.osv-enabled` | `true` | Extra gate for scans. |
| `bootui.vulnerabilities.request-timeout` | `10s` | Per OSV request. |
| `bootui.vulnerabilities.max-packages` | `500` | Batch cap; excess goes to `packagesSkipped`. |
| `bootui.vulnerabilities.max-advisories` | `200` | Detail-fetch cap. |
| `bootui.vulnerabilities.osv-base-uri` | `https://api.osv.dev` | OSV base (stub in tests). |
| `bootui.vulnerabilities.epss-enabled` | `true` | EPSS enrichment during the scan. |
| `bootui.vulnerabilities.epss-base-uri` | `https://api.first.org` | EPSS base. |
| `bootui.mcp.enabled` | `OFF` | `OFF`/`AUTO` keep it off; only `ON` exposes it. |
| `bootui.mcp.max-results` | `200` | Default and cap for `limit`. |
| `bootui.mcp.max-payload-bytes` | `1048576` | Request size cap (413). |
| `bootui.mcp.max-concurrent-calls` | `20` | Over the cap gives -32001. |
| `bootui.mcp.execution-timeout` | `30s` | Over the limit gives -32002. |
| `bootui.mcp.max-response-bytes` | `4194304` | Over the cap gives -32003. |
| `bootui.cli.enabled` | `true` | CLI endpoint; when false, a call gives 503. |
| `bootui.cli.max-results` / `max-concurrent-calls` / `execution-timeout` | `200` / `20` / `30s` | Like MCP; over capacity gives 429, timeout gives 504. |
| `bootui.free-on-idle.enabled` / `.timeout` | `true` / `5m` | [JVM] Releases buffers when idle. Skip. |

---

## 11. CLI (brief)
Sources: `bootui-cli/src/main/java/io/github/jdubois/bootui/cli/*`, `ENG/cli/*`, `AC/cli/BootUiCliController.java`, `docs/CLI.md`.

- Every CLI command is one MCP tool, mapped mechanically. It runs through the same dispatcher, so it shares panel gating and counters. It does **not** need `bootui.mcp.enabled`.
- `GET /bootui/api/cli` returns:
  ```
  CliServerStatus {enabled, serverName, serverVersion, endpoint, maxResults, callCount, totalLatencyMillis, capacityRefusals, timeouts, toolCount, tools: CliToolInfo[]}
  CliToolInfo {name, command /* e.g. "beans", "profile diff", "vulnerabilities scan" */, description, panel, action, schema, arguments: str[], panelEnabled, panelReadOnly}
  ```
- `POST /bootui/api/cli/tools/{toolName}` takes the arguments object as its body (`{"query":"x","limit":20}`).
  - Success: HTTP 200 with the bare payload DTO.
  - Failure: `{"error": msg}` with a status mapped by `ENG/cli/CliOutcomes`:

| Outcome | Status |
|---|---|
| Unknown tool | 404 |
| Other INVALID_PARAMS | 400 |
| Panel disabled or read-only | 403 |
| Action busy | 409 |
| At capacity | 429 |
| Timeout | 504 |
| CLI disabled | 503 (`"BootUI CLI endpoint is disabled. Set bootui.cli.enabled=true to allow command-line access."`) |
| Other | 500 |

- Command paths (`ENG/cli/CliCommandPaths`):

| Command | Tool |
|---|---|
| overview | get_overview |
| health | get_health |
| config | get_config |
| beans | get_beans |
| mappings | get_mappings |
| loggers | get_loggers |
| profile diff | get_profile_diff |
| vulnerabilities report | get_vulnerabilities_report |
| vulnerabilities scan | vulnerabilities_scan |

- Global options:
  - `--url` (default `http://localhost:8080`, or `$BOOTUI_URL`)
  - `--api-path`
  - `--token` (sent as `Authorization: Bearer`, or `$BOOTUI_TOKEN`)
  - `--json`, `--timeout`, `--no-color`, `--verbose`
  - Per-tool: `--query`, `--limit`, `--offset`, `--scan-id`
- Exit codes: 0 success, 1 error, 2 refused, 3 threshold.
- The CLI's update check reads a cache only and never makes a network call on the command path. `BOOTUI_NO_UPDATE_CHECK=1` disables it. [JVM] The jar, JBang and Maven-metadata parts can be dropped.
- sharpit: a `sharpit` console script can call the same `/cli` endpoints with `httpx`.

---

## Spring/JVM-only items the porter can drop
- `/mappings` raw actuator descriptor; `api/conditions`; Spring `@ConfigurationProperties` metadata (`propertySuggestions` can be `[]`); config overrides (optional for MVP).
- DevTools-classpath activation (replace with a dev-server signal); Quarkus launch-mode activation.
- XSRF-TOKEN cookie priming (Spring Security); `free-on-idle`; jar `coverage.archives*` semantics; Maven ecosystem and version ordering (use PyPI and `packaging`).
- 15 Spring-only MCP tools and every non-MVP panel.

## Open ambiguities (verify before freezing the sharpit contract)
1. Status for `IllegalArgumentException` outside loggers (config override validation): upstream falls to host default handling. Recommend `400 {"error"}`.
2. Whether `DependenciesReport` emits a top-level `status` (derived accessor). Probably not.
3. Null inclusion: assumed nulls are serialized.
