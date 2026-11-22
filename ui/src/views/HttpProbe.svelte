<script lang="ts">
  import PanelShell from '../components/PanelShell.svelte';
  import { errorText, get, post } from '../lib/api';
  import { panelActionReason } from '../lib/panelState';
  import { statusFamilyClass } from '../lib/status';
  import type { Mapping, Panel, ProbeResult } from '../lib/types';

  let { panel, q = '' }: { panel: Panel; q?: string } = $props();

  const HISTORY_KEY = 'sharpit.probe.history';
  const METHODS = ['GET', 'HEAD', 'POST', 'PUT', 'PATCH', 'DELETE', 'OPTIONS'];
  const BODY_METHODS = new Set(['POST', 'PUT', 'PATCH']);
  type Entry = { method: string; path: string };
  type RouteOption = Entry & { key: string; handler: string | null; mapping: Mapping };
  type RoutePage = { matched: number };

  /** "DELETE /owners/3" from a Replay link; anything else is just a path. */
  const [prefMethod, prefPath] = (() => {
    const m = /^([A-Z]+) (\/.*)$/.exec(q);
    return m && METHODS.includes(m[1]!) ? [m[1]!, m[2]!] : ['GET', q.startsWith('/') ? q : ''];
  })();

  let method = $state(prefMethod);
  let path = $state(prefPath);
  let headersText = $state('');
  let body = $state('');
  let sending = $state(false);
  let result = $state<ProbeResult | null>(null);
  let failure = $state<string | null>(null);
  let routeQuery = $state('');
  let routeBasePath = $state('');
  let routeMappings = $state<Mapping[]>([]);
  let routePage = $state<RoutePage | null>(null);
  let routeLoaded = $state(false);
  let routeLoading = $state(false);
  let routeError = $state<string | null>(null);
  let routePickerOpen = $state(false);
  let activeRouteIndex = $state(-1);
  let suggestedHeaders = $state<Record<string, string>>({});
  let routeTimer: ReturnType<typeof setTimeout> | null = null;
  let routeSequence = 0;
  let history = $state<Entry[]>(readHistory());

  const routeOptions = $derived.by(() =>
    routeMappings
      .filter((mapping) => typeof mapping.pattern === 'string' && mapping.pattern.startsWith('/'))
      .map((mapping, index) => ({
        key: `${mapping.method}:${mapping.pattern}:${mapping.handler ?? ''}:${index}`,
        method: mapping.method,
        path: `${routeBasePath}${mapping.pattern === '/' ? '' : mapping.pattern}` || '/',
        handler: mapping.handler,
        mapping,
      })),
  );
  const routePopupVisible = $derived(routePickerOpen && (routeLoading || routeError !== null || routeLoaded));
  const routeListVisible = $derived(routePopupVisible && routeOptions.length > 0);
  const activeRouteOptionId = $derived(
    routeListVisible && activeRouteIndex >= 0 ? `probe-route-option-${activeRouteIndex}` : undefined,
  );

  function preferredMediaType(raw: string | null): string {
    const candidates = (raw ?? '')
      .split(',')
      .map((part) => part.split(';', 1)[0]!.trim())
      .filter((part) => part && !part.startsWith('!') && !part.includes('*'));
    return candidates.find((part) => part.toLowerCase().includes('json')) ?? candidates[0] ?? '';
  }

  async function fetchRoutes(query = '') {
    const sequence = ++routeSequence;
    routeLoading = true;
    try {
      const report = await get<{
        mappings?: Mapping[];
        basePath?: string;
        page?: RoutePage;
      }>('mappings/flat', { limit: 50, q: query });
      if (sequence !== routeSequence) return;
      routeBasePath = typeof report?.basePath === 'string' ? report.basePath : '';
      routeMappings = Array.isArray(report?.mappings) ? report.mappings : [];
      routePage = report?.page ?? null;
      routeError = null;
      routeLoaded = true;
    } catch (e) {
      if (sequence !== routeSequence) return;
      routeMappings = [];
      routePage = null;
      routeLoaded = false;
      routeError = errorText(e, 'Unable to load declared routes.');
    } finally {
      if (sequence === routeSequence) routeLoading = false;
    }
    if (sequence === routeSequence) activeRouteIndex = -1;
  }

  function onRoutePickerFocus() {
    routePickerOpen = true;
    if (!routeLoaded && !routeLoading) void fetchRoutes(routeQuery.trim());
  }

  function onRoutePickerInput(value: string) {
    routeQuery = value;
    routeLoaded = false;
    routeMappings = [];
    routePage = null;
    routeError = null;
    routeSequence++;
    routeLoading = false;
    activeRouteIndex = -1;
    if (routeTimer !== null) clearTimeout(routeTimer);
    routeTimer = setTimeout(() => {
      routeTimer = null;
      void fetchRoutes(value.trim());
    }, 120);
  }

  function closeRoutePicker() {
    if (routeTimer !== null) clearTimeout(routeTimer);
    routeSequence++;
    routeLoading = false;
    routePickerOpen = false;
    activeRouteIndex = -1;
  }

  function onRoutePickerKeydown(event: KeyboardEvent) {
    const count = routeOptions.length;
    if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
      event.preventDefault();
      if (!routeListVisible) {
        routePickerOpen = true;
        if (routeTimer !== null) clearTimeout(routeTimer);
        routeTimer = null;
        if (!routeLoaded && !routeLoading) void fetchRoutes(routeQuery.trim());
        else if (count > 0) activeRouteIndex = event.key === 'ArrowDown' ? 0 : count - 1;
        return;
      }
      const step = event.key === 'ArrowDown' ? 1 : -1;
      activeRouteIndex = activeRouteIndex < 0 ? (step > 0 ? 0 : count - 1) : (activeRouteIndex + step + count) % count;
      document.getElementById(`probe-route-option-${activeRouteIndex}`)?.scrollIntoView?.({ block: 'nearest' });
    } else if (event.key === 'Enter') {
      event.preventDefault();
      if (routeListVisible && activeRouteIndex >= 0) chooseRoute(routeOptions[activeRouteIndex]!, true);
    } else if (event.key === 'Escape' && routePopupVisible) {
      event.preventDefault();
      closeRoutePicker();
    }
  }

  function chooseRoute(route: RouteOption, focusPath = false) {
    method = METHODS.includes(route.method) ? route.method : 'GET';
    path = route.path;
    routeQuery = route.path;
    routeLoaded = false;
    routeMappings = [];
    routePage = null;
    result = null;
    failure = null;

    const accept = preferredMediaType(route.mapping.produces);
    const contentType = BODY_METHODS.has(method) ? preferredMediaType(route.mapping.consumes) : '';
    suggestedHeaders = {
      ...(accept ? { Accept: accept } : {}),
      ...(BODY_METHODS.has(method) ? { 'Content-Type': contentType || 'application/json' } : {}),
    };
    if (BODY_METHODS.has(method) && (contentType || 'application/json').toLowerCase().includes('json') && !body.trim()) {
      body = '{}';
    }
    closeRoutePicker();
    if (focusPath) document.querySelector<HTMLInputElement>('input[aria-label="Path"]')?.focus();
  }

  function readHistory(): Entry[] {
    try {
      const v: unknown = JSON.parse(sessionStorage.getItem(HISTORY_KEY) ?? '[]');
      return Array.isArray(v) ? v.filter((e): e is Entry => typeof e?.method === 'string' && typeof e?.path === 'string') : [];
    } catch {
      return [];
    }
  }
  /** Method and path only: headers and bodies carry credentials and are never stored. */
  function remember(entry: Entry) {
    entry = { method: entry.method, path: entry.path.split('?')[0]! }; // a query string can carry a token
    history = [entry, ...history.filter((e) => e.method !== entry.method || e.path !== entry.path)].slice(0, 20);
    try {
      sessionStorage.setItem(HISTORY_KEY, JSON.stringify(history));
    } catch {
      // storage blocked or full: the history just is not kept
    }
  }

  function parseHeaders(text: string): Record<string, string> | string {
    const out: Record<string, string> = {};
    for (const line of text.split('\n')) {
      if (!line.trim()) continue;
      const i = line.indexOf(':');
      if (i < 1) return `"${line.trim()}" is not a header line. Write each as Name: value.`;
      out[line.slice(0, i).trim()] = line.slice(i + 1).trim();
    }
    return out;
  }

  function headersWithSuggestions(custom: Record<string, string>): Record<string, string> {
    const merged = new Map<string, { name: string; value: string }>();
    for (const [name, value] of [...Object.entries(suggestedHeaders), ...Object.entries(custom)]) {
      merged.set(name.toLowerCase(), { name, value });
    }
    return Object.fromEntries([...merged.values()].map(({ name, value }) => [name, value]));
  }

  export async function send() {
    if (why) return;
    const customHeaders = parseHeaders(headersText);
    failure = typeof customHeaders === 'string' ? customHeaders : null;
    if (typeof customHeaders === 'string') return;
    const headers = headersWithSuggestions(customHeaders);
    sending = true;
    result = null;
    remember({ method, path });
    try {
      result = await post<ProbeResult>('http-probe', { method, path, headers, ...(body ? { body } : {}) });
    } catch (e) {
      failure = errorText(e, 'The request could not be sent.');
    } finally {
      sending = false;
    }
  }

  const pretty = (text: string | null) => {
    if (!text) return '';
    try {
      return JSON.stringify(JSON.parse(text), null, 2);
    } catch {
      return text;
    }
  };
  const why = $derived(panelActionReason(panel));
</script>

<PanelShell {panel} title="HTTP Probe">
  <form class="form" onsubmit={(e) => (e.preventDefault(), void send())}>
    <div class="route-picker">
      <label for="probe-route-picker">Pick a declared route</label>
      <input
        id="probe-route-picker"
        type="search"
        role="combobox"
        aria-autocomplete="list"
        aria-expanded={routePopupVisible}
        aria-controls={routeListVisible ? 'probe-route-listbox' : undefined}
        aria-activedescendant={activeRouteOptionId}
        aria-describedby="probe-route-picker-hint"
        placeholder="Search routes by path, method, handler, or media type…"
        autocomplete="off"
        spellcheck="false"
        value={routeQuery}
        oninput={(event) => onRoutePickerInput(event.currentTarget.value)}
        onfocus={onRoutePickerFocus}
        onblur={closeRoutePicker}
        onkeydown={onRoutePickerKeydown}
      />
      <p id="probe-route-picker-hint" class="muted sm">Choose a route to fill its method and path. Replace any &#123;parameter&#125; placeholders before sending.</p>
      {#if routePopupVisible}
        <div class="route-popup">
          {#if routeError}
            <p class="notice danger" role="alert">{routeError}</p>
          {:else if routeLoading && !routeLoaded}
            <p class="route-status sm" role="status">Loading declared routes…</p>
          {:else if routeOptions.length === 0}
            <p class="route-status sm" role="status">{routeQuery.trim() ? `No declared routes match “${routeQuery.trim()}”.` : 'No declared HTTP mappings were reported.'}</p>
          {:else}
            <div id="probe-route-listbox" class="route-options" role="listbox" aria-label="Declared routes">
              {#each routeOptions as route, index (route.key)}
                <button
                  id={`probe-route-option-${index}`}
                  type="button"
                  class:active={activeRouteIndex === index}
                  role="option"
                  aria-selected={activeRouteIndex === index}
                  onmousedown={(event) => event.preventDefault()}
                  onclick={() => chooseRoute(route)}
                >
                  <span class="mono">{route.method} {route.path}</span>
                  {#if route.handler}<span class="muted sm">{route.handler}</span>{/if}
                </button>
              {/each}
            </div>
            <p class="route-status sm" role="status" aria-live="polite">
              {routePage && routePage.matched > routeOptions.length
                ? `${routeOptions.length} routes shown of ${routePage.matched} matching — type to narrow`
                : `${routeOptions.length} ${routeOptions.length === 1 ? 'route' : 'routes'}`}
            </p>
          {/if}
        </div>
      {/if}
    </div>
    <div class="line">
      <select aria-label="Method" bind:value={method}>{#each METHODS as m}<option>{m}</option>{/each}</select>
      <input id="probe-path" class="path" type="text" aria-label="Path" placeholder="/owners/1?expand=pets" bind:value={path} autocomplete="off" spellcheck="false" />
      <button type="submit" class="primary" disabled={!!why || sending || !path} title={why ?? undefined}>{sending ? 'Sending…' : 'Send'}</button>
    </div>
    <div class="areas">
      <label>Headers <span class="muted sm">one per line, Name: value. Route suggestions apply unless overridden. Never saved.</span>
        <textarea aria-label="Headers" rows="4" bind:value={headersText} spellcheck="false"></textarea></label>
      <label>Body <span class="muted sm">up to 64 KiB. Never saved.</span>
        <textarea aria-label="Body" rows="4" bind:value={body} spellcheck="false"></textarea></label>
    </div>
  </form>
  {#if history.length}
    <p class="history sm">
      <span class="muted">Recent</span>
      {#each history as e}<button class="link mono" onclick={() => ((method = e.method), (path = e.path))}>{e.method} {e.path}</button>{/each}
    </p>
  {/if}
  {#if failure}<p class="notice danger" role="alert">{failure}</p>{/if}
  {#if result}
    <section class="block result" aria-label="Response">
      <h2><span class="mono {statusFamilyClass(result.status)}">{result.status} {result.statusText}</span> <span class="muted">{result.durationMs} ms</span></h2>
      {#if result.error}<p class="danger" role="alert">{result.error}</p>{/if}
      {#each Object.entries(result.headers) as [name, value]}<div class="mono sm">{name}: {value}</div>{/each}
      {#if result.truncated}<p class="warn sm">Body truncated at 1 MiB.</p>{/if}
      <pre class="body mono">{pretty(result.body)}</pre>
    </section>
  {/if}
</PanelShell>

<style>
  .form, .history, .result { padding: var(--s3) var(--s4); }
  .route-picker { position: relative; padding: var(--s3) var(--s4) 0; }
  .route-picker > label { display: block; margin-bottom: var(--s1); }
  .route-picker > input { width: 100%; font-family: var(--mono); }
  .route-picker > p { margin: var(--s1) 0 0; }
  .route-popup { position: absolute; z-index: 2; top: calc(100% - var(--s2)); left: var(--s4); right: var(--s4); background: var(--bg); border: 1px solid var(--line); border-radius: var(--radius); }
  .route-options { max-height: 18rem; overflow-y: auto; padding: var(--s1); }
  .route-options button { display: flex; width: 100%; flex-direction: column; align-items: flex-start; gap: var(--s1); border: 0; border-radius: var(--radius); padding: var(--s2); text-align: left; background: transparent; color: inherit; cursor: pointer; }
  .route-options button.active, .route-options button:hover { background: var(--rail); }
  .route-status { border-top: 1px solid var(--line); padding: var(--s2) var(--s3); margin: 0; }
  .line { display: flex; gap: var(--s2); }
  .path { flex: 1; font-family: var(--mono); }
  .areas { display: grid; grid-template-columns: 1fr 1fr; gap: var(--s3); margin-top: var(--s3); }
  label { display: flex; flex-direction: column; gap: var(--s1); }
  textarea { font: 12.5px var(--mono); color: inherit; background: var(--bg); border: 1px solid var(--line); border-radius: var(--radius); padding: var(--s2); }
  .history { display: flex; flex-wrap: wrap; gap: var(--s3); margin: 0; }
  .result h2 { margin: var(--s6) 0 var(--s3); }
  pre.body { white-space: pre-wrap; overflow-wrap: anywhere; background: var(--rail); padding: var(--s2); margin: var(--s2) 0 0; }
</style>
