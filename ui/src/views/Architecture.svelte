<script lang="ts">
  import AdvisorPanel from '../components/AdvisorPanel.svelte';
  import { del, errorText, get, post } from '../lib/api';
  import { scannedWhen } from '../lib/format';
  import type { AdvisorReport, Panel, ViolationsPage } from '../lib/types';

  let { panel }: { panel: Panel } = $props();

  type ArchitectureReport = AdvisorReport & {
    basePackages: string[];
    classesAnalyzed: number;
    disclaimer: string;
  };
  let report = $state<ArchitectureReport | null>(null);
  let loadError = $state<string | null>(null);

  async function load() {
    try {
      report = await get<ArchitectureReport>('architecture');
      loadError = null;
    } catch (e) {
      loadError = errorText(e);
    }
  }
  load();

  const rule = (id: string) => `dismissed-rules/${encodeURIComponent(id)}`;
  const reload = async () => void (report = await get<ArchitectureReport>('architecture'));
</script>

<AdvisorPanel
  title={panel.title}
  {report}
  {loadError}
  readOnlyReason={panel.readOnly ? (panel.readOnlyReason ?? 'Read-only') : null}
  scanLabel={(phase) =>
    phase === 'scanning'
      ? 'Scanning…'
      : phase === 'results' || phase === 'failed'
        ? 'Scan again'
        : 'Run architecture checks'}
  onScan={async () => void (report = await post<ArchitectureReport>('architecture/scan'))}
  onDismiss={async (id) => {
    await post(rule(id));
    await reload();
  }}
  onRestore={async (id) => {
    await del(rule(id));
    await reload();
  }}
  onDismissFinding={async (fingerprint) => {
    await post(rule(fingerprint));
    await reload();
  }}
  loadDismissed={async () => (await get<{ dismissed: string[] }>('dismissed-rules')).dismissed}
  loadViolations={(id, offset) =>
    get<ViolationsPage>(`architecture/rules/${encodeURIComponent(id)}/violations`, {
      scanId: report?.violationDetails?.scanId,
      offset,
      limit: 100,
    })}
>
  {#snippet status(phase)}
    {#if phase === 'scanning'}Analysing application classes…
    {:else if phase === 'results' && report?.scan.scannedAt}{report.classesAnalyzed} classes analysed {scannedWhen(report.scan.scannedAt)}
    {/if}
  {/snippet}
</AdvisorPanel>
