<script lang="ts">
  import ServerTable from '../components/ServerTable.svelte';
  import type { Mapping } from '../lib/types';

  let { q = '' }: { q?: string } = $props();
  // svelte-ignore state_referenced_locally (the view is remounted when the route's q changes)
  let query = $state(q);
</script>

<ServerTable
  title="Mappings"
  path="mappings/flat"
  key="mappings"
  bind:q={query}
  placeholder="Filter by path, method or handler"
  noun="mappings"
  columns={3}
  cols={['6rem', '', '35%']}
>
  {#snippet head()}
    <tr><th>Method</th><th>Path</th><th>Handler</th></tr>
  {/snippet}
  {#snippet body(items: readonly Mapping[])}
    {#each items as m, i (i)}
      <tr>
        <td class="mono">{m.method}</td>
        <td class="mono wrap">{m.pattern}</td>
        <td class="mono shrink muted">{m.handler ?? ''}</td>
      </tr>
    {/each}
  {/snippet}
</ServerTable>
