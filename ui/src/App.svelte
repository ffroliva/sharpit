<script lang="ts">
  import { tick } from 'svelte';
  import Palette from './components/Palette.svelte';
  import TokenPrompt from './components/TokenPrompt.svelte';
  import { ApiError, authRequired, get } from './lib/api';
  import { groupPanels, notBuilt } from './lib/nav';
  import { href, route } from './lib/route';
  import { applyTheme, loadTheme, nextTheme, type Theme } from './lib/theme';
  import type { Panel } from './lib/types';
  import Activity from './views/Activity.svelte';
  import Alembic from './views/Alembic.svelte';
  import Beans from './views/Beans.svelte';
  import Config from './views/Config.svelte';
  import ConnectionPools from './views/ConnectionPools.svelte';
  import Exceptions from './views/Exceptions.svelte';
  import Health from './views/Health.svelte';
  import HttpExchanges from './views/HttpExchanges.svelte';
  import HttpProbe from './views/HttpProbe.svelte';
  import Loggers from './views/Loggers.svelte';
  import LogTail from './views/LogTail.svelte';
  import Mappings from './views/Mappings.svelte';
  import Overview from './views/Overview.svelte';
  import RestApi from './views/RestApi.svelte';
  import ServerStatus from './views/ServerStatus.svelte';
  import SqlTrace from './views/SqlTrace.svelte';
  import Threads from './views/Threads.svelte';
  import Vulnerabilities from './views/Vulnerabilities.svelte';

  let panels = $state<Panel[] | null>(null);
  let shellError = $state<string | null>(null);
  let paletteOpen = $state(false);
  let theme = $state<Theme>(loadTheme());
  /** Bumped after the token prompt succeeds, so the current view reloads its data. */
  let epoch = $state(0);

  const isMac = /Mac|iPhone|iPad/.test(navigator.platform);

  async function loadPanels() {
    try {
      // Python has providers, not Spring beans: only the label changes; the id, URL and API stay `beans`
      panels = (await get<{ panels: Panel[] }>('panels')).panels.map((p) => (p.id === 'beans' ? { ...p, title: 'Providers' } : p));
      shellError = null;
    } catch (e) {
      if (!(e instanceof ApiError && e.status === 401)) {
        shellError = e instanceof ApiError ? `sharpit answered HTTP ${e.status}.` : 'The application is not responding.';
      }
    }
  }
  loadPanels();

  // the server's own reasons where it gives one; a disabled panel's reason mirrors engine/panels.py
  function reason(p: Panel): string | null {
    if (!p.available) return p.unavailableReason ?? 'Not available in this application';
    if (!p.enabled) return `Panel is disabled via SHARPIT_PANELS_${p.id.toUpperCase().replace(/-/g, '_')}_ENABLED=false`;
    if (p.readOnly) return p.readOnlyReason ?? 'Read-only';
    return null;
  }
  const usable = (p: Panel) => p.available && p.enabled;
  const current = $derived(panels?.find((p) => p.id === $route.panel) ?? null);

  function authenticated() {
    epoch++;
    loadPanels();
  }

  /** Focus the panel's filter, else its heading: after a navigation the old focus target no longer exists. */
  function focusPanel() {
    const target =
      document.querySelector<HTMLElement>('main .panel-filter') ?? document.querySelector<HTMLElement>('main h1, main .empty .lead');
    if (!target) return document.getElementById('main')?.focus();
    if (!(target instanceof HTMLInputElement)) target.tabIndex = -1;
    target.focus();
  }

  async function paletteClosed(picked: boolean) {
    const lost = (el: Element | null) => !el || el === document.body || el.classList.contains('skip') || !el.isConnected;
    if (!picked && !lost(document.activeElement)) return; // Esc: the dialog put focus back where it was
    await new Promise((resolve) => setTimeout(resolve)); // after the hashchange the pick queued
    await tick(); // and after the new view mounted
    focusPanel();
  }

  function cycleTheme() {
    theme = nextTheme(theme);
    applyTheme(theme);
  }

  function onkeydown(event: KeyboardEvent) {
    if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'k') {
      event.preventDefault();
      if (!$authRequired && panels) paletteOpen = !paletteOpen;
      return;
    }
    const typing = event.target instanceof HTMLElement && event.target.closest('input, select, textarea, [contenteditable]');
    if (event.key === '/' && !typing && !paletteOpen) {
      const filter = document.querySelector<HTMLInputElement>('.panel-filter');
      if (filter) {
        event.preventDefault();
        filter.focus();
        filter.select();
      }
    }
  }
</script>

<svelte:window {onkeydown} />

<a class="skip" href="#main">Skip to panel</a>
<div class="shell">
  <nav class="rail" aria-label="Panels">
    <div class="brand">sharpit</div>
    {#if panels}
      {#each groupPanels(panels) as group (group.title)}
        <div class="group">{group.title}</div>
        <ul aria-label={group.title}>
          {#each group.panels as p (p.id)}
            {@const why = reason(p)}
            <li>
              <a
                href={href(p.id)}
                class:muted={!usable(p) || p.readOnly}
                aria-current={p.id === $route.panel ? 'page' : undefined}
                aria-describedby={why ? `why-${p.id}` : undefined}
              >
                {p.title}
              </a>
              {#if why}<div class="why sm" id="why-{p.id}">{why}</div>{/if}
            </li>
          {/each}
        </ul>
      {/each}
    {:else if !$authRequired && !shellError}
      <ul aria-hidden="true">{#each { length: 7 } as _}<li class="ghost"></li>{/each}</ul>
    {/if}
    <div class="tools">
      <button onclick={() => (paletteOpen = true)} disabled={!panels || $authRequired} aria-keyshortcuts={isMac ? 'Meta+K' : 'Control+K'}>
        Go to… <kbd>{isMac ? '⌘' : 'Ctrl'} K</kbd>
      </button>
      <button onclick={cycleTheme} aria-label="Theme: {theme}. Switch theme">Theme: {theme}</button>
    </div>
  </nav>

  <main id="main" tabindex="-1">
    {#if $authRequired}
      <TokenPrompt onauthenticated={authenticated} />
    {:else if shellError}
      <div class="empty" role="alert">
        <p class="lead danger">sharpit could not load</p>
        <p>{shellError}</p>
        <button onclick={loadPanels}>Retry</button>
      </div>
    {:else if panels}
      {#if !current}
        <div class="empty">
          <p class="lead">No panel called <code>{$route.panel}</code></p>
          <p><a href={href('overview')}>Open the overview</a> or press {isMac ? '⌘' : 'Ctrl'} K to search.</p>
        </div>
      {:else if !usable(current)}
        <div class="empty">
          <p class="lead">{current.title} is unavailable</p>
          <p>{reason(current)}</p>
        </div>
      {:else}
        {#key `${current.id}|${$route.q}|${epoch}`}
          {#if current.id === 'overview'}<Overview />
          {:else if current.id === 'config'}<Config q={$route.q} />
          {:else if current.id === 'mappings'}<Mappings q={$route.q} />
          {:else if current.id === 'loggers'}<Loggers panel={current} q={$route.q} />
          {:else if current.id === 'beans'}<Beans q={$route.q} />
          {:else if current.id === 'vulnerabilities'}<Vulnerabilities panel={current} />
          {:else if current.id === 'activity'}<Activity q={$route.q} />
          {:else if current.id === 'http-exchanges'}<HttpExchanges q={$route.q} />
          {:else if current.id === 'exceptions'}<Exceptions panel={current} />
          {:else if current.id === 'log-tail'}<LogTail />
          {:else if current.id === 'threads'}<Threads />
          {:else if current.id === 'health'}<Health panel={current} />
          {:else if current.id === 'http-probe'}<HttpProbe panel={current} q={$route.q} />
          {:else if current.id === 'sql-trace'}<SqlTrace panel={current} />
          {:else if current.id === 'database-connection-pools'}<ConnectionPools />
          {:else if current.id === 'alembic'}<Alembic panel={current} />
          {:else if current.id === 'rest-api'}<RestApi panel={current} />
          {:else if current.id === 'mcp-server' || current.id === 'cli'}<ServerStatus panel={current} kind={current.id} />
          {:else}
            <div class="empty"><p class="lead">{current.title}</p><p>This version of the console has no view for this panel yet.</p></div>
          {/if}
        {/key}
      {/if}
    {/if}
  </main>
</div>

{#if panels}<Palette bind:open={paletteOpen} panels={panels.filter((p) => !notBuilt(p))} onclosed={paletteClosed} />{/if}

<style>
  .shell { display: grid; grid-template-columns: var(--rail-w) 1fr; height: 100%; }
  .rail {
    display: flex; flex-direction: column; background: var(--rail); border-right: 1px solid var(--line);
    overflow: auto; min-height: 0;
  }
  .brand { height: var(--head); display: flex; align-items: center; padding: 0 var(--s4); font-weight: 600; font-size: 14.5px; }
  ul { list-style: none; margin: 0; padding: 0 0 var(--s3); }
  .group { padding: var(--s2) var(--s4) var(--s1); color: var(--muted); font-size: 12px; line-height: 16px; }
  li a {
    display: flex; align-items: center; min-height: var(--row); padding: 0 var(--s4); color: var(--ink);
    text-decoration: none; transition: background-color var(--dur) var(--ease);
  }
  li a.muted { color: var(--muted); }
  li a:hover { background: var(--sel); }
  li a[aria-current='page'] { background: var(--sel); box-shadow: inset 0 0 0 1px var(--accent); }
  li a:focus-visible { outline-offset: -2px; }
  .why { padding: 0 var(--s4) var(--s1); color: var(--muted); }
  .ghost { height: var(--row); margin: 0 var(--s4) var(--s1); background: var(--line); opacity: 0.4; border-radius: 2px; }
  .tools { margin-top: auto; display: flex; flex-direction: column; gap: var(--s2); padding: var(--s3) var(--s4); border-top: 1px solid var(--line); }
  .tools button { display: flex; justify-content: space-between; align-items: center; text-align: left; }
  kbd { font: 12px var(--ui); color: var(--muted); }
  main { min-width: 0; min-height: 0; overflow: hidden; }
  main:focus { outline: none; }
  .skip { position: absolute; left: var(--s2); top: -40px; z-index: var(--z-palette); background: var(--bg); padding: var(--s1) var(--s2); }
  .skip:focus { top: var(--s2); }

  /* Below 720px the rail is one scrolling row above the panel (DESIGN.md) */
  @media (max-width: 720px) {
    .shell { grid-template-columns: 1fr; grid-template-rows: auto 1fr; }
    .rail { flex-direction: row; align-items: stretch; border-right: 0; border-bottom: 1px solid var(--line); overflow-x: auto; }
    .brand { flex: none; }
    ul { display: flex; padding: 0; }
    .group { display: none; }
    li { flex: none; }
    li a { height: 100%; }
    .why { display: none; }
    .tools { flex-direction: row; margin: 0; border-top: 0; border-left: 1px solid var(--line); padding: var(--s1) var(--s2); align-items: center; }
  }
</style>
