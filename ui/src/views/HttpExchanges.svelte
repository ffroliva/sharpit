<script lang="ts">
  import ServerTable from '../components/ServerTable.svelte';
  import { href } from '../lib/route';
  import { openStream } from '../lib/sse';
  import { clock, statusFamilyClass } from '../lib/status';
  import type { HttpExchange, HttpHeader } from '../lib/types';

  let { q = '' }: { q?: string } = $props();

  // svelte-ignore state_referenced_locally (the view is remounted when the route's q changes)
  let query = $state(q);
  let method = $state('');
  let statusClass = $state('');
  let openId = $state<string | null>(null);
  let table = $state<{ reload(): Promise<void> }>();

  // exchanges have no stream of their own: the activity tick fires on every captured request
  $effect(() => {
    const stream = openStream('api/activity/stream', { onUpdate: () => void table?.reload() });
    return () => stream.close();
  });

  const headers = (list: HttpHeader[]) => list.map((h) => `${h.name}: ${h.values.join(', ')}${h.masked ? ' (masked)' : ''}`);
</script>

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
        <td><button class="link" aria-expanded={openId === x.id} onclick={() => (openId = openId === x.id ? null : x.id)}>Details</button></td>
      </tr>
      {#if openId === x.id}
        <tr class="detail">
          <td colspan="7">
            <p class="sm">
              <a href={href('activity', x.traceId ?? x.id)}>Open in Activity</a> ·
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
  tr.detail td { height: auto; padding: var(--s2) var(--s4); background: var(--rail); }
  .cols { display: grid; grid-template-columns: 1fr 1fr; gap: var(--s4); }
  .wrap { overflow-wrap: anywhere; }
</style>
