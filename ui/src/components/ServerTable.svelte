<script lang="ts" generics="T">
  import { tick, untrack, type Snippet } from 'svelte';
  import { ApiError, type Params } from '../lib/api';
  import { PAGE_SIZE, ServerPage } from '../lib/paging';
  import { href, parse } from '../lib/route';
  import { scrollable } from '../lib/scrollable';

  let {
    title,
    path,
    key,
    params = {},
    q = $bindable(''),
    placeholder,
    columns,
    cols,
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
    /** Column widths (CSS lengths, '' for "the rest"): a fixed layout, so columns do not jump as rows change. */
    cols?: string[];
    head: Snippet;
    body: Snippet<[readonly T[], ServerPage<T>]>;
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
  let filter = $state<HTMLInputElement>();
  let table = $state<HTMLTableElement>();

  // Filter as you type: debounce, then reload from offset 0; a stale answer is dropped.
  $effect(() => {
    const query = { ...params, q };
    const mine = ++seq;
    const delay = untrack(() => page) ? 150 : 0; // first load at once; typing waits for a pause
    loading = true;
    const timer = setTimeout(async () => {
      keepInUrl(q);
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

  // The filter goes into the hash (a reload, Back or a shared link keeps it) without a hashchange, so no remount.
  function keepInUrl(query: string) {
    const here = parse(location.hash);
    if (here.q !== query) history.replaceState(history.state, '', href(here.panel, query));
  }

  /** Re-fetch the rows on screen (as many as are loaded), e.g. after a change that affects other rows. */
  export async function reload() {
    if (!page) return;
    const mine = seq;
    loading = true;
    try {
      const next = await page.refresh();
      if (mine === seq) page = next;
    } catch {
      // keep the rows shown; the next filter or reload tries again
    } finally {
      if (mine === seq) loading = false;
    }
  }

  async function more(event: MouseEvent) {
    const button = event.currentTarget as HTMLButtonElement;
    if (!page || loadingMore) return;
    const mine = seq;
    const before = page.items.length;
    loadingMore = true;
    try {
      const next = await page.more();
      if (mine === seq) page = next;
    } finally {
      loadingMore = false;
    }
    await tick();
    // the button keeps focus while more remain; once it is gone, focus moves to the first new row, never <body>
    if (!button.isConnected) {
      const row = table?.querySelectorAll<HTMLElement>('tbody tr:not(.group)')[before];
      if (row) {
        row.tabIndex = -1;
        row.focus();
      }
    }
  }

  function clear() {
    q = '';
    filter?.focus(); // the button that was clicked disappears with the empty state
  }

  const remaining = $derived(page ? Math.min(PAGE_SIZE, page.matched - page.items.length) : 0);
</script>

<div class="panel">
  <header class="panel-head">
    <h1>{title}</h1>
    <div class="grow">
      <label class="visually-hidden" for="filter-{key}">Filter {noun}</label>
      <input bind:this={filter} id="filter-{key}" class="panel-filter" type="search" {placeholder} bind:value={q} autocomplete="off" spellcheck="false" />
    </div>
    {@render controls?.()}
    <span class="muted count" aria-live="polite">
      {#if page}{loading ? '…' : page.matched} of {page.total}{/if}
    </span>
  </header>
  <div class="panel-body" use:scrollable role="region" aria-label={title} aria-busy={loading}>
    {#if notice}<p class="notice warn">{notice}</p>{/if}
    {#if error}
      <div class="empty" role="alert"><p class="lead danger">Could not load {noun}</p><p>{error}</p></div>
    {:else}
      <table bind:this={table} aria-label={title} class:fixed={!!cols}>
        {#if cols}<colgroup>{#each cols as width}<col style:width={width || null} />{/each}</colgroup>{/if}
        <thead>{@render head()}</thead>
        <!-- the old rows stay while a new filter loads, dimmed so they do not read as the answer -->
        <tbody class:stale={loading && !!page}>
          {#if !page}
            {#each { length: 8 } as _}<tr class="skeleton">{#each { length: columns } as __}<td></td>{/each}</tr>{/each}
          {:else}
            {@render body(page.items, page)}
          {/if}
        </tbody>
      </table>
      {#if page && page.items.length === 0 && !loading}
        <div class="empty">
          {#if q}
            <p>No {noun} match <code>{q}</code>.</p>
            <button class="link" onclick={clear}>Clear the filter</button>
          {:else}
            <p>No {noun} to show.</p>
          {/if}
        </div>
      {/if}
      {#if page?.hasMore}
        <div class="more">
          <span class="muted">Showing {page.items.length} of {page.matched}</span>
          <button onclick={more} aria-disabled={loadingMore}>{loadingMore ? 'Loading…' : `Load ${remaining} more`}</button>
        </div>
      {/if}
    {/if}
  </div>
</div>

<style>
  .count { white-space: nowrap; }
  table.fixed { table-layout: fixed; }
  tbody { transition: opacity var(--dur) var(--ease); }
  tbody.stale { opacity: 0.6; }
</style>
