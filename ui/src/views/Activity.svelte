<script lang="ts">
  import PanelShell from '../components/PanelShell.svelte';
  import { errorText, get } from '../lib/api';
  import { loader } from '../lib/load.svelte';
  import { openStream } from '../lib/sse';
  import { clock } from '../lib/status';
  import type { ActivityEntry, ActivityReport, RequestProfile } from '../lib/types';

  let { q = '' }: { q?: string } = $props();

  // svelte-ignore state_referenced_locally (the view is remounted when the route's q changes)
  let query = $state(q);
  let type = $state('');
  let severity = $state('');
  let profile = $state<RequestProfile | null>(null);
  let profileError = $state<string | null>(null);

  const report = loader(() => get<ActivityReport>('activity', { type, severity, q: query }));
  $effect(() => {
    void report.reload();
  });
  $effect(() => {
    const stream = openStream('api/activity/stream', { onUpdate: () => void report.reload() });
    return () => stream.close();
  });

  async function open(entry: ActivityEntry) {
    profile = null;
    profileError = null;
    try {
      profile = await get<RequestProfile>(`activity/request/${encodeURIComponent(entry.id)}`);
    } catch (e) {
      profileError = errorText(e);
    }
  }
  const close = () => ((profile = null), (profileError = null));
  const kpi = (v: number | string | null | undefined, unit = '') => (v === null || v === undefined ? '—' : `${v}${unit}`);
  const sevClass = { ERROR: 'danger', WARN: 'warn', SLOW: 'warn', OK: 'muted' } as const;
  const groups = $derived([...(profile?.sqlGroups ?? [])].sort((a, b) => Number(b.potentialNPlusOne) - Number(a.potentialNPlusOne)));
</script>

<PanelShell title="Live Activity" loading={report.loading} error={report.error} onretry={report.reload} count={report.data ? `${report.data.entries.length} entries` : null}>
  {#snippet controls()}
    <div class="grow">
      <label class="visually-hidden" for="activity-q">Filter activity</label>
      <input id="activity-q" class="panel-filter" type="search" placeholder="Filter by path, SQL or request id" bind:value={query} autocomplete="off" spellcheck="false" />
    </div>
    <select aria-label="Type" bind:value={type}>
      <option value="">All types</option><option>REQUEST</option><option>SQL</option><option>EXCEPTION</option>
    </select>
    <select aria-label="Severity" bind:value={severity}>
      <option value="">All severities</option><option>OK</option><option>WARN</option><option>SLOW</option><option>ERROR</option>
    </select>
  {/snippet}
  {#if report.data}
    {@const r = report.data}
    <p class="kpis sm muted">
      {kpi(r.kpis.requestsPerMinute)} requests/min · {kpi(r.kpis.errorRatePercent, '%')} errors · p50 {kpi(r.kpis.p50LatencyMs, ' ms')} · p95
      {kpi(r.kpis.p95LatencyMs, ' ms')} · slowest {kpi(r.kpis.slowestEndpoint)} {kpi(r.kpis.slowestEndpointMs, ' ms')}
      {#if r.sources.length}· sources: {r.sources.join(', ')}{/if}
    </p>
    {#each r.warnings as w}<p class="notice warn">{w}</p>{/each}
    {#if profile || profileError}
      <section class="block profile" aria-label="Request profile">
        <h2>{profile?.request?.summary ?? 'Request profile'} <button class="link" onclick={close}>Close</button></h2>
        {#if profileError}<p class="danger" role="alert">{profileError}</p>
        {:else if profile && !profile.available}<p class="muted">{profile.unavailableReason ?? 'No profile available'}</p>
        {:else if profile}
          {#if profile.timing}
            {@const t = profile.timing}
            <p class="sm">SQL {t.sqlMs} ms of {t.totalMs} ms ({t.sqlCount} statements{t.sqlPercent === null ? '' : `, ${t.sqlPercent}%`})</p>
            <div class="bar" role="img" aria-label="SQL {t.sqlMs} ms of {t.totalMs} ms"><span style:width="{Math.min(100, t.sqlPercent ?? 0)}%"></span></div>
          {/if}
          {#each groups as g}
            <div class="group">
              <code class="sql">{g.sql}</code>
              <span class="sm muted">{g.executions} executions · {g.totalDurationMillis} ms total · max {g.maxDurationMillis} ms</span>
              {#if g.potentialNPlusOne}<span class="tag warn">potential N+1</span>{/if}
              {#each g.callSites as site}<span class="sm muted mono">{site}</span>{/each}
            </div>
          {/each}
          {#each profile.exceptions as x}<p class="danger sm">{x.exceptionClassName}: {x.message}</p>{/each}
          {#each profile.notes as n}<p class="sm muted">{n}</p>{/each}
        {/if}
      </section>
    {/if}
    {#if r.entries.length === 0}
      <div class="empty"><p class="lead">No requests captured yet</p><p>Call your app, then come back. This feed updates by itself.</p></div>
    {:else}
      <table aria-label="Activity">
        <thead><tr><th>Time</th><th>Type</th><th>Severity</th><th>Summary</th><th class="num">Duration</th></tr></thead>
        <tbody>
          {#each r.entries as e (e.id)}
            <tr>
              <td class="mono">{clock(e.timestamp)}</td>
              <td>{e.type}</td>
              <td class={sevClass[e.severity]}>{e.severity.toLowerCase()}</td>
              <td class="mono shrink">
                {#if e.profileable}<button class="link" onclick={() => open(e)}>{e.summary}</button>{:else}{e.summary}{/if}
                {#if e.sqlNPlusOneSuspected}<span class="tag warn">N+1</span>{/if}
              </td>
              <td class="num">{e.durationMs === null ? '' : `${e.durationMs} ms`}</td>
            </tr>
          {/each}
        </tbody>
      </table>
    {/if}
  {/if}
</PanelShell>

<style>
  .kpis, .group { padding: var(--s2) var(--s4); margin: 0; }
  .group { display: flex; flex-wrap: wrap; gap: var(--s2); align-items: baseline; border-top: 1px solid var(--line); }
  .sql { overflow-wrap: anywhere; flex-basis: 100%; }
  .bar { height: 6px; margin: 0 var(--s4) var(--s2); background: var(--line); border-radius: 2px; overflow: hidden; }
  .bar span { display: block; height: 100%; background: var(--accent); }
  .profile h2 button { margin-left: var(--s2); font-weight: 400; }
</style>
