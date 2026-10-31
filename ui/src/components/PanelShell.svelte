<script lang="ts">
  import type { Snippet } from 'svelte';
  import { scrollable } from '../lib/scrollable';

  let {
    title, loading = false, error = null, notice = null, count = null, onretry, controls, children,
  }: {
    title: string;
    loading?: boolean;
    error?: string | null;
    /** A standing note under the header, e.g. why the panel is read-only. */
    notice?: string | null;
    count?: string | null;
    onretry?: () => void;
    controls?: Snippet;
    children: Snippet;
  } = $props();
</script>

<div class="panel">
  <header class="panel-head">
    <h1>{title}</h1>
    {@render controls?.()}
    {#if count}<span class="muted count">{count}</span>{/if}
  </header>
  <div class="panel-body" use:scrollable role="region" aria-label={title} aria-busy={loading}>
    {#if notice}<p class="notice warn">{notice}</p>{/if}
    {#if error}
      <div class="empty" role="alert">
        <p class="lead danger">Could not load {title}</p>
        <p>{error}</p>
        {#if onretry}<button onclick={onretry}>Retry</button>{/if}
      </div>
    {:else if loading}
      <div class="empty" role="status"><p class="muted">Loading…</p></div>
    {:else}
      {@render children()}
    {/if}
  </div>
</div>

<style>
  .count { margin-left: auto; white-space: nowrap; }
</style>
