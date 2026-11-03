<script lang="ts">
  // The FastAPI advisor (BootUI Spring.vue, WAVE-B §7): the shared AdvisorPanel over api/fastapi.
  import AdvisorPanel from '../components/AdvisorPanel.svelte';
  import { del, errorText, get, post } from '../lib/api';
  import { scannedWhen } from '../lib/format';
  import type { AdvisorReport, Panel, ViolationsPage } from '../lib/types';

  let { panel }: { panel: Panel } = $props();

  type FastapiReport = AdvisorReport & { componentsAnalyzed: number; inspected: string[]; disclaimer: string };
  let report = $state<FastapiReport | null>(null);
  let loadError = $state<string | null>(null);

  // GET returns the last scan (or NOT_SCANNED); only the button scans
  async function load() {
    try {
      report = await get<FastapiReport>('fastapi');
      loadError = null;
    } catch (e) {
      loadError = errorText(e);
    }
  }
  load();

  const rule = (id: string) => `dismissed-rules/${encodeURIComponent(id)}`;
  const reload = async () => void (report = await get<FastapiReport>('fastapi')); // a failed reload keeps the old report
</script>

<AdvisorPanel
  title={panel.title}
  {report}
  {loadError}
  readOnlyReason={panel.readOnly ? (panel.readOnlyReason ?? 'Read-only') : null}
  scanLabel={(phase) => (phase === 'scanning' ? 'Scanning…' : phase === 'results' || phase === 'failed' ? 'Scan again' : 'Run FastAPI checks')}
  onScan={async () => void (report = await post<FastapiReport>('fastapi/scan'))}
  onDismiss={async (id) => { await post(rule(id)); await reload(); }}
  onRestore={async (id) => { await del(rule(id)); await reload(); }}
  onDismissFinding={async (fingerprint) => { await post(rule(fingerprint)); await reload(); }}
  loadDismissed={async () => (await get<{ dismissed: string[] }>('dismissed-rules')).dismissed}
  loadViolations={(id, offset) =>
    get<ViolationsPage>(`fastapi/rules/${encodeURIComponent(id)}/violations`, { scanId: report?.violationDetails?.scanId, offset, limit: 100 })}
>
  {#snippet status(phase)}
    {#if phase === 'scanning'}Reading route handlers and source…
    {:else if phase === 'results' && report?.scan.scannedAt}{report.componentsAnalyzed} route handlers analysed {scannedWhen(report.scan.scannedAt)}
    {/if}
  {/snippet}
</AdvisorPanel>
