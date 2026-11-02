# Predict: Lane D1, 2.2.0 envelope drift (dismissed findings, guard subject, header dedup, overview run)

Run of `skills/predict/SKILL.md` on the lane plan's exact Task 0 brief, with the BootUI 2.2.0 oracle read directly
(`boot-ui-ref` at `v2.2.0`: `DismissedFindingsController.java`, `DismissedRulesStore.java`,
`DismissedFindingsStoreTests.java`). Personas written in turn, each before reading the next.

## Verdict: CAUTION   Confidence: 7/10

## Summary

The guard change is one dict entry in `_GLOBAL_WRITE_SUBJECTS`; the chain order and every error string stay as they
are. The store is a port of BootUI's line format (Base64URL notes, so user text never reaches YAML syntax). One real
regression was found in the plan's header-dedup step (assets would gain `Pragma: no-cache`), and two sharpit-specific
validation choices need logging; with those mitigations the change is safe to build.

## Persona findings

### Architect: GO (8/10)
- Store stays in `engine/advisors/dismissals.py` (stdlib `base64` only); routes in `sharpit/fastapi/`. No new
  dependency, no engine import of FastAPI/Starlette.
- `routes/__init__.py` is outside D1's May-touch list. The adapter seam `adapter._routes` (May-touch) already wraps
  `build_routes`; the new `routes/dismissed_findings.py::build_routes` is appended there. No other lane's file touched.
- Reuse the existing `AdvisorViolationError(status, message)` (BootUI `AdvisorViolationException`) instead of three new
  exception classes: the routes already render it as `status {"error": message}`.

### Security: CAUTION (7/10)
- Guard chain order unchanged: the new subject is consulted inside `_panel_access`, the last link, exactly like
  `/dismissed-rules`. `GET` is a safe method, so the global write policy never touches it; `panel_for_api_path`
  maps `/dismissed-findings` to no panel, so the list is reachable whenever sharpit is active (BootUI behaviour).
- `POST`/`DELETE` under `SHARPIT_READ_ONLY=true` → 403 `{"error": "sharpit panel access denied", "panel":
  "dismissed-findings", "reason": "sharpit is read-only via SHARPIT_READ_ONLY=true"}` via the existing
  `_panel_denied` + `read_only_reason` (no new strings).
- Line injection: rule id and identity are refused if they hold whitespace or control characters; the note is
  Base64URL (no padding), so a note can never forge a line or a section. A stored line that is not exactly the
  written format is ignored, counted, and kept verbatim (never echoed).
- Error bodies: fixed messages only; the body is read as capped bytes (`_read_capped`, 64 KiB) and parsed in the
  route, so no framework diagnostic quotes the note. Notes are user text served by `GET` only, no MCP/CLI binding.
- **Risk (found here):** the plan's per-header dedup, applied unconditionally, adds `Pragma: no-cache` to static assets
  (`security_headers("asset")` deliberately has no `Pragma`), changing the asset cache policy. Mitigation below.

### Contract parity: CAUTION (7/10)
- DTOs: `{"dismissed": [{"ruleId", "identity", "note"}], "ignored": int}`, every key emitted, `note` null when absent.
- Verbatim strings from BootUI: the 400 body message, `Dismissed finding note must be at most 200 characters.`,
  `Too many dismissed findings: restore some before dismissing more.` (409), `Dismissed finding rule id is not a
  valid advisor rule id.`, `Dismissed finding identity is not a valid finding identity.`, `Dismissed finding note is
  not valid text.`. 415 comes from Spring's `consumes = application/json`.
- **Deviations to log:** BootUI's rule-id pattern (`[A-Z][A-Z0-9]*(-[A-Z0-9]+)+`) and `v<n>:` identity grammar do
  not fit sharpit's ids (`sharpit.max-queries`, pytest node ids, fingerprints). sharpit keeps its own rule-id charset
  (`[A-Za-z0-9._:-]`, ≤ 64, owned by an advisor via `advisor_for`) and an identity of ≤ 512 non-whitespace,
  non-control characters (the lane plan's rule). Neither can inject a line.
- Overview `run` and the `Scorecard` title follow contract §2 exactly.

### Host-app compatibility: GO (8/10)
- No new Starlette internals; `MutableHeaders` membership is case-insensitive already.
- A host middleware that sets one security header without CSP now gets the rest added once, not duplicated.
- Windows/POSIX: atomic write keeps the existing temp-file + `os.replace` path.

### Devil's Advocate: GO (7/10)
- Smallest change: one guard entry, one route module, one store extension, one line in `panels.py`. The 503 for
  `state_dir=None` in the plan cannot happen (`state_dir` is a `str` defaulting to `.sharpit`): drop it.
- `DismissalStorageError` adds nothing over the existing behaviour (an OS error is a 500 for `/dismissed-rules` too):
  drop it, log the decision.

## High-confidence risks (2+ personas)
1. Asset `Pragma` regression from naive per-header dedup (Security, Host-app).
2. BootUI id grammars do not fit sharpit ids; a straight port would refuse every real sharpit finding
   (Contract parity, Devil's Advocate).

## Conflicts resolved
- Plan's three new exception classes vs reuse of `AdvisorViolationError`: reuse (Architect, Devil's Advocate); the
  HTTP status and message are what the contract pins.
- Owning-panel gate for finding mutations (sharpit does it for `/dismissed-rules`) vs BootUI's global-only policy:
  BootUI wins (contract §1.4 names only `read-only`); the guard cannot read the body, and the floor
  (trusted source, Host, cross-site, token) still applies.

## Required mitigations (CAUTION)
1. Header dedup: a response that already carries `Content-Security-Policy` owns its whole header set (unchanged);
   otherwise each baseline header is added only when absent (case-insensitive). Test pins both: no duplicate
   `X-Content-Type-Options`, and assets keep no `Pragma`.
2. Identity/rule-id validation as above, logged in `handoff.md` decisions; a test proves a newline/space can never
   forge a line.
3. Error bodies never quote the body or the note (`test_mvc_refuses_bad_bodies_with_a_fixed_message_that_never_quotes_the_note`,
   `tests/masking/test_d1_masking.py`).

## High-tier llm-council
`skills/llm-council` (`--tier high`) reviews a diff; at Task 0 there is none. It is recorded under "Needs from
coordinator" in `handoff.md` to run on the lane head before merge (the review lives in the coordinator's
`review.md`, which this lane may not write).

## Recommended next step
GO with the three mitigations: Task 1 (store), Task 2 (guard, routes, headers, title), Task 3 (overview run, MCP limits).
