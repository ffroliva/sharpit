<script lang="ts">
  import PanelShell from '../components/PanelShell.svelte';
  import { get } from '../lib/api';
  import { loader } from '../lib/load.svelte';
  import { isApplicationFrame } from '../lib/status';
  import type { ThreadReport } from '../lib/types';

  let tab = $state<'threads' | 'tasks'>('threads');
  let query = $state('');
  let state = $state('');
  let open = $state<string | null>(null);

  const report = loader(() => get<ThreadReport>('threads', { q: query, state, limit: 1000 }));
  $effect(() => {
    void report.reload();
  });

  const toggle = (key: string) => (open = open === key ? null : key);
  const asText = () => {
    const r = report.data;
    if (!r) return '';
    const stack = (name: string, frames: string[]) => `${name}\n${frames.map((f) => `    ${f}`).join('\n')}`;
    return tab === 'threads' ? r.threads.map((t) => stack(`${t.name} [${t.state}]`, t.stackTrace)).join('\n\n') : r.tasks.map((t) => stack(`${t.name} [${t.state}]`, t.stackTrace)).join('\n\n');
  };
  const copy = () => navigator.clipboard.writeText(asText());
</script>

{#snippet stack(frames: string[])}
  <ol class="frames mono sm">
    {#each frames as f}<li class:app={isApplicationFrame(f)}>{f}</li>{:else}<li class="muted">no stack shown</li>{/each}
  </ol>
{/snippet}

<PanelShell
  title="Threads"
  loading={report.loading}
  error={report.error}
  onretry={report.reload}
  count={report.data ? `${report.data.threads.length} threads, ${report.data.taskCount} tasks` : null}
>
  {#snippet controls()}
    <div class="grow">
      <label class="visually-hidden" for="threads-q">Filter threads</label>
      <input id="threads-q" class="panel-filter" type="search" placeholder="Filter by name, state or frame" bind:value={query} autocomplete="off" spellcheck="false" />
    </div>
    <button onclick={report.reload}>Refresh</button>
    <button onclick={copy}>Copy as text</button>
  {/snippet}
  {#if report.data}
    {@const r = report.data}
    <div role="tablist" class="tabs" aria-label="View">
      <button role="tab" aria-selected={tab === 'threads'} onclick={() => (tab = 'threads')}>Threads ({r.threads.length})</button>
      <button role="tab" aria-selected={tab === 'tasks'} onclick={() => (tab = 'tasks')}>Tasks ({r.taskCount})</button>
    </div>
    {#each r.warnings as w}<p class="notice warn">{w}</p>{/each}
    {#if tab === 'threads'}
      <p class="chips sm">
        {#each r.stateCounts as c}
          <button class:active={state === c.state} aria-pressed={state === c.state} onclick={() => (state = state === c.state ? '' : c.state)}>{c.state} {c.count}</button>
        {/each}
      </p>
      <p class="sm muted help">State is inferred from the stack. Waits with no Python frame of their own (time.sleep, socket.recv) read as RUNNABLE: these are C-level waits.</p>
      <ul class="rows">
        {#each r.threads as t (t.id)}
          <li>
            <button class="link mono" aria-expanded={open === `t${t.id}`} onclick={() => toggle(`t${t.id}`)}>{t.name}</button>
            <span class="tag {t.state === 'WAITING' ? 'muted' : 'ok'}">{t.state}</span>
            {#if t.daemon}<span class="sm muted">daemon</span>{/if}
            {#if open === `t${t.id}`}{@render stack(t.stackTrace)}{/if}
          </li>
        {/each}
      </ul>
    {:else if r.tasks.length === 0}
      <div class="empty"><p class="lead">No asyncio tasks</p><p>Tasks are read from the application's event loop once it has served a request.</p></div>
    {:else}
      <ul class="rows">
        {#each r.tasks as t, i}
          <li>
            <button class="link mono" aria-expanded={open === `k${i}`} onclick={() => toggle(`k${i}`)}>{t.name}</button>
            <span class="mono sm muted">{t.coroutine ?? ''}</span>
            <span class="tag muted">{t.state}</span>
            {#if t.request}<span class="sm">{t.request.method} {t.request.path} · {t.request.ageMs} ms</span>{/if}
            {#if open === `k${i}`}{@render stack(t.stackTrace)}{/if}
          </li>
        {/each}
      </ul>
    {/if}
  {/if}
</PanelShell>

<style>
  .tabs { display: flex; gap: var(--s1); padding: var(--s2) var(--s4) 0; }
  .tabs button[aria-selected='true'] { border-color: var(--accent); }
  .chips { display: flex; gap: var(--s2); padding: var(--s2) var(--s4) 0; margin: 0; }
  .chips button.active { border-color: var(--accent); background: var(--sel); }
  .help { margin: 0; padding: var(--s1) var(--s4); }
  .rows { list-style: none; margin: 0; padding: 0; }
  .rows li { padding: var(--s1) var(--s4); border-bottom: 1px solid var(--line); }
  .frames { margin: var(--s1) 0 0; padding-left: var(--s6); color: var(--muted); }
  .frames li { border: 0; padding: 0; }
  .frames li.app { color: var(--ink); font-weight: 600; }
</style>
