<script lang="ts">
  import PanelShell from '../components/PanelShell.svelte';
  import { get } from '../lib/api';
  import { loader } from '../lib/load.svelte';
  import type { PoolSnapshot, PoolsReport } from '../lib/types';

  const POLL_MS = 2000;
  const HISTORY = 60; // snapshots kept per pool for the sparkline (spec 7.7), in memory only

  const report = loader(() => get<PoolsReport>('database-connection-pools/pools'));
  let live = $state<Record<string, PoolSnapshot[]>>({});

  async function poll() {
    if (document.hidden) return; // only the visible panel polls
    for (const p of report.data?.pools ?? []) {
      if (!p.available) continue;
      try {
        const snap = await get<PoolSnapshot>(`database-connection-pools/pools/${encodeURIComponent(p.poolName)}/snapshot`);
        live[p.poolName] = [...(live[p.poolName] ?? []), snap].slice(-HISTORY);
      } catch {
        // a pool that went away keeps its last numbers; the next full load drops it
      }
    }
  }
  $effect(() => {
    void report.reload();
    const timer = setInterval(() => void poll(), POLL_MS);
    return () => clearInterval(timer);
  });

  const latest = (name: string, first: PoolSnapshot | null) => live[name]?.at(-1) ?? first;
  /** A polyline of the active count over the kept snapshots, scaled to the pool's max (or the highest seen). */
  function spark(name: string, max: number | null): string {
    const points = live[name] ?? [];
    if (points.length < 2) return '';
    const top = Math.max(1, max ?? 0, ...points.map((s) => s.total));
    return points.map((s, i) => `${(i / (HISTORY - 1)) * 100},${20 - (s.active / top) * 20}`).join(' ');
  }
  const ms = (v: number | null) => (v === null ? '—' : v >= 1000 ? `${v / 1000} s` : `${v} ms`);
</script>

<PanelShell
  title="Database Connection Pools"
  loading={report.loading}
  error={report.error}
  onretry={report.reload}
  count={report.data ? `${report.data.total} ${report.data.total === 1 ? 'pool' : 'pools'}` : null}
>
  {#if report.data}
    {#if report.data.pools.length === 0}
      <div class="empty">
        <p class="lead">No database engine registered</p>
        <p>Pass your SQLAlchemy engines to sharpit, or let the app run a query first:</p>
        <pre class="mono">sharpit.install(app, engines=[engine])</pre>
      </div>
    {/if}
    <div class="cards">
      {#each report.data.pools as p (p.poolName)}
        {@const s = latest(p.poolName, p.snapshot)}
        <section class="card" aria-label={p.poolName}>
          <h2 class="mono">{p.poolName}</h2>
          <p class="sm muted">{p.driverClassName}{#if p.username} · user {p.username}{/if}</p>
          {#if !p.available}
            <p class="muted">{p.unavailableReason}</p>
          {:else if s}
            <p class="gauge">
              <span><strong>{s.active}</strong> active</span>
              <span><strong>{s.idle}</strong> idle</span>
              <span class="muted">max {p.maximumPoolSize ?? 'unlimited'}</span>
            </p>
            {#if p.maximumPoolSize}
              <meter min="0" max={p.maximumPoolSize} value={s.active} aria-label="{p.poolName}: {s.active} of {p.maximumPoolSize} connections checked out"></meter>
            {/if}
            {#if spark(p.poolName, p.maximumPoolSize)}
              <svg class="spark" viewBox="0 0 100 20" preserveAspectRatio="none" role="img" aria-label="Active connections over the last {live[p.poolName]?.length} polls">
                <polyline points={spark(p.poolName, p.maximumPoolSize)} />
              </svg>
            {/if}
            <dl class="sm">
              <dt>Checkout timeout</dt><dd>{ms(p.connectionTimeoutMs)}</dd>
              <dt>Recycle after</dt><dd>{ms(p.maxLifetimeMs)}</dd>
              <dt>Autocommit</dt><dd>{p.autoCommit ? 'yes' : 'no'}</dd>
            </dl>
          {/if}
        </section>
      {/each}
    </div>
  {/if}
</PanelShell>

<style>
  .cards { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: var(--s4); padding: var(--s4); }
  .card { border: 1px solid var(--line); border-radius: var(--radius); padding: var(--s3) var(--s4); }
  .card h2 { margin: 0; font-size: 13px; overflow-wrap: anywhere; }
  .card p { margin: var(--s1) 0; }
  .gauge { display: flex; gap: var(--s4); align-items: baseline; }
  .gauge strong { font-size: 18px; }
  meter { width: 100%; }
  .spark { width: 100%; height: 24px; }
  .spark polyline { fill: none; stroke: var(--accent); stroke-width: 1; vector-effect: non-scaling-stroke; }
  dl { display: grid; grid-template-columns: auto 1fr; gap: 0 var(--s3); margin: var(--s2) 0 0; }
  dd { margin: 0; }
  pre { margin: 0; }
</style>
