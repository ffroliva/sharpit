<script lang="ts">
  import PanelShell from '../components/PanelShell.svelte';
  import { get } from '../lib/api';
  import { loader } from '../lib/load.svelte';
  import { href } from '../lib/route';
  import type { Panel } from '../lib/types';

  let { panel }: { panel: Panel } = $props();

  type NPlusOne = {
    method: string | null; route: string | null; routePath: string | null; routeReason: string | null;
    sql: string; executionsPerRequest: number; requests: number; threshold: number;
  };
  type Report = {
    available: boolean; enableAvailable: boolean; unavailableReason: string | null;
    statistics: Record<string, number | boolean | string | null | unknown[]> & { nPlusOne: NPlusOne[]; nPlusOneWindow: string; warnings?: string[] };
  };

  // same text as NULL_REASON in engine/collectors/sqlastats.py and nullable.json
  const NOT_MEASURED = 'SQLAlchemy reports SQL statements, not ORM session or entity operations (transactions live in the transactions panel)';
  const report = loader(() => get<Report>('sqlalchemy-statistics'));
  $effect(() => void report.reload());

  const MEASURED = [
    ['statementCount', 'Statements'], ['queryExecutionCount', 'SELECT statements'], ['queryExecutionMaxTime', 'Slowest (ms)'],
  ] as const;
  const UNMEASURED = [
    ['sessionOpenCount', 'Sessions opened'], ['sessionCloseCount', 'Sessions closed'], ['flushCount', 'Flushes'],
    ['connectCount', 'Connections'], ['transactionCount', 'Transactions'], ['entityLoadCount', 'Entities loaded'],
    ['entityInsertCount', 'Entities inserted'], ['entityUpdateCount', 'Entities updated'],
    ['entityDeleteCount', 'Entities deleted'], ['collectionLoadCount', 'Collections loaded'],
  ] as const;
</script>

<PanelShell title={panel.title} loading={report.loading} error={report.error} onretry={report.reload}>
  {#if report.data}
    {#if !report.data.available}
      <div class="empty"><p class="lead">Statistics unavailable</p><p>{report.data.unavailableReason}</p></div>
    {:else}
      {@const s = report.data.statistics}
      {#each s.warnings ?? [] as warning (warning)}<p class="warn">{warning}</p>{/each}
      <section class="block">
        <h2>Statistics</h2>
        <dl class="facts statistics">
          {#each MEASURED as [key, label] (key)}
            <dt>{label}</dt><dd class="num"><strong>{s[key]}</strong></dd>
          {/each}
          {#each UNMEASURED as [key, label] (key)}
            <dt>{label}</dt>
            <dd class="num muted status" title={NOT_MEASURED}>{s[key] === null ? 'not measured' : s[key]}</dd>
          {/each}
        </dl>
      </section>
      {#if s.queryExecutionMaxTimeQueryString}
        <p class="sm muted">Slowest statement</p>
        <pre class="mono">{s.queryExecutionMaxTimeQueryString}</pre>
      {/if}
      <section class="block">
        <h2>N+1 candidates</h2>
        <p class="sm muted">{s.nPlusOneWindow}</p>
        {#if s.nPlusOne.length === 0}
          <p class="muted">None: no request ran one SELECT shape repeatedly.</p>
        {:else}
          <table>
            <thead><tr><th>Route</th><th>Executions per request</th><th>Requests</th><th>Statement</th></tr></thead>
            <tbody>
              {#each s.nPlusOne as n (n.method + ':' + n.route + ':' + n.sql)}
                <tr>
                  <td>
                    {#if n.route}
                      <a href={href('http-exchanges', n.routePath ?? '')}>{n.method} {n.route}</a>
                    {:else}
                      <span class="muted" title={n.routeReason}>unknown route</span>
                    {/if}
                  </td>
                  <td class="num">{n.executionsPerRequest}</td>
                  <td class="num">{n.requests}</td>
                  <td class="mono">{n.sql}</td>
                </tr>
              {/each}
            </tbody>
          </table>
        {/if}
      </section>
    {/if}
  {/if}
</PanelShell>

<style>
  section.block > p { margin: 0; padding: 0 var(--s4) var(--s2); }
</style>
