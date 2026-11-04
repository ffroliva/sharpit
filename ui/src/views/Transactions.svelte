<script lang="ts">
  import PanelShell from '../components/PanelShell.svelte';
  import { errorText, get, post } from '../lib/api';
  import { loader } from '../lib/load.svelte';
  import { openStream } from '../lib/sse';
  import { clock } from '../lib/status';
  import type { Panel } from '../lib/types';

  type TransactionEntry = {
    id: number;
    methodName: string;
    propagation: string;
    status: string;
    startTimestamp: number;
    endTimestamp: number | null;
    durationMillis: number;
    parentId: number | null;
    thread: string | null;
    traceId: string | null;
    sqlStatementCount: number;
    connectionCount: number;
    readOnly: boolean | null;
    slow: boolean;
    connectionHeld: boolean;
    errorMessage: string | null;
  };

  type TransactionsReport = {
    available: boolean;
    unavailableReason: string | null;
    capturing: boolean;
    bufferSize: number;
    totalCaptured: number;
    stats: Record<string, number>;
    entries: TransactionEntry[];
    warnings: string[];
  };

  let { panel }: { panel: Panel } = $props();
  let failure = $state<string | null>(null);
  let acting = $state(false);
  const report = loader(() => get<TransactionsReport>('transactions'));
  const readOnly = $derived(panel.readOnly ? (panel.readOnlyReason ?? 'Read-only') : null);

  $effect(() => {
    void report.reload();
    const stream = openStream('api/transactions/stream', { onUpdate: () => void report.reload() });
    return () => stream.close();
  });

  async function act(path: string, body?: unknown) {
    if (acting || readOnly) return;
    acting = true;
    failure = null;
    try {
      await post(path, body);
      await report.reload();
    } catch (e) {
      failure = errorText(e);
    } finally {
      acting = false;
    }
  }
</script>

<PanelShell
  title={panel.title}
  loading={report.loading}
  error={report.error}
  onretry={report.reload}
  notice={readOnly}
  count={report.data?.available ? `${report.data.entries.length} of ${report.data.bufferSize} kept · ${report.data.totalCaptured} captured` : null}
>
  {#snippet controls()}
    {#if report.data?.available && !readOnly}
      <button onclick={() => act('transactions/recording', { enabled: !report.data!.capturing })} disabled={acting}>
        {report.data.capturing ? 'Pause' : 'Resume'}
      </button>
      <button onclick={() => act('transactions/clear')} disabled={acting}>Clear</button>
    {/if}
  {/snippet}
  {#if failure}<p class="notice danger" role="alert">{failure}</p>{/if}
  {#if report.data}
    {@const r = report.data}
    {#if !r.available}
      <div class="empty"><p class="lead">Transactions are unavailable</p><p>{r.unavailableReason}</p></div>
    {:else}
      {#each r.warnings as warning}<p class="notice warn">{warning}</p>{/each}
      {#if !r.capturing}<p class="notice warn">Recording is paused: new transactions are not captured until you resume.</p>{/if}
      {#if r.entries.length === 0}
        <div class="empty"><p class="lead">No transactions captured yet</p><p>Transactions appear after a registered SQLAlchemy engine commits or rolls back.</p></div>
      {:else}
        <table>
          <thead><tr><th>Started</th><th>Method</th><th>Status</th><th class="num">Duration</th><th class="num">SQL</th><th>Read only</th></tr></thead>
          <tbody>
            {#each r.entries as entry (entry.id)}
              <tr class:child={entry.parentId !== null} data-parent={entry.parentId ?? ''}>
                <td class="mono">{clock(entry.startTimestamp)}</td>
                <td><span class="method">{entry.methodName}</span><span class="sm muted">{entry.propagation}</span></td>
                <td>
                  <span class:danger={entry.status === 'ROLLED_BACK' || entry.status === 'UNKNOWN'} class="tag">{entry.status}</span>
                  {#if entry.slow}<span class="tag warn">slow</span>{/if}
                  {#if entry.connectionHeld}<span class="tag warn">held</span>{/if}
                  {#if entry.errorMessage}<span class="sm danger line">{entry.errorMessage}</span>{/if}
                </td>
                <td class="num">{entry.durationMillis} ms</td>
                <td class="num">{entry.sqlStatementCount}</td>
                <td>{entry.readOnly === null ? '—' : entry.readOnly ? 'Yes' : 'No'}</td>
              </tr>
            {/each}
          </tbody>
        </table>
      {/if}
    {/if}
  {/if}
</PanelShell>

<style>
  td { height: auto; vertical-align: top; }
  .method { display: block; }
  .child .method { padding-left: var(--s3); border-left: 2px solid var(--rail); }
  .line { display: block; }
</style>
