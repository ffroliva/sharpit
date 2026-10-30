<script lang="ts">
  import { ApiError, del, get, post } from '../lib/api';
  import { scannedWhen, upgradeHint } from '../lib/format';
  import { scrollable } from '../lib/scrollable';
  import type { Dependency, Panel, Vulnerability, VulnReport } from '../lib/types';

  let { panel }: { panel: Panel } = $props();

  let report = $state<VulnReport | null>(null);
  let loadError = $state<string | null>(null);
  let scanning = $state(false);
  /** The 409 body's own text, shown next to the Scan button. */
  let busy = $state<string | null>(null);
  let scanError = $state<string | null>(null);
  let actionError = $state<string | null>(null);
  let pendingRule = $state<string | null>(null);

  type Phase = 'loading' | 'load-failed' | 'never-scanned' | 'scanning' | 'failed' | 'results';
  const phase: Phase = $derived(
    scanning
      ? 'scanning'
      : scanError || report?.scan.status === 'ERROR'
        ? 'failed'
        : loadError
          ? 'load-failed'
          : !report
            ? 'loading'
            : report.scan.scannedAt === null
              ? 'never-scanned'
              : 'results',
  );
  const disabledReason = $derived(
    panel.readOnly
      ? panel.readOnlyReason
      : report && !report.scanningEnabled
        ? report.scan.message
        : null,
  );

  const SEVERITY = ['CRITICAL', 'HIGH', 'MEDIUM', 'LOW', 'UNKNOWN', 'NONE'];
  const rank = (severity: string) => (SEVERITY.indexOf(severity) + 7) % 7; // unknown words sort last
  // worst first, so the finding to fix next is at the top
  const findings = $derived(
    (report?.dependencies ?? [])
      .flatMap((dep) => dep.vulnerabilities.map((v) => ({ dep, v })))
      .sort((a, b) => rank(a.v.severity) - rank(b.v.severity)),
  );
  const active = $derived(findings.filter((f) => !f.v.dismissed).length);

  // sharpit's rule id (dismissals.py): `<vulnId>::pypi:<name>`
  const ruleId = (dep: Dependency, v: Vulnerability) => `${v.id}::pypi:${dep.packageName}`;

  async function load() {
    try {
      report = await get<VulnReport>('vulnerabilities');
      loadError = null;
    } catch (e) {
      loadError = describe(e);
    }
  }

  async function scan() {
    if (scanning || disabledReason) return;
    scanning = true;
    busy = null;
    scanError = null;
    try {
      report = await post<VulnReport>('vulnerabilities/scan');
    } catch (e) {
      if (e instanceof ApiError && e.status === 409) busy = field(e.body, 'message') ?? field(e.body, 'error') ?? 'Another scan is running.';
      else scanError = describe(e);
    } finally {
      scanning = false;
    }
  }

  async function toggle(dep: Dependency, v: Vulnerability) {
    const rule = ruleId(dep, v);
    if (pendingRule || panel.readOnly) return;
    pendingRule = rule;
    actionError = null;
    try {
      const path = `dismissed-rules/${encodeURIComponent(rule)}`;
      await (v.dismissed ? del(path) : post(path));
      report = await get<VulnReport>('vulnerabilities'); // a failed reload keeps the old report
    } catch (e) {
      actionError = `${v.dismissed ? 'Restore' : 'Dismiss'} failed: ${describe(e)}`;
    } finally {
      pendingRule = null;
    }
  }

  function describe(e: unknown): string {
    if (e instanceof ApiError) return field(e.body, 'error') ?? e.message;
    return 'The application is not responding.';
  }

  function field(body: unknown, key: string): string | undefined {
    const value = typeof body === 'object' && body !== null ? (body as Record<string, unknown>)[key] : undefined;
    return typeof value === 'string' ? value : undefined;
  }

  const tone = (severity: string) =>
    severity === 'CRITICAL' || severity === 'HIGH' ? 'danger' : severity === 'MEDIUM' ? 'warn' : 'muted';

  load();
</script>

<div class="panel" data-phase={phase}>
  <header class="panel-head">
    <h1>Vulnerabilities</h1>
    <span class="grow muted" aria-live="polite">
      {#if phase === 'scanning'}
        Scanning {report?.total ?? ''} packages with OSV.dev…
      {:else if phase === 'results' && report}
        {report.scan.packagesScanned} packages scanned {scannedWhen(report.scan.scannedAt!)}
      {:else if report}
        {report.total} packages
      {/if}
    </span>
    {#if busy}<span class="warn" role="status">{busy}</span>{/if}
    <button class="primary" onclick={scan} disabled={scanning || !!disabledReason} aria-busy={scanning}>
      {scanning ? 'Scanning…' : phase === 'results' || phase === 'failed' ? 'Scan again' : 'Scan with OSV.dev'}
    </button>
  </header>

  <div class="panel-body" use:scrollable role="region" aria-label="Vulnerabilities">
    {#if disabledReason}<p class="notice warn">{disabledReason}</p>{/if}
    {#if actionError}<p class="notice danger" role="alert">{actionError}</p>{/if}

    {#if phase === 'loading'}
      <table aria-hidden="true"><tbody>{#each { length: 6 } as _}<tr class="skeleton"><td></td><td></td></tr>{/each}</tbody></table>
    {:else if phase === 'load-failed'}
      <div class="empty"><p class="lead danger">Could not load the dependency inventory</p><p>{loadError}</p></div>
    {:else if phase === 'never-scanned' || phase === 'scanning'}
      <div class="empty">
        <p class="lead">{phase === 'scanning' ? 'Scanning…' : 'Not scanned yet'}</p>
        <p class="muted">
          {#if phase === 'scanning'}
            Sending the names and versions of {report?.total} packages to OSV.dev…
          {:else}
            Scanning sends the names and versions of the {report?.total} installed packages to OSV.dev. Nothing leaves this
            machine until you press Scan.
          {/if}
        </p>
      </div>
      {@render inventory()}
    {:else if phase === 'failed'}
      <div class="empty" role="alert">
        <p class="lead danger">Scan failed</p>
        <p>{scanError ?? report?.scan.message}</p>
        <p class="muted">Check the network connection to api.osv.dev, then scan again.</p>
      </div>
      {@render inventory()}
    {:else if report}
      <section class="block summary">
        <p>
          {#if active === 0}
            <span class="ok">No known vulnerabilities</span> in {report.scan.packagesScanned} packages.
          {:else}
            <strong>{report.vulnerable}</strong> of {report.total} packages have {active} known
            {active === 1 ? 'vulnerability' : 'vulnerabilities'}.
          {/if}
          {#each report.severityCounts.filter((c) => c.count > 0) as c (c.severity)}
            <span class="tag {tone(c.severity)}">{c.severity} {c.count}</span>
          {/each}
        </p>
        {#if report.scan.packagesSkipped > 0}
          <p class="warn">{report.scan.packagesSkipped} packages were not scanned (package limit reached).</p>
        {/if}
        {#if report.scan.status === 'PARTIAL'}<p class="warn">{report.scan.message}</p>{/if}
      </section>
      {#if findings.length > 0}
        <table>
          <thead>
            <tr><th>Package</th><th>Advisory</th><th>Severity</th><th>Fix</th><th><span class="visually-hidden">Action</span></th></tr>
          </thead>
          <tbody>
            {#each findings as { dep, v } (ruleId(dep, v))}
              <tr class:dismissed={v.dismissed}>
                <td class="mono">{dep.packageName} {dep.version}</td>
                <td>
                  <a class="mono" href="https://osv.dev/vulnerability/{encodeURIComponent(v.id)}" target="_blank" rel="noreferrer">{v.id}</a>
                  {#if v.aliases.length}<span class="mono muted sm"> {v.aliases.join(', ')}</span>{/if}
                  {#if v.summary}<span class="line muted">{v.summary}</span>{/if}
                </td>
                <td>
                  <span class={v.dismissed ? 'muted' : tone(v.severity)}>{v.severity}</span>
                  {#if v.score !== null}<span class="muted"> {v.score.toFixed(1)}</span>{/if}
                  {#if v.dismissed}<span class="tag muted">dismissed</span>{/if}
                </td>
                <td>
                  {#if upgradeHint(dep.packageName, dep.version, v.fixedVersions)}
                    <code class="hint">{upgradeHint(dep.packageName, dep.version, v.fixedVersions)}</code>
                  {:else if v.fixedVersions.length > 0}<span class="muted">No fix listed above your version</span>
                  {:else}<span class="muted">No fixed version yet</span>{/if}
                </td>
                <td class="num">
                  <button
                    onclick={() => toggle(dep, v)}
                    disabled={!!pendingRule || panel.readOnly}
                    title={panel.readOnly ? (panel.readOnlyReason ?? undefined) : undefined}
                    aria-label="{v.dismissed ? 'Restore' : 'Dismiss'} {v.id} in {dep.packageName}"
                  >
                    {v.dismissed ? 'Restore' : 'Dismiss'}
                  </button>
                </td>
              </tr>
            {/each}
          </tbody>
        </table>
      {/if}
      <section class="block"><h2>Scanned packages</h2></section>
      {@render inventory(true)}
    {/if}
  </div>
</div>

{#snippet inventory(scanned = false)}
  {#if report && report.dependencies.length > 0}
    <table>
      <thead><tr><th>Package</th><th>Version</th>{#if scanned}<th>Result</th>{/if}</tr></thead>
      <tbody>
        {#each report.dependencies as dep (dep.packageName + dep.version)}
          {@const open = dep.vulnerabilities.filter((v) => !v.dismissed).length}
          <tr>
            <td class="mono">{dep.packageName}</td><td class="mono">{dep.version}</td>
            {#if scanned}
              <td class={open ? tone(dep.highestSeverity) : 'muted'}>
                {open ? `${open} known ${open === 1 ? 'vulnerability' : 'vulnerabilities'}` : 'no known issues'}
              </td>
            {/if}
          </tr>
        {/each}
      </tbody>
    </table>
  {/if}
{/snippet}

<style>
  .summary p { margin: 0; padding: var(--s3) var(--s4) 0; }
  .summary p:last-child { padding-bottom: var(--s3); }
  .summary .tag { margin-left: var(--s2); }
  tr.dismissed td { color: var(--muted); }
  tr.dismissed .mono { text-decoration: line-through; }
  .line { display: block; }
  .hint { user-select: all; white-space: nowrap; } /* one click selects the whole command */
  section.block h2 { padding-bottom: var(--s2); }
</style>
