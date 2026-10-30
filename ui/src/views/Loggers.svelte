<script lang="ts">
  import ServerTable from '../components/ServerTable.svelte';
  import { ApiError, get, post } from '../lib/api';
  import type { Logger, Panel } from '../lib/types';

  let { panel, q = '' }: { panel: Panel; q?: string } = $props();

  // svelte-ignore state_referenced_locally (the view is remounted when the route's q changes)
  let query = $state(q);
  let levels = $state<string[]>([]);
  /** Rows changed in this session, by name: the server's answer replaces the paged row. */
  let changed = $state<Record<string, Logger>>({});
  let pending = $state<string | null>(null);
  let failure = $state<{ name: string; text: string } | null>(null);

  get<{ availableLevels: string[] }>('loggers', { limit: 1 }).then(
    (d) => (levels = d.availableLevels),
    () => {},
  );

  async function setLevel(logger: Logger, select: HTMLSelectElement) {
    const value = select.value;
    pending = logger.name;
    failure = null;
    try {
      const level = value === '' ? null : value; // null clears the configured level: the logger inherits again
      changed[logger.name] = await post<Logger>(`loggers/${encodeURIComponent(logger.name)}`, { level });
    } catch (e) {
      const body = e instanceof ApiError ? e.body : null;
      const text = typeof body === 'object' && body !== null && 'error' in body ? String(body.error) : 'The change failed.';
      failure = { name: logger.name, text };
      select.value = logger.configuredLevel ?? ''; // the change was not applied: show what is configured
    } finally {
      pending = null;
    }
  }
</script>

<ServerTable
  title="Loggers"
  path="loggers"
  key="loggers"
  bind:q={query}
  placeholder="Filter by logger name"
  noun="loggers"
  notice={panel.readOnly ? panel.readOnlyReason : null}
  columns={3}
>
  {#snippet head()}
    <tr><th>Logger</th><th>Effective</th><th>Configured</th></tr>
  {/snippet}
  {#snippet body(items: readonly Logger[])}
    {#each items as row (row.name)}
      {@const l = changed[row.name] ?? row}
      <tr>
        <td class="mono wrap">{l.name}</td>
        <td class="mono">{l.effectiveLevel ?? '—'}</td>
        <td>
          <label class="visually-hidden" for="level-{l.name}">Level for {l.name}</label>
          <select
            id="level-{l.name}"
            value={l.configuredLevel ?? ''}
            disabled={panel.readOnly || pending === l.name}
            title={panel.readOnly ? (panel.readOnlyReason ?? undefined) : undefined}
            onchange={(e) => setLevel(l, e.currentTarget)}
          >
            <option value="">inherit</option>
            {#each levels as level}<option value={level}>{level}</option>{/each}
          </select>
          {#if failure?.name === l.name}<span class="danger" role="alert">{failure.text}</span>{/if}
        </td>
      </tr>
    {/each}
  {/snippet}
</ServerTable>
