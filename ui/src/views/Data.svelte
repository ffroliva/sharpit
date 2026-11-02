<script lang="ts">
  import PanelShell from '../components/PanelShell.svelte';
  import { get } from '../lib/api';
  import { loader } from '../lib/load.svelte';
  import type { Panel } from '../lib/types';

  interface Relationship { name: string; target: string; lazy: string | null }
  interface Repository {
    beanName: string;
    repositoryInterface: string;
    idType: string | null;
    storeModule: string;
    queryMethodCount: number | null;
    fragmentCount: number | null;
    table: string | null;
    relationships: Relationship[] | null;
  }
  interface Report { springDataPresent: boolean; total: number; unavailableReason?: string | null; repositories: Repository[] }
  interface Method { name: string; signature: string }
  interface Detail { methods: Method[]; unavailableReason: string | null }

  let { panel }: { panel: Panel } = $props();

  const report = loader(() => get<Report>('data/repositories'));
  let open = $state<string | null>(null);
  let detail = $state<Detail | null>(null);
  let detailError = $state<string | null>(null);

  $effect(() => {
    void report.reload();
  });

  async function toggle(name: string) {
    detail = null;
    detailError = null;
    if (open === name) {
      open = null;
      return;
    }
    open = name;
    try {
      const loaded = await get<Detail>(`data/repositories/${encodeURIComponent(name)}`);
      if (open === name) detail = loaded;
    } catch {
      if (open === name) detailError = 'Could not load this class';
    }
  }
  const count = (v: number | null) => (v === null ? '—' : String(v));
</script>

<PanelShell
  title={panel.title}
  loading={report.loading}
  error={report.error}
  onretry={report.reload}
  count={report.data ? `${report.data.total} ${report.data.total === 1 ? 'class' : 'classes'}` : null}
>
  {#if report.data}
    {#if report.data.unavailableReason}
      <p class="muted note">{report.data.unavailableReason}</p>
    {/if}
    {#if report.data.repositories.length === 0}
      <div class="empty">
        <p class="lead">No mapped classes</p>
        <p>Pass your declarative base so sharpit can list your models:</p>
        <pre class="mono">sharpit.install(app, models=Base)</pre>
      </div>
    {:else}
      <table>
        <thead>
          <tr><th>Class</th><th>Table</th><th>Id</th><th>Methods</th><th>Fragments</th></tr>
        </thead>
        <tbody>
          {#each report.data.repositories as r (r.repositoryInterface)}
            <tr>
              <td>
                <button class="row mono" aria-expanded={open === r.beanName} onclick={() => void toggle(r.beanName)}>{r.beanName}</button>
              </td>
              <td class="mono">{r.table ?? '—'}</td>
              <td class="mono">{r.idType ?? '—'}</td>
              <td>{count(r.queryMethodCount)}</td>
              <td>{count(r.fragmentCount)}</td>
            </tr>
            {#if open === r.beanName}
              <tr class="detail">
                <td colspan="5">
                  <p class="sm muted mono">{r.repositoryInterface} · {r.storeModule}</p>
                  {#if detailError}
                    <p role="alert">{detailError}</p>
                  {:else if r.relationships === null || detail?.unavailableReason}
                    <p class="muted">{detail?.unavailableReason ?? 'Mappers are not configured yet: the app has not run a query'}</p>
                  {:else if r.relationships.length === 0}
                    <p class="muted">No relationships</p>
                  {:else}
                    <ul>
                      {#each r.relationships as rel (rel.name)}
                        <li><span class="mono">{rel.name}</span> → <span class="mono">{rel.target}</span> <span class="muted">lazy: {rel.lazy ?? '—'}</span></li>
                      {/each}
                    </ul>
                    {#if detail}
                      <ul class="sm muted mono">
                        {#each detail.methods as m (m.name)}<li>{m.signature}</li>{/each}
                      </ul>
                    {/if}
                  {/if}
                </td>
              </tr>
            {/if}
          {/each}
        </tbody>
      </table>
    {/if}
  {/if}
</PanelShell>

<style>
  .note { padding: var(--s3) var(--s4); margin: 0; }
  table { width: 100%; border-collapse: collapse; }
  th, td { text-align: left; padding: var(--s2) var(--s4); border-bottom: 1px solid var(--line); }
  .row { background: none; border: 0; padding: 0; color: var(--accent); cursor: pointer; font: inherit; }
  .detail td { background: var(--surface, transparent); }
  ul { margin: 0; padding-left: var(--s4); }
  pre { margin: 0; }
</style>
