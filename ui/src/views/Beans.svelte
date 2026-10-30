<script lang="ts">
  import { tick } from 'svelte';
  import BeanGraph from '../components/BeanGraph.svelte';
  import ServerTable from '../components/ServerTable.svelte';
  import type { BeanRow } from '../lib/types';

  let { q = '' }: { q?: string } = $props();

  // svelte-ignore state_referenced_locally (the view is remounted when the route's q changes)
  let query = $state(q);
  let classification = $state('');
  let mode = $state<'list' | 'graph'>('list');
  let focus = $state<string | null>(null);

  /** Switching remounts the header, so keyboard focus follows to the pressed view button (the graph then takes it to
   * the centre node once drawn, when one was chosen). */
  async function show(next: 'list' | 'graph', name: string | null = null) {
    if (next === 'graph') focus = name;
    mode = next;
    await tick();
    document.querySelector<HTMLElement>('main .switch button[aria-pressed="true"]')?.focus();
  }
</script>

{#snippet switcher()}
  <div class="switch" role="group" aria-label="View">
    <button aria-pressed={mode === 'list'} onclick={() => show('list')}>List</button>
    <button aria-pressed={mode === 'graph'} onclick={() => show('graph', focus)}>Graph</button>
  </div>
{/snippet}

{#if mode === 'graph'}
  <BeanGraph bind:focus controls={switcher} />
{:else}
  <ServerTable
    title="Providers"
    path="beans"
    key="beans"
    params={{ classification }}
    bind:q={query}
    placeholder="Filter by name or type"
    noun="providers"
    columns={4}
    cols={['', '9rem', '7rem', '5rem']}
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
      <tr><th>Provider</th><th>Scope</th><th class="num">Depends on</th><th><span class="visually-hidden">Graph</span></th></tr>
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
          <td class="num"><button onclick={() => show('graph', b.name)} aria-label="Show {b.name} in the graph">Graph</button></td>
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
