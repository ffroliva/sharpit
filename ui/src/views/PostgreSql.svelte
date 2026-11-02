<script lang="ts">
  import PanelShell from '../components/PanelShell.svelte';
  import { errorText, get, post } from '../lib/api';
  import { loader } from '../lib/load.svelte';
  import { scannedWhen } from '../lib/format';
  import type { Panel } from '../lib/types';

  // BootUI 2.2.0 PostgresInsightReport (contract §5); only the fields this view reads are typed.
  interface Section { id: string; title: string; status: string; reason: string | null; hint: string | null; rowCount: number; truncated: boolean }
  interface Change { metric: string; previous: string; current: string; direction: string }
  interface Vitals { cacheHitRatio: number | null; rollbackRatio: number | null; connections: number | null; maxConnections: number | null; deadlocks: number | null }
  interface Database {
    name: string; databaseName: string | null; serverVersion: string | null; role: string | null; monitoringRole: boolean;
    status: string; message: string | null; vitalSigns: Vitals | null; sections: Section[]; changes: Change[];
  }
  interface Diagnostic { source: string; level: string; message: string | null }
  interface Report {
    disclaimer: string; status: string; message: string | null; readAt: number | null; databases: Database[];
    diagnostics: Diagnostic[]; limitations: string[];
  }

  let { panel }: { panel: Panel } = $props();

  const report = loader(() => get<Report>('postgresql'));
  $effect(() => void report.reload());

  const readOnly = $derived(panel.readOnly ? (panel.readOnlyReason ?? 'Read-only') : null);
  let reading = $state(false);
  let failure = $state<string | null>(null);

  /** The only call that connects to PostgreSQL; GET serves the last read. */
  async function read() {
    if (reading || readOnly) return;
    reading = true;
    failure = null;
    try {
      await post('postgresql/read');
      await report.reload();
    } catch (e) {
      failure = errorText(e, 'PostgreSQL could not be read.');
    } finally {
      reading = false;
    }
  }

  const percent = (v: number | null) => (v === null ? '—' : `${(v * 100).toFixed(1)}%`);
  const statusClass = (s: string) => (s === 'FAILED' || s === 'ERROR' ? 'danger' : s === 'SKIPPED' || s === 'PARTIAL' ? 'warn' : s === 'AVAILABLE' || s === 'READ' ? 'ok' : 'muted');
</script>

<PanelShell title={panel.title} loading={report.loading} error={report.error} onretry={report.reload} notice={readOnly}>
  {#snippet controls()}
    {#if !readOnly}
      <button class="primary push" onclick={read} disabled={reading} aria-busy={reading}>
        {reading ? 'Reading…' : 'Read PostgreSQL'}
      </button>
    {/if}
  {/snippet}
  {#if failure}<p class="notice danger" role="alert">{failure}</p>{/if}
  {#if report.data}
    {@const r = report.data}
    <p class="sm muted meta">
      <span class={statusClass(r.status)}>{r.status}</span>
      {#if r.readAt} · read {scannedWhen(r.readAt)}{/if} · {r.disclaimer}
    </p>
    {#if r.message}<p class="sm meta">{r.message}</p>{/if}
    {#each r.databases as db (db.name)}
      <section class="block" aria-label={db.name}>
        <h2 class="mono">{db.name}</h2>
        <p class="sm">
          <span class={statusClass(db.status)}>{db.status}</span>
          {#if db.databaseName} · database <span class="mono">{db.databaseName}</span>{/if}
          {#if db.serverVersion} · PostgreSQL {db.serverVersion}{/if}
          {#if db.role} · role <span class="mono">{db.role}</span>{#if !db.monitoringRole} <span class="tag warn">no pg_monitor</span>{/if}{/if}
        </p>
        {#if db.message}<p class="sm warn">{db.message}</p>{/if}
        {#if db.vitalSigns}
          {@const v = db.vitalSigns}
          <p class="sm">
            cache hit {percent(v.cacheHitRatio)} · rollback {percent(v.rollbackRatio)} ·
            connections {v.connections ?? '—'} / {v.maxConnections ?? '—'} · deadlocks {v.deadlocks ?? '—'}
          </p>
        {/if}
        {#if db.changes.length}
          <h3>Since the previous read</h3>
          <ul class="sm">
            {#each db.changes as c (c.metric)}
              <li>{c.metric}: <span class="mono">{c.previous} → {c.current}</span> <span class="tag muted">{c.direction}</span></li>
            {/each}
          </ul>
        {/if}
        <table>
          <thead><tr><th>Section</th><th>Status</th><th>Rows</th><th>Reason</th></tr></thead>
          <tbody>
            {#each db.sections as s (s.id)}
              <tr>
                <td>{s.title}</td>
                <td class={statusClass(s.status)}>{s.status}</td>
                <td class="mono">{s.rowCount}{#if s.truncated} <span class="tag warn">row limit</span>{/if}</td>
                <td class="sm">{s.reason ?? ''}{#if s.hint}<span class="muted hint">{s.hint}</span>{/if}</td>
              </tr>
            {/each}
          </tbody>
        </table>
      </section>
    {/each}
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
</style>
