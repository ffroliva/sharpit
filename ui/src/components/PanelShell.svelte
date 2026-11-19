<script lang="ts">
  import type { Snippet } from 'svelte';
  import { panelActionReason } from '../lib/panelState';
  import { focusRegion, scrollable } from '../lib/scrollable';
  import type { Panel } from '../lib/types';

  let {
    title, panel, loading = false, error = null, notice = null, count = null, onretry, controls, children,
  }: {
    title: string;
    panel?: Panel | Partial<Panel> | null;
    loading?: boolean;
    error?: string | null;
    /** A standing note under the header, e.g. why the panel is read-only. */
    notice?: string | null;
    count?: string | null;
    onretry?: () => void;
    controls?: Snippet;
    children: Snippet;
  } = $props();

  const derivedNotice = $derived(notice ?? (panel ? panelActionReason(panel) : null));
</script>

<div class="panel">
  <header class="panel-head">
    <h1>{title}</h1>
    {@render controls?.()}
    {#if count}<span class="muted count">{count}</span>{/if}
  </header>
  <div class="panel-body" use:scrollable role="region" aria-label={title} aria-busy={loading}>
    {#if derivedNotice}<p class="notice warn">{derivedNotice}</p>{/if}
    {#if error}
      <div class="empty" role="alert">
        <p class="lead danger">Could not load {title}</p>
        <p>{error}</p>
        {#if onretry}<button onclick={(event) => { focusRegion(event); onretry(); }}>Retry</button>{/if}
      </div>
    {:else if loading}
      <div class="empty" role="status"><p class="muted">Loading…</p></div>
    {:else}
      {@render children()}
    {/if}
  </div>
</div>

<style>
  .panel-head h1 { margin-right: auto; }
  .count { white-space: nowrap; }
</style>
