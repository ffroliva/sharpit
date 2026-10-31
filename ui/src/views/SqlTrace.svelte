<script lang="ts">
  import PanelShell from '../components/PanelShell.svelte';
  import { errorText, get, post } from '../lib/api';
  import { loader } from '../lib/load.svelte';
  import { href } from '../lib/route';
  import { openStream } from '../lib/sse';
  import { clock } from '../lib/status';
  import type { Panel, SqlTraceReport } from '../lib/types';

  let { panel }: { panel: Panel } = $props();

  let tab = $state<'recent' | 'top'>('recent');
  let failure = $state<string | null>(null);
  let acting = $state(false);
  const report = loader(() => get<SqlTraceReport>('sql-trace'));
  $effect(() => {
    void report.reload();
    const stream = openStream('api/sql-trace/stream', { onUpdate: () => void report.reload() });
    return () => stream.close();
  });

  const readOnly = $derived(panel.readOnly ? (panel.readOnlyReason ?? 'Read-only') : null);
  /** Pause/Resume and Clear answer the new report; the next reload shows it. */
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

  const maxMs = $derived(Math.max(1, ...(report.data?.entries ?? []).map((e) => e.durationMillis)));
  const pct = (ms: number) => `${Math.max(2, Math.round((ms / maxMs) * 100))}%`;
</script>

<PanelShell
  title="SQL Trace"
  loading={report.loading}
  error={report.error}
  onretry={report.reload}
  notice={readOnly}
  count={report.data?.available ? `${report.data.entries.length} of ${report.data.bufferSize} kept · ${report.data.totalCaptured} captured` : null}
>
  {#snippet controls()}
    {#if report.data?.available}
      <button class="push" onclick={() => act('sql-trace/recording', { enabled: !report.data!.capturing })} disabled={!!readOnly || acting} title={readOnly ?? undefined}>
        {report.data.capturing ? 'Pause' : 'Resume'}
      </button>
      <button onclick={() => act('sql-trace/clear')} disabled={!!readOnly || acting} title={readOnly ?? undefined}>Clear</button>
    {/if}
  {/snippet}
  {#if failure}<p class="notice danger" role="alert">{failure}</p>{/if}
  {#if report.data}
    {@const r = report.data}
    {#if !r.available}
      <div class="empty"><p class="lead">SQL Trace is off</p><p>{r.unavailableReason}</p></div>
    {:else}
      {#each r.warnings as w}<p class="notice warn">{w}</p>{/each}
      {#if !r.capturing}<p class="notice warn">Recording is paused: new statements are not captured until you resume.</p>{/if}
      <div role="tablist" class="tabs" aria-label="SQL Trace view">
        <button role="tab" id="sql-tab-recent" aria-controls="sql-panel" aria-selected={tab === 'recent'} onclick={() => (tab = 'recent')}>Recent ({r.entries.length})</button>
        <button role="tab" id="sql-tab-top" aria-controls="sql-panel" aria-selected={tab === 'top'} onclick={() => (tab = 'top')}>Top statements ({r.topStatements.length})</button>
      </div>
      <div id="sql-panel" role="tabpanel" aria-labelledby={tab === 'recent' ? 'sql-tab-recent' : 'sql-tab-top'}>
        {#if r.entries.length === 0 && r.topStatements.length === 0}
          <div class="empty">
            <p class="lead">No SQL captured yet</p>
            <p>Statements show here once {r.dataSources.length ? r.dataSources.join(', ') : 'a registered engine'} runs SQL. Call a route that queries the database.</p>
          </div>
        {:else if tab === 'recent'}
          <table>
            <thead><tr><th>Time</th><th>Statement</th><th class="num">Duration</th><th class="num">Rows</th><th>Call site</th></tr></thead>
            <tbody>
              {#each r.entries as e (e.id)}
                <tr>
                  <td class="mono">{clock(e.timestamp)}</td>
                  <td>
                    <span class="mono sql">{e.sql}</span>
                    <span class="sm muted">{e.category} · {e.statementType}</span>
                    {#if e.slow}<span class="tag warn">slow</span>{/if}
                    {#if !e.success}<span class="tag danger">failed</span>{/if}
                    {#if e.errorMessage}<span class="sm danger line">{e.errorMessage}</span>{/if}
                  </td>
                  <td class="num">
                    {e.durationMillis} ms
                    <span class="bar" aria-hidden="true"><span class={e.slow ? 'slow' : ''} style:width={pct(e.durationMillis)}></span></span>
                  </td>
                  <td class="num">{e.affectedRows ?? '—'}</td>
                  <td class="sm">
                    <span class="mono">{e.callSite ?? '—'}</span>
                    {#if e.traceId}<a class="line" href={href('activity', e.traceId)}>Open request</a>{/if}
                  </td>
                </tr>
              {/each}
            </tbody>
          </table>
        {:else}
          <table>
            <thead><tr><th>Normalised statement</th><th class="num">Executions</th><th class="num">Total</th><th class="num">Max</th><th>Call sites</th></tr></thead>
            <tbody>
              {#each r.topStatements as g (g.sql)}
                <tr>
                  <td>
                    <span class="mono sql">{g.sql}</span>
                    {#if g.potentialNPlusOne}<span class="tag danger" title="The same SELECT ran many times: likely a query in a loop">N+1</span>{/if}
                  </td>
                  <td class="num">{g.executions}</td>
                  <td class="num">{g.totalDurationMillis} ms</td>
                  <td class="num">{g.maxDurationMillis} ms</td>
                  <td class="mono sm">{g.callSites.join(', ') || '—'}</td>
                </tr>
              {/each}
            </tbody>
          </table>
        {/if}
      </div>
    {/if}
  {/if}
</PanelShell>

<style>
  .push { margin-left: auto; }
  .tabs { display: flex; gap: var(--s1); padding: var(--s2) var(--s4) 0; }
  .tabs button[aria-selected='true'] { border-color: var(--accent); }
  td { height: auto; vertical-align: top; }
  .sql { display: block; white-space: pre-wrap; overflow-wrap: anywhere; }
  .line { display: block; }
  .bar { display: block; height: 4px; margin-top: 2px; background: var(--rail); border-radius: 2px; }
  .bar span { display: block; height: 100%; background: var(--muted); border-radius: 2px; }
  .bar span.slow { background: var(--warn); }
</style>
