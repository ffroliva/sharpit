<script lang="ts">
  import AdvisorPanel from '../components/AdvisorPanel.svelte';
  import { del, errorText, get, post } from '../lib/api';
  import { scannedWhen, upgradeHint } from '../lib/format';
  import type { Dependency, Panel, Vulnerability, VulnReport } from '../lib/types';

  let { panel }: { panel: Panel } = $props();

  let report = $state<VulnReport | null>(null);
  let loadError = $state<string | null>(null);

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
  const path = (rule: string) => `dismissed-rules/${encodeURIComponent(rule)}`;

  async function load() {
    try {
      report = await get<VulnReport>('vulnerabilities');
      loadError = null;
    } catch (e) {
      loadError = errorText(e);
    }
  }
  const reload = async () => void (report = await get<VulnReport>('vulnerabilities')); // a failed reload keeps the old report

  const tone = (severity: string) =>
    severity === 'CRITICAL' || severity === 'HIGH' ? 'danger' : severity === 'MEDIUM' ? 'warn' : 'muted';

  load();
</script>

<AdvisorPanel
  title="Vulnerabilities"
  {report}
  {loadError}
  vulnerabilities
  readOnlyReason={panel.readOnly ? (panel.readOnlyReason ?? 'Read-only') : null}
  scanDisabledReason={report && !report.scanningEnabled ? report.scan.message : null}
  scanLabel={(phase) => (phase === 'scanning' ? 'Scanning…' : phase === 'results' || phase === 'failed' ? 'Scan again' : 'Scan with OSV.dev')}
  onScan={async () => void (report = await post<VulnReport>('vulnerabilities/scan'))}
  onDismiss={async (rule) => { await post(path(rule)); await reload(); }}
  onRestore={async (rule) => { await del(path(rule)); await reload(); }}
>
  {#snippet status(phase)}
    {#if phase === 'scanning'}
      Scanning {report?.total ?? ''} packages with OSV.dev…
    {:else if phase === 'results' && report}
      {report.scan.packagesScanned} packages scanned {scannedWhen(report.scan.scannedAt!)}
    {:else if report}
      {report.total} packages
    {/if}
  {/snippet}
  {#snippet children({ phase, pending, toggle })}
    {#if phase === 'never-scanned' || phase === 'scanning'}
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
      <p class="notice muted">Check the network connection to api.osv.dev, then scan again.</p>
      {@render inventory()}
    {:else if phase === 'results' && report}
      <section class="block summary">
        <p>
          {#if active === 0}
            <span class="ok">No known vulnerabilities</span> in {report.scan.packagesScanned} packages.
          {:else}
            <strong>{report.vulnerable}</strong> of {report.total} packages have {active} known
            {active === 1 ? 'vulnerability' : 'vulnerabilities'}.
          {/if}
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
                  {#if upgradeHint(dep.packageName, v.fixedVersions)}
                    <code class="hint">{upgradeHint(dep.packageName, v.fixedVersions)}</code>
                  {:else if v.fixedVersions.length > 0}<span class="muted">No fix listed above your version</span>
                  {:else}<span class="muted">No fixed version yet</span>{/if}
                </td>
                <td class="num">
                  <button
                    onclick={() => toggle(ruleId(dep, v), v.dismissed)}
                    disabled={!!pending || panel.readOnly}
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
  {/snippet}
</AdvisorPanel>

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
  tr.dismissed td { color: var(--muted); }
  tr.dismissed .mono { text-decoration: line-through; }
  .line { display: block; }
  .hint { user-select: all; white-space: nowrap; } /* one click selects the whole command */
  section.block h2 { padding-bottom: var(--s2); }
</style>
