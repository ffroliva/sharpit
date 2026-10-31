<script lang="ts">
  import ServerTable from '../components/ServerTable.svelte';
  import { errorText, get, post } from '../lib/api';
  import type { Logger, Panel } from '../lib/types';

  let { panel, q = '' }: { panel: Panel; q?: string } = $props();

  // svelte-ignore state_referenced_locally (the view is remounted when the route's q changes)
  let query = $state(q);
  let levels = $state<string[]>([]);
  /** The server's answer for a row just changed, shown until the reload of the visible rows lands. */
  let changed = $state<Record<string, Logger>>({});
  let pending = $state<string | null>(null);
  let failure = $state<{ name: string; text: string } | null>(null);
  let table = $state<{ reload(): Promise<void> }>();

  // NOTSET is Python's spelling of "inherit", which the first option already offers
  get<{ availableLevels: string[] }>('loggers', { limit: 1 }).then(
    (d) => (levels = d.availableLevels.filter((l) => l !== 'NOTSET')),
    () => {},
  );

  async function setLevel(logger: Logger, select: HTMLSelectElement) {
    const value = select.value;
    // busy is aria-disabled, not disabled: a disabled select would drop keyboard focus to <body>
    if (pending || panel.readOnly) {
      select.value = logger.configuredLevel ?? '';
      return;
    }
    pending = logger.name;
    failure = null;
    try {
      const level = value === '' ? null : value; // null clears the configured level: the logger inherits again
      changed[logger.name] = await post<Logger>(`loggers/${encodeURIComponent(logger.name)}`, { level });
      // descendants inherit the new level: reload the visible rows so their Effective column is true again
      await table?.reload();
      changed = {};
    } catch (e) {
      failure = { name: logger.name, text: errorText(e, 'The change failed.') };
      select.value = logger.configuredLevel ?? ''; // the change was not applied: show what is configured
    } finally {
      pending = null;
    }
  }
</script>

<ServerTable
  bind:this={table}
  title="Loggers"
  path="loggers"
  key="loggers"
  bind:q={query}
  placeholder="Filter by logger name"
  noun="loggers"
  notice={panel.readOnly ? panel.readOnlyReason : null}
  columns={3}
  cols={['', '7rem', '15rem']}
>
  {#snippet head()}
    <tr><th>Logger</th><th>Effective</th><th>Configured</th></tr>
  {/snippet}
  {#snippet body(items: readonly Logger[])}
    {#each items as row (row.name)}
      {@const l = changed[row.name] ?? row}
      {@const explicit = l.configuredLevel !== null}
      <tr class:explicit>
        <td class="mono wrap">{l.name}</td>
        <!-- an explicit level is the interesting one: ink; an inherited one recedes -->
        <td class="mono" class:muted={!explicit} title={explicit ? 'Set on this logger' : 'Inherited from a parent logger'}>
          {l.effectiveLevel ?? '—'}
        </td>
        <td>
          <label class="visually-hidden" for="level-{l.name}">Level for {l.name}</label>
          <select
            id="level-{l.name}"
            value={l.configuredLevel ?? ''}
            disabled={panel.readOnly}
            aria-disabled={pending === l.name || undefined}
            title={panel.readOnly ? (panel.readOnlyReason ?? undefined) : undefined}
            onchange={(e) => setLevel(l, e.currentTarget)}
          >
            <option value="">{explicit ? 'inherit from parent' : `inherit (${l.effectiveLevel ?? 'NOTSET'})`}</option>
            {#each levels as level}<option value={level}>{level}</option>{/each}
          </select>
          {#if failure?.name === l.name}<span class="danger" role="alert">{failure.text}</span>{/if}
        </td>
      </tr>
    {/each}
  {/snippet}
</ServerTable>

<style>
  tr.explicit td:first-child { font-weight: 600; }
  select { width: 11rem; } /* one width whatever the option text: the column never jumps */
  select[aria-disabled='true'] { cursor: progress; }
</style>
