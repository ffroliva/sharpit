<script lang="ts">
  import PanelShell from '../components/PanelShell.svelte';
  import { errorText, get, post } from '../lib/api';
  import { loader } from '../lib/load.svelte';
  import { scannedWhen } from '../lib/format';
  import type { AlembicReport, Panel } from '../lib/types';

  let { panel }: { panel: Panel } = $props();

  const NOT_READ = '(not read yet)'; // the server's name for the file-side history before any database read
  const report = loader(() => get<AlembicReport>('alembic/migrations'));
  $effect(() => void report.reload());

  const readOnly = $derived(panel.readOnly ? (panel.readOnlyReason ?? 'Read-only') : null);
  let reading = $state(false);
  let failure = $state<string | null>(null);

  /** The only call that connects to the database; GET never does. */
  async function readVersion() {
    if (reading || readOnly) return;
    reading = true;
    failure = null;
    try {
      await post('alembic/refresh');
      await report.reload();
    } catch (e) {
      failure = errorText(e, 'The database version could not be read.');
    } finally {
      reading = false;
    }
  }

  const stateClass = (state: string) => (state === 'Pending' ? 'warn' : state === 'Missing' ? 'danger' : state === 'Success' ? 'ok' : 'muted');
</script>

<PanelShell
  title="Alembic"
  loading={report.loading}
  error={report.error}
  onretry={report.reload}
  notice={readOnly}
  count={report.data?.alembicPresent ? `${report.data.total} revisions` : null}
>
  {#snippet controls()}
    <button class="primary push" onclick={readVersion} disabled={!!readOnly || reading} aria-busy={reading} title={readOnly ?? undefined}>
      {reading ? 'Reading…' : 'Read database version'}
    </button>
  {/snippet}
  {#if failure}<p class="notice danger" role="alert">{failure}</p>{/if}
  {#if report.data}
    {@const r = report.data}
    {#if !r.alembicPresent}
      <div class="empty">
        <p class="lead">No Alembic configuration found</p>
        <p>sharpit looked for <code>{r.configPath ?? 'alembic.ini'}</code>. Point it at your ini file with
          <code>SHARPIT_ALEMBIC_CONFIG</code> or <code>install(app, alembic_config="alembic.ini")</code>.</p>
      </div>
    {:else}
      <p class="sm muted meta">
        <span class="mono">{r.configPath}</span> · {r.heads.length === 1 ? 'head' : 'heads'} <span class="mono">{r.heads.join(', ') || '—'}</span>
        {#if r.heads.length > 1}<span class="tag warn">{r.heads.length} heads: the history has branches</span>{/if}
        · sharpit never runs migrations
      </p>
      {#each r.databases as db (db.name)}
        <section class="block" aria-label={db.name}>
          {#if db.name === NOT_READ}
            <h2>Database version not read yet</h2>
            {#if db.unavailableReason}
              <p class="sm">{db.unavailableReason}</p>
              <pre class="mono">sharpit.install(app, engines=[engine])</pre>
            {:else}
              <p class="sm muted">The history below comes from the revision files. Press “Read database version” to see which are applied.</p>
            {/if}
          {:else}
            <h2 class="mono">{db.name}</h2>
            <p class="sm">
              current <span class="mono">{db.currentVersion ?? 'none'}</span> · {db.applied} applied ·
              <span class={db.pending ? 'warn' : ''}>{db.pending} pending</span>
              {#if db.checkedAt} · read {scannedWhen(db.checkedAt)}{/if}
            </p>
            {#if db.unavailableReason}<p class="sm warn">{db.unavailableReason}</p>{/if}
          {/if}
          <table>
            <thead><tr><th>Revision</th><th>Description</th><th>State</th><th>Script</th></tr></thead>
            <tbody>
              {#each db.migrations as m (m.version)}
                <tr class:pending={m.state === 'Pending'}>
                  <td class="mono">{m.version}{#if r.heads.includes(m.version)} <span class="tag muted">head</span>{/if}</td>
                  <td>{m.description ?? ''}</td>
                  <td class={stateClass(m.state)}>{m.state}</td>
                  <td class="mono sm muted">{m.script ?? '—'}</td>
                </tr>
              {/each}
            </tbody>
          </table>
        </section>
      {/each}
    {/if}
  {/if}
</PanelShell>

<style>
  .push { margin-left: auto; }
  .meta { margin: 0; padding: var(--s2) var(--s4); }
  section.block h2 { padding-bottom: var(--s1); }
  section.block > p, pre { margin: 0; padding: 0 var(--s4) var(--s2); }
  tr.pending td { background: var(--sel); }
</style>
