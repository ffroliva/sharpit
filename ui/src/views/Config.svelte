<script lang="ts">
  import ServerTable from '../components/ServerTable.svelte';
  import { get } from '../lib/api';
  import type { Property } from '../lib/types';

  let { q = '' }: { q?: string } = $props();

  // svelte-ignore state_referenced_locally (the view is remounted when the route's q changes)
  let query = $state(q);
  let source = $state('');
  /** Sources in precedence order, highest first (the order the server lists them). */
  let sources = $state<string[]>([]);

  get<{ sources: string[] }>('config', { limit: 1 }).then(
    (d) => (sources = d.sources),
    () => {}, // the table shows the load error
  );

  function groups(items: readonly Property[]): [string, Property[]][] {
    const by = new Map<string, Property[]>(sources.map((s) => [s, []]));
    for (const p of items) {
      const list = by.get(p.source);
      if (list) list.push(p);
      else by.set(p.source, [p]);
    }
    return [...by].filter(([, rows]) => rows.length > 0);
  }

  const isDefault = (s: string) => s.startsWith('default');
  // the row's source beat a lower one: an explicit override, or a set value over the code's default
  const won = (p: Property) => p.override || (p.defaultValue !== null && !isDefault(p.source));
  const show = (v: unknown) => (v === null || v === undefined ? '' : typeof v === 'string' ? v : JSON.stringify(v));
  const rank = (s: string) => sources.indexOf(s);
</script>

<ServerTable
  title="Configuration"
  path="config"
  key="properties"
  params={{ source }}
  bind:q={query}
  placeholder="Filter by name or value"
  noun="properties"
  columns={3}
>
  {#snippet controls()}
    <label class="visually-hidden" for="config-source">Source</label>
    <select id="config-source" bind:value={source}>
      <option value="">All sources</option>
      {#each sources as s}<option value={s}>{s}</option>{/each}
    </select>
  {/snippet}
  {#snippet head()}
    <tr><th>Name</th><th>Value</th><th>Source</th></tr>
  {/snippet}
  {#snippet body(items: readonly Property[])}
    {#each groups(items) as [name, rows] (name)}
      <tr class="group">
        <th colspan="3" scope="colgroup">
          {name}
          {#if rank(name) >= 0}
            <span class="muted sm">
              {rank(name) === 0 ? 'highest precedence' : `precedence ${rank(name) + 1} of ${sources.length}`}
            </span>
          {/if}
        </th>
      </tr>
      {#each rows as p (p.name)}
        <tr>
          <td class="mono wrap" title={p.description ?? undefined}>{p.name}</td>
          <td class="mono shrink">
            {show(p.value)}
            {#if p.masked}<span class="tag warn">masked</span>{/if}
            {#if won(p)}<span class="muted sm"> default {show(p.defaultValue) || '—'}</span>{/if}
          </td>
          <td>
            <span class="mono">{p.source}</span>
            {#if won(p)}<span class="tag ok" title="This source's value is the one in effect">won</span>{/if}
          </td>
        </tr>
      {/each}
    {/each}
  {/snippet}
</ServerTable>

<style>
  .tag { margin-left: var(--s1); }
</style>
