<script lang="ts" generics="T">
  import { untrack, type Snippet } from 'svelte';
  import { ApiError, type Params } from '../lib/api';
  import { PAGE_SIZE, ServerPage } from '../lib/paging';

  let {
    title,
    path,
    key,
    params = {},
    q = $bindable(''),
    placeholder,
    columns,
    head,
    body,
    controls,
    noun,
    notice = null,
  }: {
    title: string;
    path: string;
    key: string;
    params?: Params;
    q?: string;
    placeholder: string;
    columns: number;
    head: Snippet;
    body: Snippet<[readonly T[]]>;
    controls?: Snippet;
    noun: string;
    /** A standing note under the header, e.g. why the panel is read-only. */
    notice?: string | null;
  } = $props();

  let page = $state<ServerPage<T> | null>(null);
  let loading = $state(true);
  let loadingMore = $state(false);
  let error = $state<string | null>(null);
  let seq = 0;

  // Filter as you type: debounce, then reload from offset 0; a stale answer is dropped.
  $effect(() => {
    const query = { ...params, q };
    const mine = ++seq;
    const delay = untrack(() => page) ? 150 : 0; // first load at once; typing waits for a pause
    loading = true;
    const timer = setTimeout(async () => {
      try {
        const next = await ServerPage.load<T>(path, key, query);
        if (mine === seq) {
          page = next;
          error = null;
        }
      } catch (e) {
        if (mine === seq) error = e instanceof ApiError ? `HTTP ${e.status}` : 'The application is not responding.';
      } finally {
        if (mine === seq) loading = false;
      }
    }, delay);
    return () => clearTimeout(timer);
  });

  async function more() {
    if (!page || loadingMore) return;
    const mine = seq;
    loadingMore = true;
    try {
      const next = await page.more();
      if (mine === seq) page = next;
    } finally {
      loadingMore = false;
    }
  }

  const remaining = $derived(page ? Math.min(PAGE_SIZE, page.matched - page.items.length) : 0);
</script>

<div class="panel">
  <header class="panel-head">
    <h1>{title}</h1>
    <div class="grow">
      <label class="visually-hidden" for="filter-{key}">Filter {noun}</label>
      <input id="filter-{key}" class="panel-filter" type="search" {placeholder} bind:value={q} autocomplete="off" spellcheck="false" />
    </div>
    {@render controls?.()}
    <span class="muted count" aria-live="polite">
      {#if page}{page.matched} of {page.total}{/if}
    </span>
  </header>
  <div class="panel-body" tabindex="0" role="region" aria-label={title} aria-busy={loading}>
    {#if notice}<p class="notice warn">{notice}</p>{/if}
    {#if error}
      <div class="empty" role="alert"><p class="lead danger">Could not load {noun}</p><p>{error}</p></div>
    {:else}
      <table aria-label={title}>
        <thead>{@render head()}</thead>
        <tbody>
          {#if !page}
            {#each { length: 8 } as _}<tr class="skeleton">{#each { length: columns } as __}<td></td>{/each}</tr>{/each}
          {:else}
            {@render body(page.items)}
          {/if}
        </tbody>
      </table>
      {#if page && page.items.length === 0 && !loading}
        <div class="empty">
          {#if q}
            <p>No {noun} match <code>{q}</code>.</p>
            <button class="link" onclick={() => (q = '')}>Clear the filter</button>
          {:else}
            <p>No {noun} to show.</p>
          {/if}
        </div>
      {/if}
      {#if page?.hasMore}
        <div class="more">
          <span class="muted">Showing {page.items.length} of {page.matched}</span>
          <button onclick={more} disabled={loadingMore}>{loadingMore ? 'Loading…' : `Load ${remaining} more`}</button>
        </div>
      {/if}
    {/if}
  </div>
</div>

<style>
  .count { white-space: nowrap; }
</style>
