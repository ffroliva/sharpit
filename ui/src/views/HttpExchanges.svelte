<script lang="ts">
  import ServerTable from '../components/ServerTable.svelte';
  import { get } from '../lib/api';
  import { href } from '../lib/route';
  import { openStream } from '../lib/sse';
  import { clock, statusFamilyClass } from '../lib/status';
  import type { HttpExchange, HttpHeader } from '../lib/types';

  type RouteSummary = { id: string; method: string; route: string; routeSource: string; requests: number; errorCount: number; timedRequests: number; totalDurationMs: number; p95DurationMs: number | null; topFor: string[] };
  type RouteReport = { available: boolean; unavailableReason: string | null; window: { retainedExchanges: number; bufferSize: number; totalDurationMs: number }; routes: RouteSummary[]; distinctRoutes: number; routesTruncated: boolean; topPerCriterion: number; notes: string[] };

  let { q = '' }: { q?: string } = $props();

  // svelte-ignore state_referenced_locally (the view is remounted when the route's q changes)
  let query = $state(q);
  let method = $state('');
  let statusClass = $state('');
  let openId = $state<string | null>(null);
  let table = $state<{ reload(): Promise<void> }>();
  let routeReport = $state<RouteReport | null>(null);
  let routeError = $state<string | null>(null);
  let rank = $state<'requests' | 'totalDurationMs' | 'p95DurationMs'>('requests');
  let selectedRoute = $state<RouteSummary | null>(null);
  let drawer = $state<HTMLDialogElement>();
  let routeQuery = $state('');
  let opener: HTMLElement | null = null;

  $effect(() => {
    let active = true;
    get<RouteReport>('http-exchanges/routes').then((value) => { if (active) routeReport = value; }).catch((error) => { if (active) routeError = String(error); });
    return () => { active = false; };
  });

  const rankedRoutes = $derived([...(routeReport?.routes ?? [])].sort((a, b) => (b[rank] ?? 0) - (a[rank] ?? 0) || a.id.localeCompare(b.id)));
  function openRoute(route: RouteSummary, event: MouseEvent) {
    selectedRoute = route;
    opener = event.currentTarget as HTMLElement;
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
    const stream = openStream('api/activity/stream', { onUpdate: () => void table?.reload() });
    return () => stream.close();
  });

  const headers = (list: HttpHeader[]) => list.map((h) => `${h.name}: ${h.values.join(', ')}${h.masked ? ' (masked)' : ''}`);
</script>

<section class="block routes" aria-label="HTTP route rankings">
  <header class="panel-head">
    <h2>Route rankings</h2>
    <label>Rank routes by
      <select aria-label="Rank routes by" bind:value={rank}>
        <option value="requests">Requests</option>
        <option value="totalDurationMs">Total duration</option>
        <option value="p95DurationMs">p95 duration</option>
      </select>
    </label>
  </header>
  {#if routeError}<p class="notice warn" role="status">Route rankings are unavailable.</p>
  {:else if routeReport && !routeReport.available}<p class="muted">{routeReport.unavailableReason}</p>
  {:else if routeReport}
    <p class="muted">Ranked from {routeReport.window.retainedExchanges} retained exchanges · buffer {routeReport.window.bufferSize}</p>
    <table class="route-table" aria-label="Ranked HTTP routes">
      <thead><tr><th>Route</th><th>Requests</th><th>Errors</th><th>Timed</th><th>Total duration</th><th>p95 duration</th><th></th></tr></thead>
      <tbody>
        {#each rankedRoutes as route (route.id)}
          <tr data-route-id={route.id}>
            <td><span class="mono">{route.method} {route.route}</span><span class="muted sm">{route.routeSource === 'FRAMEWORK_TEMPLATE' ? 'template' : 'masked path'}</span></td>
            <td>{route.requests}</td><td>{route.errorCount}</td><td>{route.timedRequests}</td>
            <td>{route.totalDurationMs} ms</td><td>{route.p95DurationMs ?? '—'} ms</td>
            <td><button class="link" aria-label="View exchanges for {route.id}" aria-haspopup="dialog" aria-pressed={selectedRoute?.id === route.id} onclick={(event) => openRoute(route, event)}>View exchanges</button></td>
          </tr>
        {:else}<tr><td colspan="7" class="muted">No route rankings available.</td></tr>{/each}
      </tbody>
    </table>
    {#if routeReport.routesTruncated}<p class="muted">Showing the top routes from {routeReport.distinctRoutes} retained routes.</p>{/if}
    {#each routeReport.notes as note}<p class="muted sm">{note}</p>{/each}
  {/if}
</section>

<dialog bind:this={drawer} class="route-drawer" aria-label="Route exchanges" onkeydown={(event) => event.key === 'Escape' && closeRoute()} onclick={(event) => event.target === drawer && closeRoute()} onclose={() => { selectedRoute = null; routeQuery = ''; opener?.focus(); }}>
  {#if selectedRoute}
    <header class="panel-head"><h2>{selectedRoute.method} {selectedRoute.route}</h2><button class="link" aria-label="Close route exchanges" onclick={closeRoute}>Close</button></header>
    <ServerTable title="Route exchanges" path="http-exchanges" key="route-exchanges" params={{ route: selectedRoute.id, method, statusClass }} bind:q={routeQuery} placeholder="Filter route exchanges" noun="requests" columns={7} cols={['5.5rem', '5rem', '', '4.5rem', '5.5rem', '5.5rem', '6rem']}>
      {#snippet controls()}{/snippet}
      {#snippet head()}<tr><th>Time</th><th>Method</th><th>Path</th><th>Status</th><th>Duration</th><th>Size</th><th></th></tr>{/snippet}
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

<style>
  .routes { padding: var(--s4); overflow: auto; }
  .route-table { width: 100%; }
  .route-table td:first-child > * { display: block; }
  .route-drawer { position: fixed; inset: 0 0 0 auto; margin: 0; width: min(72rem, 100%); max-width: 100%; height: 100dvh; max-height: 100dvh; border: 0; padding: var(--s4); background: var(--panel); color: var(--ink); overflow: auto; }
  .route-drawer::backdrop { background: rgb(0 0 0 / 40%); }
  @media (max-width: 720px) { .route-table { display: block; overflow-x: auto; } .route-drawer { padding: var(--s2); } }
  tr.detail td { height: auto; padding: var(--s2) var(--s4); background: var(--rail); }
  .cols { display: grid; grid-template-columns: 1fr 1fr; gap: var(--s4); }
  .wrap { overflow-wrap: anywhere; }
</style>
