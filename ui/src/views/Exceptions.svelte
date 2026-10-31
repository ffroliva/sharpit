<script lang="ts">
  import PanelShell from '../components/PanelShell.svelte';
  import { del, errorText, get, post } from '../lib/api';
  import { loader } from '../lib/load.svelte';
  import { href } from '../lib/route';
  import { openStream } from '../lib/sse';
  import { clock, isApplicationFrame } from '../lib/status';
  import type { ExceptionDetail, ExceptionFrame, ExceptionGroup, Panel } from '../lib/types';

  let { panel }: { panel: Panel } = $props();

  const report = loader(() => get<{ groups: ExceptionGroup[]; totalExceptions: number }>('exceptions'));
  let selected = $state<string | null>(null);
  let detail = $state<ExceptionDetail | null>(null);
  let failure = $state<string | null>(null);

  async function loadDetail(id: string) {
    try {
      detail = await get<ExceptionDetail>(`exceptions/${encodeURIComponent(id)}`);
    } catch (e) {
      failure = errorText(e);
    }
  }
  function refresh() {
    void report.reload();
    if (selected) void loadDetail(selected);
  }
  $effect(() => {
    void report.reload();
    const stream = openStream('api/exceptions/stream', { onUpdate: refresh });
    return () => stream.close();
  });

  function toggle(id: string) {
    selected = selected === id ? null : id;
    detail = null;
    if (selected) void loadDetail(id);
  }
  async function act(run: () => Promise<unknown>) {
    failure = null;
    try {
      await run();
      refresh();
    } catch (e) {
      failure = errorText(e, 'The change failed.');
    }
  }
  const setStatus = (g: ExceptionGroup, status: string) => act(() => post(`exceptions/${encodeURIComponent(g.id)}/status`, { status }));
  const clear = () =>
    act(async () => {
      selected = null;
      detail = null;
      await del('exceptions');
    });
  const why = $derived(panel.readOnly ? (panel.readOnlyReason ?? 'Read-only') : undefined);
  const frameText = (f: ExceptionFrame) => `${f.declaringClass}.${f.methodName} (${f.fileName ?? '?'}:${f.lineNumber})`;
  const statusClass = { OPEN: 'danger', ACKNOWLEDGED: 'warn', RESOLVED: 'ok' } as const;
</script>

{#snippet frames(list: ExceptionFrame[])}
  <ol class="frames mono sm">
    {#each list as f}<li class:app={isApplicationFrame(f)}>{frameText(f)}</li>{/each}
  </ol>
{/snippet}

<PanelShell
  title="Exceptions"
  loading={report.loading}
  error={report.error}
  onretry={report.reload}
  notice={panel.readOnly ? why : null}
  count={report.data ? `${report.data.groups.length} groups, ${report.data.totalExceptions} total` : null}
>
  {#snippet controls()}
    <button class="clear" onclick={clear} disabled={panel.readOnly} title={why}>Clear all</button>
  {/snippet}
  {#if failure}<p class="notice danger" role="alert">{failure}</p>{/if}
  {#if report.data && report.data.groups.length === 0}
    <div class="empty"><p class="lead">No exceptions captured. That is good news.</p></div>
  {:else if report.data}
    <ul class="groups">
      {#each report.data.groups as g (g.id)}
        <li>
          <div class="row">
            <button class="link title mono" aria-expanded={selected === g.id} onclick={() => toggle(g.id)}>{g.exceptionClassName}</button>
            <span class="tag {statusClass[g.status]}">{g.status}</span>
            <span class="tag muted">{g.applicationException ? 'application' : 'framework'}</span>
            <span class="num">{g.count}×</span>
            <span class="sm muted">last {clock(g.lastSeen)}</span>
            {#if g.regressionCount}<span class="tag warn">regressed {g.regressionCount}×</span>{/if}
          </div>
          <div class="sm muted wrap">{g.message ?? ''}{g.lastRequestPath ? ` — ${g.lastRequestMethod} ${g.lastRequestPath}` : ''}</div>
          <div class="actions">
            <button disabled={panel.readOnly || g.status === 'ACKNOWLEDGED'} title={why} onclick={() => setStatus(g, 'ACKNOWLEDGED')}>Acknowledge</button>
            <button disabled={panel.readOnly || g.status === 'RESOLVED'} title={why} onclick={() => setStatus(g, 'RESOLVED')}>Resolve</button>
          </div>
          {#if selected === g.id}
            <section class="detail" aria-label="Detail for {g.exceptionClassName}">
              {#if !detail}<p class="muted">Loading…</p>
              {:else}
                <h2>Stack</h2>
                {@render frames(detail.frames)}
                {#each detail.causes as c}
                  <h2>Caused by <span class="mono">{c.exceptionClassName}</span></h2>
                  <p class="sm wrap">{c.message ?? ''}</p>
                  {@render frames(c.frames)}
                {/each}
                <h2>Last {detail.occurrences.length} occurrences</h2>
                <ul class="occ sm">
                  {#each detail.occurrences as o}
                    <li>
                      <span class="mono">{clock(o.timestamp)}</span> {o.source}
                      {#if o.traceId}<a href={href('activity', o.traceId)}>{o.requestMethod} {o.requestPath}</a>{:else}{o.requestMethod ?? ''} {o.requestPath ?? ''}{/if}
                    </li>
                  {/each}
                </ul>
              {/if}
            </section>
          {/if}
        </li>
      {/each}
    </ul>
  {/if}
</PanelShell>

<style>
  .groups, .occ { list-style: none; margin: 0; padding: 0; }
  .groups > li { padding: var(--s2) var(--s4); border-bottom: 1px solid var(--line); }
  .row { display: flex; gap: var(--s2); align-items: baseline; flex-wrap: wrap; }
  .title { font-size: 12.5px; }
  .wrap { overflow-wrap: anywhere; }
  .actions { display: flex; gap: var(--s2); margin-top: var(--s1); }
  .frames { margin: 0; padding-left: var(--s6); color: var(--muted); }
  .frames li.app { color: var(--ink); font-weight: 600; }
  .detail h2 { margin: var(--s3) 0 var(--s1); padding: 0; font-size: 13px; }
  .clear { margin-left: auto; }
</style>
