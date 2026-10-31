<script lang="ts">
  import PanelShell from '../components/PanelShell.svelte';
  import { openStream, type StreamState } from '../lib/sse';
  import { clock } from '../lib/status';
  import type { LogLine } from '../lib/types';

  const MAX_LINES = 2000;
  const RANK: Record<string, number> = { DEBUG: 10, INFO: 20, WARNING: 30, WARN: 30, ERROR: 40, CRITICAL: 50, FATAL: 50 };
  const levelClass = (level: string) => ((RANK[level] ?? 0) >= 40 ? 'danger' : (RANK[level] ?? 0) === 30 ? 'warn' : (RANK[level] ?? 20) < 20 ? 'muted' : '');

  let lines = $state<LogLine[]>([]);
  let conn = $state<StreamState>('connecting');
  let paused = $state(false);
  let level = $state('');
  let logger = $state('');
  let search = $state('');
  let tail = $state<HTMLElement>();
  let lastId = '';
  let stream: { close(): void } | null = null;

  function start(after?: string) {
    stream = openStream('api/log-tail/stream', {
      after,
      onState: (s) => (conn = s),
      onLine: (data, id) => {
        if (id) lastId = id;
        try {
          lines = [...lines, JSON.parse(data) as LogLine].slice(-MAX_LINES);
        } catch {
          // a malformed line is skipped; the stream goes on
        }
      },
    });
  }
  $effect(() => {
    start();
    return () => stream?.close();
  });

  function pause() {
    stream?.close();
    paused = true;
  }
  function resume() {
    paused = false;
    start(lastId || undefined);
  }

  const visible = $derived(
    lines.filter(
      (l) =>
        (!level || (RANK[l.level] ?? 0) >= (RANK[level] ?? 0)) &&
        (!logger || l.logger.toLowerCase().includes(logger.toLowerCase())) &&
        (!search || l.message.toLowerCase().includes(search.toLowerCase())),
    ),
  );
  const text = (l: LogLine) => `${clock(l.timestamp)} ${l.level} ${l.logger} ${l.message}`;
  const copy = () => navigator.clipboard.writeText(visible.map(text).join('\n'));

  // follow the tail while live; a paused view stays where the reader left it
  $effect(() => {
    void visible.length;
    if (!paused) tail?.lastElementChild?.scrollIntoView?.({ block: 'end' });
  });
</script>

<PanelShell title="Log Tail" count={`${visible.length} of ${lines.length} lines`}>
  {#snippet controls()}
    <select aria-label="Level" bind:value={level}>
      <option value="">All levels</option>
      {#each ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'] as l}<option value={l}>{l} and above</option>{/each}
    </select>
    <input type="search" aria-label="Logger" placeholder="Logger" bind:value={logger} autocomplete="off" spellcheck="false" />
    <div class="grow">
      <input class="panel-filter" type="search" aria-label="Search" placeholder="Search the buffer" bind:value={search} autocomplete="off" spellcheck="false" />
    </div>
    {#if paused}<button onclick={resume}>Resume</button>{:else}<button onclick={pause}>Pause</button>{/if}
    <button onclick={copy} disabled={visible.length === 0}>Copy visible</button>
  {/snippet}
  {#if conn === 'error'}
    <p class="notice danger" role="alert">Log stream unavailable (too many streams open, or the session expired). Retrying.</p>
  {/if}
  {#if lines.length === 0}
    <div class="empty">
      {#if conn === 'connecting'}
        <p class="muted" role="status">Connecting…</p>
      {:else if conn === 'connected'}
        <p class="lead">No log lines yet</p>
        <p>Only records that reach the root logger (or uvicorn's loggers) are shown.</p>
      {/if}
    </div>
  {:else}
    <ul class="tail" bind:this={tail} aria-label="Log lines">
      {#each visible as l}
        <li class="line mono {levelClass(l.level)}"><span class="muted">{clock(l.timestamp)}</span> {l.level} <span class="muted">{l.logger}</span> {l.message}</li>
      {/each}
    </ul>
  {/if}
</PanelShell>

<style>
  .tail { list-style: none; margin: 0; padding: var(--s2) var(--s4); }
  .line { white-space: pre-wrap; overflow-wrap: anywhere; line-height: 18px; }
</style>
