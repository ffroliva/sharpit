<script lang="ts">
  import PanelShell from '../components/PanelShell.svelte';
  import { del, errorText, get } from '../lib/api';
  import { loader } from '../lib/load.svelte';
  import type { Panel } from '../lib/types';

  let { panel }: { panel: Panel } = $props();

  type Summary = {
    traceId: string; rootSpanName: string; httpPath: string | null; services: string[];
    startEpochNanos: number; endEpochNanos: number; durationNanos: number; spanCount: number; hasError: boolean; hasAi: boolean;
  };
  type Report = { enabled: boolean; unavailableReason?: string | null; retained: number; capacity: number; traces: Summary[] };
  type Attribute = { key: string; type: string; value: string | null };
  type Span = {
    traceId: string; spanId: string; parentSpanId: string | null; name: string; kind: string; serviceName: string | null;
    scope: string | null; startEpochNanos: number; endEpochNanos: number; durationNanos: number; statusCode: string;
    statusMessage: string | null; attributes: Attribute[]; events: { name: string; timeOffsetNanos: number; attributes: Attribute[] }[];
  };
  type Detail = { traceId: string; spans: Span[] };

  const report = loader(() => get<Report>('traces'));
  $effect(() => void report.reload());
  let detail = $state<Detail | null>(null);
  let failure = $state<string | null>(null);
  let detailRequest = 0;

  // nanoseconds (the contract's unit) shown as milliseconds
  const ms = (nanos: number) => `${(nanos / 1e6).toFixed(nanos < 1e7 ? 2 : 1)} ms`;
  const why = $derived(panel.readOnly ? (panel.readOnlyReason ?? 'Read-only') : undefined);

  async function open(t: Summary) {
    const request = ++detailRequest;
    failure = null;
    try {
      const loaded = await get<Detail>(`traces/${encodeURIComponent(t.traceId)}`);
      if (request === detailRequest) detail = loaded;
    } catch (e) {
      if (request === detailRequest) failure = errorText(e, 'The trace could not be loaded.');
    }
  }
  async function clear() {
    const request = ++detailRequest;
    failure = null;
    try {
      await del('traces');
      if (request === detailRequest) {
        detail = null;
        report.reload();
      }
    } catch (e) {
      if (request === detailRequest) failure = errorText(e, 'Clearing failed.');
    }
  }
  // waterfall geometry: each bar's offset and width as a share of the whole trace
  const bounds = (spans: Span[]) => {
    const start = Math.min(...spans.map((s) => s.startEpochNanos));
    const end = Math.max(...spans.map((s) => s.endEpochNanos));
    return { start, total: Math.max(end - start, 1) };
  };
</script>

<PanelShell
  title={panel.title}
  loading={report.loading}
  error={report.error}
  onretry={report.reload}
  notice={panel.readOnly ? why : null}
  count={report.data?.enabled ? `${report.data.retained} traces (capacity ${report.data.capacity} spans)` : null}
>
  {#snippet controls()}
    <button onclick={clear} disabled={panel.readOnly} title={why}>Clear</button>
  {/snippet}
  {#if failure}<p class="notice danger" role="alert">{failure}</p>{/if}
  {#if report.data}
    {#if !report.data.enabled}
      <div class="empty"><p class="lead">Traces unavailable</p><p>{report.data.unavailableReason}</p></div>
    {:else if detail}
      {@const b = bounds(detail.spans)}
      <p><button onclick={() => { detailRequest++; detail = null; }}>Back to traces</button> <span class="mono sm">{detail.traceId}</span></p>
      <table class="waterfall">
        <thead><tr><th>Span</th><th>Service</th><th>Duration</th><th>Timeline</th></tr></thead>
        <tbody>
          {#each detail.spans as s (s.spanId)}
            <tr class:error={s.statusCode === 'ERROR'}>
              <td>
                <span class="sm muted">{s.kind}</span> {s.name}
                {#if s.statusMessage}<p class="status-message">{s.statusMessage}</p>{/if}
              </td>
              <td>{s.serviceName ?? ''}</td>
              <td>{ms(s.durationNanos)}</td>
              <td class="lane">
                <span
                  class="bar"
                  style:left={`${((s.startEpochNanos - b.start) / b.total) * 100}%`}
                  style:width={`${Math.max((s.durationNanos / b.total) * 100, 0.5)}%`}
                  title={s.statusMessage ?? s.statusCode}
                ></span>
              </td>
            </tr>
            {#if s.attributes.length}
              <tr><td colspan="4">
                <dl class="attrs mono sm">
                  {#each s.attributes as a (a.key)}<dt>{a.key}</dt><dd>{a.value ?? ''}</dd>{/each}
                </dl>
              </td></tr>
            {/if}
            {#each s.events as e (`${s.spanId}:${e.timeOffsetNanos}:${e.name}`)}
              <tr class="event"><td colspan="4">
                <strong>{e.name}</strong> <span class="sm muted">+{ms(e.timeOffsetNanos)}</span>
                {#if e.attributes.length}
                  <dl class="attrs mono sm">
                    {#each e.attributes as a (`${e.name}:${a.key}`)}<dt>{a.key}</dt><dd>{a.value ?? ''}</dd>{/each}
                  </dl>
                {/if}
              </td></tr>
            {/each}
          {/each}
        </tbody>
      </table>
    {:else if report.data.traces.length === 0}
      <div class="empty"><p class="lead">No traces recorded yet.</p></div>
    {:else}
      <table>
        <thead><tr><th>Root span</th><th>Path</th><th>Services</th><th>Spans</th><th>Duration</th></tr></thead>
        <tbody>
          {#each report.data.traces as t (t.traceId)}
            <tr class:error={t.hasError}>
              <td><button class="link" onclick={() => open(t)}>{t.rootSpanName}</button>{#if t.hasAi} <span class="sm muted">AI</span>{/if}</td>
              <td class="mono">{t.httpPath ?? ''}</td>
              <td>{t.services.join(', ')}</td>
              <td>{t.spanCount}</td>
              <td>{ms(t.durationNanos)}</td>
            </tr>
          {/each}
        </tbody>
      </table>
    {/if}
  {/if}
</PanelShell>

<style>
  tr.error td:first-child { color: var(--danger); }
  .lane { position: relative; min-width: 12rem; }
  .bar { position: absolute; top: 30%; height: 40%; background: var(--accent); border-radius: 2px; }
  .attrs { display: grid; grid-template-columns: max-content 1fr; gap: 0 var(--s4); margin: 0; }
  .attrs dd { margin: 0; overflow-wrap: anywhere; }
  .status-message { margin: var(--s1) 0 0; }
  .link { background: none; border: 0; padding: 0; color: inherit; text-decoration: underline; cursor: pointer; }
</style>
