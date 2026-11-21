<script lang="ts">
  import { tick } from 'svelte';
  import ServerTable from '../components/ServerTable.svelte';
  import { get } from '../lib/api';
  import { href } from '../lib/route';
  import { openStream } from '../lib/sse';
  import { clock, statusFamilyClass } from '../lib/status';
  import type { HttpExchange, HttpHeader } from '../lib/types';

  type RouteSummary = { id: string; method: string; route: string; routeSource: string; requests: number; status2xx: number; status3xx: number; status4xx: number; status5xx: number; statusOther: number; errorCount: number; timedRequests: number; avgDurationMs: number | null; p50DurationMs: number | null; p95DurationMs: number | null; p99DurationMs: number | null; maxDurationMs: number | null; totalDurationMs: number; shareOfRetainedTimePercent: number; topFor: string[] };
  type RouteReport = { available: boolean; unavailableReason: string | null; window: { retainedExchanges: number; bufferSize: number; totalDurationMs: number }; routes: RouteSummary[]; distinctRoutes: number; routesTruncated: boolean; topPerCriterion: number; notes: string[] };

  let { q = '' }: { q?: string } = $props();

  // svelte-ignore state_referenced_locally (the view is remounted when the route's q changes)
  let query = $state(q);
  let method = $state('');
  let statusClass = $state('');
  let openId = $state<string | null>(null);
  let table = $state<{ reload(): Promise<void> }>();
  let routeTable = $state<{ reload(): Promise<void> }>();
  let routeReport = $state<RouteReport | null>(null);
  let routeError = $state<string | null>(null);
  let rank = $state<'requests' | 'totalDurationMs' | 'p95DurationMs' | 'maxDurationMs' | 'errorCount'>('requests');
  let selectedRoute = $state<RouteSummary | null>(null);
  let drawer = $state<HTMLDialogElement>();
  let routeQuery = $state('');
  let opener: HTMLElement | null = null;
  let pointerStartedOnBackdrop = false;

  let routeRequest = 0;
  async function refreshRoutes() {
    const request = ++routeRequest;
    try {
      const value = await get<RouteReport>('http-exchanges/routes');
      if (request === routeRequest) {
        routeReport = value;
        routeError = null;
      }
    } catch (error) {
      if (request === routeRequest) routeError = String(error);
    }
  }

  $effect(() => {
    void refreshRoutes();
    const timer = setInterval(() => void refreshRoutes(), 30_000);
    return () => clearInterval(timer);
  });

  const metricCriteria = { requests: 'REQUESTS', totalDurationMs: 'TOTAL_DURATION', p95DurationMs: 'P95_DURATION', maxDurationMs: 'MAX_DURATION', errorCount: 'ERROR_COUNT' };
  const metricLabels = { requests: 'Requests', totalDurationMs: 'Total time', p95DurationMs: 'p95 time', maxDurationMs: 'Slowest request', errorCount: 'Errors' };
  const duration = (value: number | null) => value === null ? '—' : value < 1000 ? `${value} ms` : `${(value / 1000).toFixed(2)} s`;
  const average = (value: number | null) => value === null ? '—' : value < 1000 ? `${value.toFixed(1)} ms` : `${(value / 1000).toFixed(2)} s`;
  const scoredRoutes = $derived((routeReport?.routes ?? []).filter((route) => route.topFor?.includes(metricCriteria[rank])));
  const unmeasured = $derived((routeReport?.routes?.length ?? 0) > 0 && scoredRoutes.length === 0);
  const rankedRoutes = $derived([...(unmeasured ? (routeReport?.routes ?? []).filter((route) => route.topFor?.length) : scoredRoutes)].sort((a, b) => (b[rank] ?? 0) - (a[rank] ?? 0) || (a.id < b.id ? -1 : a.id > b.id ? 1 : 0)));
  async function openRoute(route: RouteSummary, event: MouseEvent) {
    selectedRoute = route;
    opener = event.currentTarget as HTMLElement;
    await tick();
    if (drawer && typeof drawer.showModal === 'function') drawer.showModal();
    else drawer?.setAttribute('open', '');
    drawer?.querySelector<HTMLButtonElement>('[aria-label="Close route exchanges"]')?.focus();
  }
  function closeRoute() {
    if (drawer?.open && typeof drawer.close === 'function') drawer.close();
    else drawer?.removeAttribute('open');
    selectedRoute = null;
    routeQuery = '';
    opener?.focus();
  }

  // exchanges have no stream of their own: the activity tick fires on every captured request
  $effect(() => {
    const stream = openStream('api/activity/stream', { onUpdate: () => { void table?.reload(); void routeTable?.reload(); void refreshRoutes(); } });
    return () => stream.close();
  });

  const headers = (list: HttpHeader[]) => list.map((h) => `${h.name}: ${h.values.join(', ')}${h.masked ? ' (masked)' : ''}`);
</script>

<div class="exchanges-view">
<section class="block routes" aria-labelledby="route-rankings-heading">
  <header class="panel-head">
    <h2 id="route-rankings-heading">Routes <span class="muted">{rankedRoutes.length}</span></h2>
    <button class="link" onclick={() => void refreshRoutes()}>Refresh rankings</button>
    <label for="route-ranking-metric">Rank by
      <select id="route-ranking-metric" aria-label="Rank routes by" bind:value={rank}>
        <option value="requests">Requests</option>
        <option value="totalDurationMs">Total time</option>
        <option value="p95DurationMs">p95 time</option>
        <option value="maxDurationMs">Slowest request</option>
        <option value="errorCount">Errors</option>
      </select>
    </label>
  </header>
  {#if routeError}<p class="notice warn" role="status">Route rankings are unavailable.</p>
  {:else if routeReport && !routeReport.available}<p class="muted">{routeReport.unavailableReason}</p>
  {:else if routeReport}
    <p class="muted">Top routes by {metricLabels[rank].toLowerCase()} over the retained window ({routeReport.window.retainedExchanges} retained exchanges · buffer {routeReport.window.bufferSize}).</p>
    {#if unmeasured}<p class="muted">No retained route records a non-zero {metricLabels[rank].toLowerCase()} in this window, so the routes are listed unranked.</p>{/if}
    {#if routeReport.routes.length === 0}<p class="muted">No application request is retained yet, so there is no route to rank. Send a request to the application and refresh this panel.</p>{/if}
    <table class="route-table" aria-label="Ranked HTTP routes">
      <thead><tr><th scope="col">Route</th><th scope="col">Requests</th><th scope="col">Status</th><th scope="col">Avg</th><th scope="col">p50</th><th scope="col">p95</th><th scope="col">p99</th><th scope="col">Max</th><th scope="col">Share</th><th scope="col"><span class="visually-hidden">Actions</span></th></tr></thead>
      <tbody>
        {#each rankedRoutes as route (route.id)}
          <tr data-route-id={route.id}>
            <td><span class="mono">{route.method} {route.route}</span><span class="muted sm">{route.routeSource === 'FRAMEWORK_TEMPLATE' ? 'template' : 'masked path'}</span></td>
            <td>{route.requests}<span class="muted sm">{route.timedRequests < route.requests ? `${route.timedRequests} timed` : ''}</span></td>
            <td class="statuses"><span>{route.status2xx} 2xx</span><span>{route.status3xx} 3xx</span><span>{route.status4xx} 4xx</span><span>{route.status5xx} 5xx</span><span>{route.statusOther} other</span></td>
            <td>{average(route.avgDurationMs)}</td><td>{duration(route.p50DurationMs)}</td><td>{duration(route.p95DurationMs)}</td><td>{duration(route.p99DurationMs)}</td><td>{duration(route.maxDurationMs)}</td><td>{route.shareOfRetainedTimePercent.toFixed(1)}%</td>
            <td><button class="link" aria-label="Show the retained exchanges of {route.id}" aria-haspopup="dialog" aria-pressed={selectedRoute?.id === route.id} onclick={(event) => openRoute(route, event)}>Exchanges</button></td>
          </tr>
        {:else}<tr><td colspan="10" class="muted">No route rankings available.</td></tr>{/each}
      </tbody>
    </table>
    {#if routeReport.routesTruncated}<p class="muted">Showing the top {routeReport.topPerCriterion} of {routeReport.distinctRoutes} retained routes; more routes are not shown.</p>{/if}
    {#if routeReport.notes.length}<details class="muted sm"><summary>How these figures are computed</summary><ul>{#each routeReport.notes as note}<li>{note}</li>{/each}</ul></details>{/if}
  {/if}
</section>

<dialog bind:this={drawer} class="route-drawer" aria-modal="true" aria-labelledby="route-drawer-title" aria-describedby="route-drawer-route" onkeydown={(event) => event.key === 'Escape' && closeRoute()} onpointerdown={(event) => (pointerStartedOnBackdrop = event.target === drawer)} onclick={(event) => { if (event.target === drawer && pointerStartedOnBackdrop) closeRoute(); pointerStartedOnBackdrop = false; }} oncancel={(event) => { event.preventDefault(); closeRoute(); }} onclose={() => { selectedRoute = null; routeQuery = ''; opener?.focus(); }}>
  {#if selectedRoute}
    <header class="panel-head"><h2 id="route-drawer-title">Route exchanges</h2><p id="route-drawer-route" class="mono">{selectedRoute.method} {selectedRoute.route}</p><button class="link" aria-label="Close route exchanges" onclick={closeRoute}>Close</button></header>
    <ServerTable bind:this={routeTable} title="Route exchanges" path="http-exchanges" key="route-exchanges" params={{ route: selectedRoute.id, method: '', statusClass }} bind:q={routeQuery} placeholder="Filter route exchanges" noun="requests" columns={7} cols={['5.5rem', '5rem', '', '4.5rem', '5.5rem', '5.5rem', '6rem']}>
      {#snippet controls()}{/snippet}
      {#snippet head()}<tr><th scope="col">Time</th><th scope="col">Method</th><th scope="col">Path</th><th scope="col">Status</th><th scope="col">Duration</th><th scope="col">Size</th><th scope="col"><span class="visually-hidden">Actions</span></th></tr>{/snippet}
      {#snippet body(items: readonly HttpExchange[])}
        {#each items as x (x.id)}<tr><td class="mono">{clock(x.timestamp)}</td><td>{x.method}</td><td class="mono wrap">{x.uri}</td><td>{x.status}</td><td>{x.durationMs} ms</td><td>{x.responseSizeBytes ?? '—'}</td><td><a href={href('activity', x.id)}>Activity</a></td></tr>{/each}
      {/snippet}
    </ServerTable>
  {/if}
</dialog>

<ServerTable
  bind:this={table}
  title="HTTP Exchanges"
  path="http-exchanges"
  key="exchanges"
  params={{ method, statusClass }}
  bind:q={query}
  placeholder="Filter by path, query or trace id"
  noun="requests"
  columns={7}
  cols={['5.5rem', '5rem', '', '4.5rem', '5.5rem', '5.5rem', '6rem']}
>
  {#snippet controls()}
    <select aria-label="Method" bind:value={method}>
      <option value="">All methods</option>
      {#each ['GET', 'POST', 'PUT', 'PATCH', 'DELETE', 'HEAD', 'OPTIONS'] as m}<option>{m}</option>{/each}
    </select>
    <select aria-label="Status class" bind:value={statusClass}>
      <option value="">All statuses</option>
      {#each ['2xx', '3xx', '4xx', '5xx'] as s}<option>{s}</option>{/each}
    </select>
  {/snippet}
  {#snippet head()}
    <tr><th>Time</th><th>Method</th><th>Path</th><th>Status</th><th class="num">Duration</th><th class="num">Size</th><th></th></tr>
  {/snippet}
  {#snippet body(items: readonly HttpExchange[])}
    {#if items.length === 0}
      <tr><td colspan="7" class="muted">No requests captured yet. Call your app, then come back.</td></tr>
    {/if}
    {#each items as x (x.id)}
      <tr>
        <td class="mono">{clock(x.timestamp)}</td>
        <td class="mono">{x.method}</td>
        <td class="mono wrap">{x.uri}</td>
        <td class="mono {statusFamilyClass(x.status)}">{x.status}</td>
        <td class="num">{x.durationMs} ms</td>
        <td class="num">{x.responseSizeBytes ?? '—'}</td>
        <td><button class="link" aria-label="Details for {x.method} {x.uri}" aria-expanded={openId === x.id} onclick={() => (openId = openId === x.id ? null : x.id)}>Details</button></td>
      </tr>
      {#if openId === x.id}
        <tr class="detail">
          <td colspan="7">
            <p class="sm">
              <a href={href('activity', x.id)}>Open in Activity</a> ·
              <a href={href('http-probe', `${x.method} ${x.path}`)}>Replay in Probe</a>
              {#if x.principal}· user {x.principal}{/if}{#if x.remoteAddress}· from {x.remoteAddress}{/if}
            </p>
            <div class="cols">
              <div><strong>Request headers</strong>{#each headers(x.requestHeaders) as line}<div class="mono sm wrap">{line}</div>{:else}<div class="muted sm">none shown</div>{/each}</div>
              <div><strong>Response headers</strong>{#each headers(x.responseHeaders) as line}<div class="mono sm wrap">{line}</div>{:else}<div class="muted sm">none shown</div>{/each}</div>
            </div>
          </td>
        </tr>
      {/if}
    {/each}
  {/snippet}
</ServerTable>
</div>

<style>
  .exchanges-view { height: 100%; min-height: 0; display: grid; grid-template-rows: minmax(0, 42%) minmax(0, 1fr); }
  .routes { min-height: 0; padding: var(--s4); overflow: auto; }
  .route-table { width: 100%; }
  .statuses span { display: block; white-space: nowrap; }
  .route-table td:first-child > * { display: block; }
  .route-drawer { position: fixed; inset: 0 0 0 auto; margin: 0; width: min(72rem, 100%); max-width: 100%; height: 100dvh; max-height: 100dvh; border: 0; padding: var(--s4); background: var(--bg); color: var(--ink); overflow: auto; }
  .route-drawer::backdrop { background: rgb(0 0 0 / 40%); }
  @media (max-width: 720px) { .route-table { display: block; overflow-x: auto; } .route-drawer { padding: var(--s2); } }
  tr.detail td { height: auto; padding: var(--s2) var(--s4); background: var(--rail); }
  .cols { display: grid; grid-template-columns: 1fr 1fr; gap: var(--s4); }
  .wrap { overflow-wrap: anywhere; }
</style>
