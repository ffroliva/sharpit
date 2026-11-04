<script lang="ts">
  import AdvisorPanel from '../components/AdvisorPanel.svelte';
  import { del, errorText, get, post } from '../lib/api';
  import { scannedWhen } from '../lib/format';
  import type { AdvisorReport, Panel, ViolationsPage } from '../lib/types';

  let { panel }: { panel: Panel } = $props();

  type SecurityReport = AdvisorReport & { filterChainsAnalyzed: number; disclaimer: string };
  let report = $state<SecurityReport | null>(null);
  let loadError = $state<string | null>(null);

  // GET returns the last scan (or NOT_SCANNED); only the button scans
  async function load() {
    try {
      report = await get<SecurityReport>('security');
      loadError = null;
    } catch (e) {
      loadError = errorText(e);
    }
  }
  load();

  const rule = (id: string) => `dismissed-rules/${encodeURIComponent(id)}`;
  const reload = async () => void (report = await get<SecurityReport>('security')); // a failed reload keeps the old report
  const stacks = (n: number) => `${n} middleware stack${n === 1 ? '' : 's'}`;
</script>

<AdvisorPanel
  title={panel.title}
  {report}
  {loadError}
  onretry={load}
  readOnlyReason={panel.readOnly ? (panel.readOnlyReason ?? 'Read-only') : null}
  scanLabel={(phase) => (phase === 'scanning' ? 'Scanning…' : phase === 'results' || phase === 'failed' ? 'Scan again' : 'Run security checks')}
  onScan={async () => void (report = await post<SecurityReport>('security/scan'))}
  onDismiss={async (id) => { await post(rule(id)); await reload(); }}
  onRestore={async (id) => { await del(rule(id)); await reload(); }}
  onDismissFinding={async (fingerprint) => { await post(rule(fingerprint)); await reload(); }}
  loadDismissed={async () => (await get<{ dismissed: string[] }>('dismissed-rules')).dismissed}
  loadViolations={(id, offset) =>
    get<ViolationsPage>(`security/rules/${encodeURIComponent(id)}/violations`, { scanId: report?.violationDetails?.scanId, offset, limit: 100 })}
>
  {#snippet status(phase)}
    {#if phase === 'scanning'}Reading the middleware stacks and routes…
    {:else if phase === 'results' && report?.scan.scannedAt}{stacks(report.filterChainsAnalyzed)} scanned {scannedWhen(report.scan.scannedAt)}
    {/if}
  {/snippet}
</AdvisorPanel>
