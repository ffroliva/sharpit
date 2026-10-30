<script lang="ts">
  import { ServerPage } from '../lib/paging';
  import { search, type Entry, type Hit } from '../lib/palette';
  import { href } from '../lib/route';
  import type { Panel } from '../lib/types';

  let { open = $bindable(false), panels }: { open?: boolean; panels: Panel[] } = $props();

  let dialog: HTMLDialogElement;
  let input = $state<HTMLInputElement>();
  let query = $state('');
  let active = $state(0);
  let extra = $state<Entry[]>([]);
  let indexState = $state<'idle' | 'loading' | 'ready' | 'partial'>('idle');

  const KINDS: Record<Entry['kind'], string> = { panel: 'Panels', logger: 'Loggers', config: 'Configuration' };
  const usable = (id: string) => panels.some((p) => p.id === id && p.available && p.enabled);

  // Loggers and config keys are fetched on the first open only: rendering the shell stays cheap.
  /** Per source; a palette over more keys than this is a filter's job. */
  const MAX_ROWS = 10000;

  async function loadIndex() {
    indexState = 'loading';
    const sources: [string, string, Entry['kind'], string][] = [
      ['loggers', 'loggers', 'logger', 'loggers'],
      ['config', 'properties', 'config', 'config'],
    ];
    const results = await Promise.allSettled(
      sources
        .filter(([, , , panel]) => usable(panel))
        .map(async ([path, key, kind]) => {
          const rows = await ServerPage.loadAll<{ name: string }>(path, key, MAX_ROWS);
          return rows.map((row): Entry => ({ kind, id: row.name, label: row.name }));
        }),
    );
    extra = results.flatMap((r) => (r.status === 'fulfilled' ? r.value : []));
    indexState = results.every((r) => r.status === 'fulfilled') ? 'ready' : 'partial';
  }

  const index: Entry[] = $derived([
    ...panels.map((p): Entry => ({ kind: 'panel', id: p.id, label: p.title })),
    ...extra,
  ]);

  // ranked hits, then grouped by kind in the order each kind first appears
  const groups = $derived.by(() => {
    const by = new Map<Entry['kind'], Hit[]>();
    for (const hit of search(index, query, 60)) {
      const list = by.get(hit.entry.kind);
      if (list) list.push(hit);
      else by.set(hit.entry.kind, [hit]);
    }
    return [...by];
  });
  const flat = $derived(groups.flatMap(([, hits]) => hits));

  $effect(() => {
    if (open && !dialog.open) {
      query = '';
      active = 0;
      dialog.showModal();
      input?.focus();
      if (indexState === 'idle') loadIndex();
    } else if (!open && dialog.open) dialog.close();
  });

  $effect(() => {
    query; // a new query restarts the selection at the best hit
    active = 0;
  });

  function pick(entry: Entry) {
    location.hash =
      entry.kind === 'panel' ? href(entry.id) : href(entry.kind === 'logger' ? 'loggers' : 'config', entry.id);
    open = false;
  }

  function onkeydown(event: KeyboardEvent) {
    if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
      event.preventDefault();
      const n = flat.length;
      if (n) active = (active + (event.key === 'ArrowDown' ? 1 : n - 1)) % n;
      document.getElementById(`opt-${active}`)?.scrollIntoView({ block: 'nearest' });
    } else if (event.key === 'Enter') {
      event.preventDefault();
      const hit = flat[active];
      if (hit) pick(hit.entry);
    }
  }

  /** The label split around the first case-insensitive occurrence of the query, for the accent highlight. */
  function parts(label: string): [string, string, string] {
    const q = query.trim().toLowerCase();
    const at = q ? label.toLowerCase().indexOf(q) : -1;
    return at < 0 ? [label, '', ''] : [label.slice(0, at), label.slice(at, at + q.length), label.slice(at + q.length)];
  }
</script>

<!-- svelte-ignore a11y_click_events_have_key_events, a11y_no_noninteractive_element_interactions -->
<dialog
  bind:this={dialog}
  class="palette"
  aria-label="Go to"
  onclose={() => (open = false)}
  onclick={(e) => e.target === dialog && (open = false)}
>
  <input
    bind:this={input}
    bind:value={query}
    {onkeydown}
    type="text"
    role="combobox"
    aria-expanded="true"
    aria-controls="palette-list"
    aria-activedescendant={flat.length ? `opt-${active}` : undefined}
    aria-label="Go to a panel, logger or config key"
    placeholder="Go to a panel, logger or config key"
    autocomplete="off"
    spellcheck="false"
  />
  <div id="palette-list" role="listbox" aria-label="Results">
    {#each groups as [kind, hits] (kind)}
      {@const offset = flat.indexOf(hits[0]!)}
      <div role="group" aria-labelledby="grp-{kind}">
        <div class="kind muted sm" id="grp-{kind}">{KINDS[kind]}</div>
        {#each hits as hit, i (hit.entry.kind + hit.entry.id)}
          {@const [before, match, after] = parts(hit.entry.label)}
          <!-- svelte-ignore a11y_click_events_have_key_events -->
          <div
            id="opt-{offset + i}"
            role="option"
            tabindex="-1"
            aria-selected={offset + i === active}
            class="opt"
            class:mono={kind !== 'panel'}
            onclick={() => pick(hit.entry)}
            onpointermove={() => (active = offset + i)}
          >
            {before}<mark>{match}</mark>{after}
          </div>
        {/each}
      </div>
    {:else}
      <p class="none muted">Nothing matches <code>{query}</code>. Try fewer letters.</p>
    {/each}
  </div>
  <footer class="muted sm">
    <span><kbd>↑</kbd> <kbd>↓</kbd> move · <kbd>Enter</kbd> open · <kbd>Esc</kbd> close</span>
    {#if indexState === 'loading'}<span>Loading loggers and config keys…</span>
    {:else if indexState === 'partial'}<span class="warn">Some loggers or config keys could not be loaded.</span>{/if}
  </footer>
</dialog>

<style>
  .palette {
    width: min(640px, calc(100vw - 32px)); max-height: min(520px, calc(100vh - 96px)); margin: 12vh auto auto;
    padding: 0; border: 1px solid var(--line); border-radius: var(--radius);
    background: var(--rail); color: var(--ink); box-shadow: 0 8px 24px oklch(0 0 0 / 0.18);
    flex-direction: column; overflow: hidden;
  }
  .palette[open] { display: flex; animation: palette-in var(--dur) var(--ease); }
  .palette::backdrop { background: oklch(0 0 0 / 0.25); }
  @keyframes palette-in { from { opacity: 0; transform: translateY(-6px); } }
  .palette input {
    width: 100%; height: 48px; padding: 0 var(--s4); border: 0; border-bottom: 1px solid var(--line); border-radius: 0;
    background: var(--bg); font-size: 16.5px; line-height: 24px; outline: none;
  }
  .palette input:focus-visible { box-shadow: inset 0 -2px 0 var(--accent); }
  [role='listbox'] { overflow: auto; flex: 1; padding-bottom: var(--s2); }
  .kind { padding: var(--s2) var(--s4) var(--s1); }
  .opt { padding: var(--s1) var(--s4); cursor: pointer; word-break: break-all; }
  .opt[aria-selected='true'] { background: var(--sel); box-shadow: inset 0 0 0 1px var(--accent); }
  mark { background: none; color: var(--accent); font-weight: 600; }
  .none { padding: var(--s3) var(--s4); margin: 0; }
  footer { display: flex; justify-content: space-between; gap: var(--s3); padding: var(--s2) var(--s4); border-top: 1px solid var(--line); }
  kbd { font: inherit; border: 1px solid var(--line); border-radius: 3px; padding: 0 3px; }
</style>
