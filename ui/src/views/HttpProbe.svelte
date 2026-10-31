<script lang="ts">
  import PanelShell from '../components/PanelShell.svelte';
  import { errorText, post } from '../lib/api';
  import { ServerPage } from '../lib/paging';
  import { statusFamilyClass } from '../lib/status';
  import type { Mapping, Panel, ProbeResult } from '../lib/types';

  let { panel, q = '' }: { panel: Panel; q?: string } = $props();

  const HISTORY_KEY = 'sharpit.probe.history';
  const METHODS = ['GET', 'HEAD', 'POST', 'PUT', 'PATCH', 'DELETE', 'OPTIONS'];
  type Entry = { method: string; path: string };

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
  let routes = $state<string[]>([]);
  let history = $state<Entry[]>(readHistory());

  // route suggestions: the patterns of the app's own routes
  ServerPage.loadAll<Mapping>('mappings/flat', 'mappings', 1000).then(
    (rows) => (routes = [...new Set(rows.map((r) => r.pattern))].sort()),
    () => {},
  );

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
    history = [entry, ...history.filter((e) => e.method !== entry.method || e.path !== entry.path)].slice(0, 20);
    sessionStorage.setItem(HISTORY_KEY, JSON.stringify(history));
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

  async function send() {
    const headers = parseHeaders(headersText);
    failure = typeof headers === 'string' ? headers : null;
    if (typeof headers === 'string') return;
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
  const why = $derived(panel.readOnly ? (panel.readOnlyReason ?? 'Read-only') : undefined);
</script>

<PanelShell title="HTTP Probe" notice={panel.readOnly ? why : null}>
  <form class="form" onsubmit={(e) => (e.preventDefault(), void send())}>
    <div class="line">
      <select aria-label="Method" bind:value={method}>{#each METHODS as m}<option>{m}</option>{/each}</select>
      <input class="path" type="text" aria-label="Path" list="probe-routes" placeholder="/owners/1?expand=pets" bind:value={path} autocomplete="off" spellcheck="false" />
      <datalist id="probe-routes">{#each routes as r}<option value={r}></option>{/each}</datalist>
      <button type="submit" class="primary" disabled={panel.readOnly || sending || !path} title={why}>{sending ? 'Sending…' : 'Send'}</button>
    </div>
    <div class="areas">
      <label>Headers <span class="muted sm">one per line, Name: value. Never saved.</span>
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
  .line { display: flex; gap: var(--s2); }
  .path { flex: 1; font-family: var(--mono); }
  .areas { display: grid; grid-template-columns: 1fr 1fr; gap: var(--s3); margin-top: var(--s3); }
  label { display: flex; flex-direction: column; gap: var(--s1); }
  textarea { font: 12.5px var(--mono); color: inherit; background: var(--bg); border: 1px solid var(--line); border-radius: var(--radius); padding: var(--s2); }
  .history { display: flex; flex-wrap: wrap; gap: var(--s3); margin: 0; }
  .result h2 { padding: 0; margin-bottom: var(--s2); }
  pre.body { white-space: pre-wrap; overflow-wrap: anywhere; background: var(--rail); padding: var(--s2); margin: var(--s2) 0 0; }
</style>
