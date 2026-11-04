<script lang="ts">
  import PanelShell from '../components/PanelShell.svelte';
  import { get } from '../lib/api';
  import { loader } from '../lib/load.svelte';
  import { openStream } from '../lib/sse';
  import type { Panel } from '../lib/types';

  type SecurityLogData = { name: string; value: string | null; masked: boolean; truncated: boolean };
  type SecurityLogEvent = {
    timestamp: string;
    principal: string | null;
    type: string;
    data: SecurityLogData[];
    traceId: string | null;
    requestId: string | null;
  };
  type SecurityLogsReport = {
    auditEventsPresent: boolean;
    unavailableReason: string | null;
    maxLogs: number;
    typeSummaries: { type: string; count: number }[];
    events: SecurityLogEvent[];
    page: { total: number; matched: number; returned: number };
  };

  let { panel }: { panel: Panel } = $props();
  let principal = $state('');
  let type = $state('');
  const report = loader(() => get<SecurityLogsReport>('security-logs', { principal, type, limit: 200 }));

  $effect(() => {
    void report.reload();
    const stream = openStream('api/security-logs/stream', { onUpdate: () => void report.reload() });
    return () => stream.close();
  });

  function filterBy(next: string) {
    type = type === next ? '' : next;
    void report.reload();
  }
</script>

<PanelShell
  title={panel.title}
  loading={report.loading}
  error={report.error}
  onretry={report.reload}
  count={report.data?.auditEventsPresent ? `${report.data.page.matched} of ${report.data.page.total} events · max ${report.data.maxLogs}` : null}
>
  {#snippet controls()}
    <form class="filters" onsubmit={(e) => { e.preventDefault(); void report.reload(); }}>
      <input type="text" aria-label="Principal" placeholder="Principal" bind:value={principal} />
      <input type="text" aria-label="Type" placeholder="Type" bind:value={type} />
      <button type="submit">Filter</button>
    </form>
  {/snippet}
  {#if report.data}
    {@const r = report.data}
    {#if !r.auditEventsPresent}
      <div class="empty"><p class="lead">Security logs are unavailable</p><p>{r.unavailableReason}</p></div>
    {:else}
      {#if r.unavailableReason}<p class="notice warn">{r.unavailableReason}</p>{/if}
      {#if r.typeSummaries.length}
        <p class="summaries">
          {#each r.typeSummaries as summary (summary.type)}
            <button class="tag" class:active={type === summary.type} onclick={() => filterBy(summary.type)}>{summary.type} · {summary.count}</button>
          {/each}
        </p>
      {/if}
      {#if r.events.length === 0}
        <div class="empty"><p class="lead">No security events yet</p><p>401 and 403 responses appear here, and events the app records with <code>sharpit.record_security_event()</code>.</p></div>
      {:else}
        <table>
          <thead><tr><th>Time</th><th>Type</th><th>Principal</th><th>Data</th><th>Request</th></tr></thead>
          <tbody>
            {#each r.events as event, i (`${event.timestamp}-${i}`)}
              <tr>
                <td class="mono">{event.timestamp}</td>
                <td><span class="tag" class:danger={event.type.endsWith('FAILURE')}>{event.type}</span></td>
                <td>{event.principal ?? '—'}</td>
                <td>
                  {#each event.data as row (row.name)}
                    <span class="sm line"><span class="muted">{row.name}</span> {row.value ?? '—'}{#if row.masked}<span class="tag warn">masked</span>{/if}{#if row.truncated}<span class="tag">truncated</span>{/if}</span>
                  {/each}
                </td>
                <td class="mono sm">{event.requestId ?? '—'}</td>
              </tr>
            {/each}
          </tbody>
        </table>
      {/if}
    {/if}
  {/if}
</PanelShell>

<style>
  .filters { display: flex; gap: var(--s2); }
  .summaries { display: flex; flex-wrap: wrap; gap: var(--s2); }
  .active { outline: 2px solid var(--rail); }
  td { height: auto; vertical-align: top; }
  .line { display: block; }
</style>
