<script lang="ts">
  import BeanGraph from '../components/BeanGraph.svelte';
  import ServerTable from '../components/ServerTable.svelte';
  import type { BeanRow } from '../lib/types';

  let { q = '' }: { q?: string } = $props();

  // svelte-ignore state_referenced_locally (the view is remounted when the route's q changes)
  let query = $state(q);
  let classification = $state('');
  let mode = $state<'list' | 'graph'>('list');
  let focus = $state<string | null>(null);

  function showInGraph(name: string) {
    focus = name;
    mode = 'graph';
  }
</script>

{#snippet switcher()}
  <div class="switch" role="group" aria-label="View">
    <button aria-pressed={mode === 'list'} onclick={() => (mode = 'list')}>List</button>
    <button aria-pressed={mode === 'graph'} onclick={() => (mode = 'graph')}>Graph</button>
  </div>
{/snippet}

{#if mode === 'graph'}
  <BeanGraph bind:focus controls={switcher} />
{:else}
  <ServerTable
    title="Beans"
    path="beans"
    key="beans"
    params={{ classification }}
    bind:q={query}
    placeholder="Filter by name or type"
    noun="beans"
    columns={4}
  >
    {#snippet controls()}
      <label class="visually-hidden" for="bean-class">Classification</label>
      <select id="bean-class" bind:value={classification}>
        <option value="">All classifications</option>
        <option value="APPLICATION">application</option>
        <option value="FRAMEWORK">framework</option>
      </select>
      {@render switcher()}
    {/snippet}
    {#snippet head()}
      <tr><th>Bean</th><th>Scope</th><th class="num">Depends on</th><th><span class="visually-hidden">Graph</span></th></tr>
    {/snippet}
    {#snippet body(items: readonly BeanRow[])}
      {#each items as b (b.name)}
        <tr>
          <td class="wrap">
            <span class="mono">{b.name}</span>
            {#if b.classification !== 'APPLICATION'}<span class="muted sm"> {b.classification.toLowerCase()}</span>{/if}
          </td>
          <td class="muted">{b.scope ?? ''}</td>
          <td class="num" title={b.dependencies.join('\n')}>{b.dependencies.length}</td>
          <td class="num"><button onclick={() => showInGraph(b.name)} aria-label="Show {b.name} in the graph">Graph</button></td>
        </tr>
      {/each}
    {/snippet}
  </ServerTable>
{/if}

<style>
  .switch { display: inline-flex; }
  .switch button { border-radius: 0; }
  .switch button:first-child { border-radius: var(--radius) 0 0 var(--radius); }
  .switch button:last-child { border-radius: 0 var(--radius) var(--radius) 0; margin-left: -1px; }
  .switch button[aria-pressed='true'] { background: var(--sel); border-color: var(--accent); position: relative; }
</style>
