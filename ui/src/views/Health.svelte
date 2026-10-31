<script lang="ts">
  import { untrack } from 'svelte';
  import PanelShell from '../components/PanelShell.svelte';
  import { errorText, get, post } from '../lib/api';
  import { loader } from '../lib/load.svelte';
  import { clock } from '../lib/status';
  import type { HealthNode, Panel } from '../lib/types';

  let { panel }: { panel: Panel } = $props();

  const tree = loader(() => get<HealthNode>('health'));
  let failure = $state<string | null>(null);
  let running = $state(false);

  /** Only a writable panel runs the checks (a POST that runs user code); a read-only one shows the cache. */
  async function refresh() {
    if (running) return; // single-flight: never start a second check while one is running
    failure = null;
    if (!panel.readOnly) {
      running = true;
      try {
        await post('health/check');
      } catch (e) {
        failure = errorText(e, 'The checks could not run.'); // e.g. 409: a previous run is still going
      } finally {
        running = false;
      }
    }
    await tree.reload();
  }
  // Once on open; there is no timer, because a check runs user code.
  $effect(() => untrack(() => void refresh()));

  const cls = (status: string) => (status === 'UP' ? 'ok' : status === 'DOWN' ? 'danger' : status === 'OUT_OF_SERVICE' ? 'warn' : 'muted');
  const checkedAt = $derived(tree.data?.details?.checkedAt);
  const shown = (v: unknown) => (typeof v === 'string' ? v : JSON.stringify(v));
</script>

{#snippet item(n: HealthNode)}
  <li>
    <span class="mono">{n.name}</span> <span class="tag {cls(n.status)}">{n.status}</span>
    {#if n.details}
      {#each Object.entries(n.details).filter(([k, v]) => k !== 'checkedAt' && v !== null) as [k, v]}
        <span class="sm muted wrap">{k}: <span class="mono">{shown(v)}</span></span>
      {/each}
    {/if}
    {#if n.unavailableReason}<div class="sm muted">{n.unavailableReason}</div>{/if}
    {#if n.components.length}<ul>{#each n.components as c}{@render item(c)}{/each}</ul>{/if}
  </li>
{/snippet}

<PanelShell
  title="Health"
  loading={tree.loading}
  error={tree.error}
  onretry={tree.reload}
  notice={panel.readOnly ? (panel.readOnlyReason ?? 'Read-only') : null}
  count={typeof checkedAt === 'number' ? `last run ${clock(checkedAt)}` : 'never run'}
>
  {#snippet controls()}
    <button class="primary run" onclick={refresh} disabled={panel.readOnly || running} title={panel.readOnly ? (panel.readOnlyReason ?? 'Read-only') : undefined}>Run checks</button>
  {/snippet}
  {#if failure}<p class="notice danger" role="alert">{failure}</p>{/if}
  {#if tree.data}
    {@const root = tree.data}
    {#if root.guidanceReason}<p class="notice">{root.guidanceReason}</p>{/if}
    {#if !root.available}
      <div class="empty"><p class="lead">Nothing to check yet</p><p>{root.unavailableReason}</p></div>
    {:else}
      <ul class="tree">{@render item(root)}</ul>
    {/if}
    {#each root.setup as step}
      <section class="block">
        <h2>{step.title}</h2>
        <p class="sm muted step">{step.description}</p>
        {#each step.snippets as snippet}<pre class="mono step">{snippet}</pre>{/each}
      </section>
    {/each}
  {/if}
</PanelShell>

<style>
  .tree, .tree ul { list-style: none; margin: 0; padding-left: var(--s4); }
  .tree { padding: var(--s3) var(--s4); }
  .tree li { padding: var(--s1) 0; }
  .wrap { overflow-wrap: anywhere; }
  .run { margin-left: auto; }
  .step { margin: 0; padding: var(--s1) var(--s4); }
  pre { overflow: auto; }
</style>
