<script lang="ts">
  import PanelShell from '../components/PanelShell.svelte';
  import { errorText, get, post } from '../lib/api';
  import { loader } from '../lib/load.svelte';
  import { scannedWhen } from '../lib/format';
  import type { Panel } from '../lib/types';

  // BootUI 2.2.0 MySqlInsightReport (contract §6); only the fields this view reads are typed.
  interface Section { id: string; title: string; status: string; reason: string | null; hint: string | null; rowCount: number; truncated: boolean }
  interface Change { metric: string; previous: string; current: string; direction: string }
  interface Metric { id: string; label: string; value: number | null; unit: string; scope: string; source: string }
  interface Capabilities { serverVersion: string | null; serverComment: string | null; isMariaDb: boolean; performanceSchema: boolean }
  type Row = Record<string, unknown>;
  interface DataSource {
    name: string; databaseName: string | null; status: string; message: string | null;
    capabilities: Capabilities; sections: Section[]; changes: Change[]; metrics: Metric[];
    sessions: Row[]; statements: Row[]; indexes: Row[]; tables: Row[]; lockWaits: Row[];
    replicationChannels: Row[]; settings: Row[]; truncated: boolean;
  }
  interface Diagnostic { source: string; level: string; message: string | null }
  interface Report {
    disclaimer: string; status: string; message: string | null; readStartedAt: number | null; readAt: number | null;
    dataSourcesRead: number; dataSources: DataSource[]; diagnostics: Diagnostic[]; limitations: string[];
    truncated: boolean;
  }

  let { panel }: { panel: Panel } = $props();

  const report = loader(() => get<Report>('mysql'));
  $effect(() => void report.reload());

  const readOnly = $derived(panel.readOnly ? (panel.readOnlyReason ?? 'Read-only') : null);
  let reading = $state(false);
  let latest = $state<Report | null>(null); // the POST answers the report it read: no second GET
  const shown = $derived(latest ?? report.data);
  let failure = $state<string | null>(null);

  /** The only call that connects to MySQL; GET serves the last read. */
  async function read() {
    if (reading || readOnly) return;
    reading = true;
    failure = null;
    try {
      latest = await post<Report>('mysql/read');
    } catch (e) {
      failure = errorText(e, 'MySQL could not be read.');
    } finally {
      reading = false;
    }
  }

  const rowLists = (ds: DataSource): [string, Row[]][] =>
    ([
      ['Sessions', ds.sessions], ['Statements', ds.statements], ['Indexes', ds.indexes],
      ['Tables', ds.tables], ['Lock waits', ds.lockWaits], ['Replication channels', ds.replicationChannels],
      ['Settings', ds.settings],
    ] as [string, Row[]][]).filter(([, rows]) => rows.length > 0);
  const cell = (v: unknown) => (v === null || v === undefined ? '—' : typeof v === 'object' ? JSON.stringify(v) : String(v));
  const statusClass = (s: string) => (s === 'FAILED' || s === 'ERROR' ? 'danger' : s === 'SKIPPED' || s === 'PARTIAL' ? 'warn' : s === 'AVAILABLE' || s === 'READ' ? 'ok' : 'muted');
</script>

<PanelShell title={panel.title} loading={report.loading} error={report.error} onretry={report.reload} notice={readOnly}>
  {#snippet controls()}
    {#if !readOnly}
      <button class="primary push" onclick={read} disabled={reading} aria-busy={reading}>
        {reading ? 'Reading…' : 'Read MySQL'}
      </button>
    {/if}
  {/snippet}
  {#if failure}<p class="notice danger" role="alert">{failure}</p>{/if}
  {#if shown}
    {@const r = shown}
    <p class="sm muted meta">
      <span class={statusClass(r.status)}>{r.status}</span>
      {#if r.readAt} · read {scannedWhen(r.readAt)}{/if} · {r.disclaimer}
    </p>
    {#if r.message}<p class="sm meta">{r.message}</p>{/if}
    {#each r.dataSources as ds (ds.name)}
      <section class="block" aria-label={ds.name}>
        <h2 class="mono">{ds.name}</h2>
        <p class="sm">
          <span class={statusClass(ds.status)}>{ds.status}</span>
          {#if ds.databaseName} · database <span class="mono">{ds.databaseName}</span>{/if}
          {#if ds.capabilities?.serverVersion} · {ds.capabilities.isMariaDb ? 'MariaDB' : 'MySQL'} {ds.capabilities.serverVersion}{/if}
          {#if ds.capabilities && !ds.capabilities.performanceSchema} <span class="tag warn">no performance_schema</span>{/if}
        </p>
        {#if ds.message}<p class="sm warn">{ds.message}</p>{/if}
        {#if ds.metrics?.length}
          <p class="sm">
            {#each ds.metrics as m, i (m.id)}
              {m.label}: <span class="mono">{m.value ?? '—'}{m.unit ? ` ${m.unit}` : ''}</span>{i < ds.metrics.length - 1 ? ' · ' : ''}
            {/each}
          </p>
        {/if}
        {#if ds.changes.length}
          <h3>Since the previous read</h3>
          <ul class="sm">
            {#each ds.changes as c (c.metric)}
              <li>{c.metric}: <span class="mono">{c.previous} → {c.current}</span> <span class="tag muted">{c.direction}</span></li>
            {/each}
          </ul>
        {/if}
        <table>
          <thead><tr><th>Section</th><th>Status</th><th>Rows</th><th>Reason</th></tr></thead>
          <tbody>
            {#each ds.sections as s (s.id)}
              <tr>
                <td>{s.title}</td>
                <td class={statusClass(s.status)}>{s.status}</td>
                <td class="mono">{s.rowCount}{#if s.truncated} <span class="tag warn">row limit</span>{/if}</td>
                <td class="sm">{s.reason ?? ''}{#if s.hint}<span class="muted hint">{s.hint}</span>{/if}</td>
              </tr>
            {/each}
          </tbody>
        </table>
        {#each rowLists(ds) as [title, rows] (title)}
          <h3>{title}</h3>
          <div class="rows">
            <table>
              <thead><tr>{#each Object.keys(rows[0]) as key (key)}<th>{key}</th>{/each}</tr></thead>
              <tbody>
                {#each rows as row, i (i)}
                  <tr>{#each Object.keys(rows[0]) as key (key)}<td class="sm mono">{cell(row[key])}</td>{/each}</tr>
                {/each}
              </tbody>
            </table>
          </div>
        {/each}
      </section>
    {/each}
    {#if r.limitations.length}
      <section class="block" aria-label="Limitations">
        <h2>Limitations</h2>
        <ul class="sm">
          {#each r.limitations as text, i (i)}<li>{text}</li>{/each}
        </ul>
      </section>
    {/if}
    {#if r.diagnostics.length}
      <section class="block" aria-label="Diagnostics">
        <h2>Diagnostics</h2>
        <ul class="sm">
          {#each r.diagnostics as d, i (i)}
            <li><span class={statusClass(d.level === 'ERROR' ? 'FAILED' : d.level === 'WARNING' ? 'SKIPPED' : 'muted')}>{d.level}</span> <span class="mono">{d.source}</span> {d.message ?? ''}</li>
          {/each}
        </ul>
      </section>
    {/if}
  {/if}
</PanelShell>

<style>
  .push { margin-left: auto; }
  .meta { margin: 0; padding: var(--s2) var(--s4); }
  section.block h2, section.block h3 { padding-bottom: var(--s1); }
  section.block > p, section.block > ul { margin: 0; padding: 0 var(--s4) var(--s2); }
  .hint { display: block; }
  .rows { overflow-x: auto; }
</style>
