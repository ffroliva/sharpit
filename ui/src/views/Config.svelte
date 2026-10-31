<script lang="ts">
  import ServerTable from '../components/ServerTable.svelte';
  import { get } from '../lib/api';
  import type { ServerPage } from '../lib/paging';
  import type { Property, PropertySuggestion } from '../lib/types';

  let { q = '' }: { q?: string } = $props();

  // svelte-ignore state_referenced_locally (the view is remounted when the route's q changes)
  let query = $state(q);
  let source = $state('');
  /** Sources in precedence order, highest first (the order the server lists them). */
  let sources = $state<string[]>([]);
  let envOpen = $state(false);

  get<{ sources: string[] }>('config', { limit: 1 }).then(
    (d) => (sources = d.sources),
    () => {}, // the table shows the load error
  );

  const ENV = 'systemEnvironment';
  // The app's own keys: a settings field (its own source, or an env value with the field's default beside it) or a key
  // the code reads with os.getenv (the scan's file:line is in description). Everything else is the machine's environment.
  // shortcut: a settings field whose default is None and whose value comes from the environment reads as machine env;
  // the API would need to mark settings fields explicitly to tell them apart.
  const isApp = (p: Property) => p.source !== ENV || p.description !== null || p.defaultValue !== null;

  type Row = { kind: 'set'; p: Property } | { kind: 'unset'; s: PropertySuggestion };

  function split(items: readonly Property[], page: ServerPage<Property>) {
    // an unset key has no source: it belongs only to the unfiltered view
    const unset = source ? [] : ((page.data.propertySuggestions ?? []) as PropertySuggestion[]);
    const app: Row[] = [
      ...items.filter(isApp).map((p): Row => ({ kind: 'set', p })),
      ...unset.map((s): Row => ({ kind: 'unset', s })),
    ].sort((a, b) => cmp(name(a), name(b)));
    // only the loaded rows are split; with more on the server the env count is a lower bound
    return { app, env: items.filter((p) => !isApp(p)), partial: items.length < page.matched };
  }
  const name = (r: Row) => (r.kind === 'set' ? r.p.name : r.s.name);
  const cmp = (a: string, b: string) => (a < b ? -1 : a > b ? 1 : 0);

  const isDefault = (s: string) => s.startsWith('default');
  // the row's source beat a lower one: an explicit override, or a set value over the code's default
  const won = (p: Property) => p.override || (p.defaultValue !== null && !isDefault(p.source));
  const show = (v: unknown) => (v === null || v === undefined ? '' : typeof v === 'string' ? v : JSON.stringify(v));
  const precedence = (s: string) => {
    const i = sources.indexOf(s);
    return i < 0 ? '' : i === 0 ? 'highest precedence' : i === sources.length - 1 ? 'lowest precedence' : `precedence ${i + 1} of ${sources.length}`;
  };
  // the getenv scan reports `path/to/module.py:line`; a settings field's description is prose
  const provenance = (d: string) => (/\.py:\d+$/.test(d) ? `read at ${d}` : d);
  const filtering = $derived(query.trim() !== '');
</script>

{#snippet nameCell(n: string, description: string | null)}
  <td class="wrap">
    <span class="name mono">{n}</span>
    {#if description}<span class="prov muted sm">{provenance(description)}</span>{/if}
  </td>
{/snippet}

<ServerTable
  title="Configuration"
  path="config"
  key="properties"
  params={{ source }}
  bind:q={query}
  placeholder="Filter by name or value"
  noun="properties"
  columns={2}
  cols={['40%', '']}
>
  {#snippet controls()}
    <label class="visually-hidden" for="config-source">Source</label>
    <select id="config-source" bind:value={source}>
      <option value="">All sources</option>
      {#each sources as s}<option value={s}>{s}</option>{/each}
    </select>
  {/snippet}
  {#snippet head()}
    <tr><th>Name</th><th>Value</th></tr>
  {/snippet}
  {#snippet body(items: readonly Property[], page: ServerPage<Property>)}
    {@const { app, env, partial } = split(items, page)}
    {@const envCount = partial ? `at least ${env.length}` : `${env.length}`}
    {#if app.length > 0}
      <tr class="group">
        <th colspan="2" scope="colgroup">
          Your application <span class="muted sm">settings fields and the keys your code reads</span>
        </th>
      </tr>
      {#each app as r (r.kind + name(r))}
        <tr>
          {#if r.kind === 'set'}
            {@const p = r.p}
            {@render nameCell(p.name, p.description)}
            <td class="shrink">
              <span class="mono">{show(p.value)}</span>
              {#if p.masked}<span class="tag warn">masked</span>{/if}
              <span class="src muted sm">
                <span title={precedence(p.source)}>{p.source}</span>
                {#if won(p)}<span class="tag ok" title="This source's value is the one in effect">won</span>
                  <span>over default <span class="mono">{show(p.defaultValue) || '—'}</span></span>{/if}
              </span>
            </td>
          {:else}
            {@render nameCell(r.s.name, r.s.description)}
            <td class="shrink muted">
              not set · default <span class="mono">{show(r.s.defaultValue) || '—'}</span>
            </td>
          {/if}
        </tr>
      {/each}
    {/if}
    {#if env.length > 0}
      {@const open = envOpen || filtering}
      <tr class="group">
        <th colspan="2" scope="colgroup">
          {#if filtering}
            Other environment variables ({envCount})
          {:else}
            <button class="disclose" aria-expanded={open} onclick={() => (envOpen = !envOpen)}>
              Other environment variables ({envCount})
            </button>
          {/if}
          <span class="muted sm">this machine's own, not read by your code</span>
        </th>
      </tr>
      {#if open}
        {#each env as p (p.name)}
          <tr>
            {@render nameCell(p.name, null)}
            <td class="shrink">
              <span class="mono">{show(p.value)}</span>
              {#if p.masked}<span class="tag warn">masked</span>{/if}
            </td>
          </tr>
        {/each}
      {/if}
    {/if}
  {/snippet}
</ServerTable>

<style>
  .tag { margin-left: var(--s1); }
  .prov, .src { display: block; }
  td.shrink, td.wrap { padding-top: var(--s1); padding-bottom: var(--s1); }
  .disclose { border: 0; background: none; padding: 0; height: auto; font-weight: 600; }
  .disclose::before { content: '▸'; display: inline-block; width: 1em; color: var(--muted); }
  .disclose[aria-expanded='true']::before { content: '▾'; }
</style>
