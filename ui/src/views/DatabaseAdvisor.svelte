<script lang="ts">
  import AdvisorPanel from '../components/AdvisorPanel.svelte';
  import { del, errorText, get, post } from '../lib/api';
  import { scannedWhen } from '../lib/format';
  import type { AdvisorReport, Panel, ViolationsPage } from '../lib/types';

  let { panel }: { panel: Panel } = $props();

  type DataSource = { name: string; product: string | null; status: string; message: string | null; tablesAnalyzed: number; truncated: boolean };
  type Diagnostic = { source: string; level: string; message: string };
  type DatabaseAdvisorReport = AdvisorReport & { tablesAnalyzed: number; dataSources: DataSource[]; diagnostics: Diagnostic[] };
  let report = $state<DatabaseAdvisorReport | null>(null);
  let loadError = $state<string | null>(null);
  // INFO diagnostics are neutral notes (a rule that does not apply); warnings and errors are missing coverage
  const problems = $derived((report?.diagnostics ?? []).filter((d) => d.level !== 'INFO'));

  // GET returns the last scan (or NOT_SCANNED) and never connects; only the button scans
  async function load() {
    try {
      report = await get<DatabaseAdvisorReport>('database-advisor');
      loadError = null;
    } catch (e) {
      loadError = errorText(e);
    }
  }
  load();

  const rule = (id: string) => `dismissed-rules/${encodeURIComponent(id)}`;
  const reload = async () => void (report = await get<DatabaseAdvisorReport>('database-advisor')); // a failed reload keeps the old report
</script>

<AdvisorPanel
  title={panel.title}
  {report}
  {loadError}
  readOnlyReason={panel.readOnly ? (panel.readOnlyReason ?? 'Read-only') : null}
  scanLabel={(phase) => (phase === 'scanning' ? 'Scanning…' : phase === 'results' || phase === 'failed' ? 'Scan again' : 'Run Database checks')}
  onScan={async () => void (report = await post<DatabaseAdvisorReport>('database-advisor/scan'))}
  onDismiss={async (id) => { await post(rule(id)); await reload(); }}
  onRestore={async (id) => { await del(rule(id)); await reload(); }}
  onDismissFinding={async (fingerprint) => { await post(rule(fingerprint)); await reload(); }}
  loadDismissed={async () => (await get<{ dismissed: string[] }>('dismissed-rules')).dismissed}
  loadViolations={(id, offset) =>
    get<ViolationsPage>(`database-advisor/rules/${encodeURIComponent(id)}/violations`, { scanId: report?.violationDetails?.scanId, offset, limit: 100 })}
>
  {#snippet status(phase)}
    {#if phase === 'scanning'}Reading the schema…
    {:else if phase === 'results' && report?.scan.scannedAt}{report.tablesAnalyzed} tables across {report.dataSources.length} datasources scanned {scannedWhen(report.scan.scannedAt)}
    {/if}
  {/snippet}
</AdvisorPanel>

{#if report?.dataSources.length}
  <section aria-label="Datasources">
    <h2>Datasources</h2>
    <ul>
      {#each report.dataSources as source (source.name)}
        <li>{source.name} {source.product ?? ''} {source.status} {source.tablesAnalyzed} tables{source.message ? `: ${source.message}` : ''}</li>
      {/each}
    </ul>
  </section>
{/if}

{#if problems.length}
  <section aria-label="Diagnostics">
    <h2>Diagnostics</h2>
    <ul>
      {#each problems as d, i (i)}
        <li>{d.level} {d.source}: {d.message}</li>
      {/each}
    </ul>
  </section>
{/if}
