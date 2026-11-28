<script lang="ts">
  import PanelShell from '../components/PanelShell.svelte';
  import { errorText, get } from '../lib/api';
  import type {
    Panel,
    SideEffectsReport,
    SideEffectsRow,
    SideEffectsSensor,
    SideEffectsSensorReport,
  } from '../lib/types';

  let { panel }: { panel?: Panel | null } = $props();

  const GROUPS = [
    { id: 'network', label: 'Network' },
    { id: 'files-processes', label: 'Files and processes' },
    { id: 'environment', label: 'Environment' },
    { id: 'threads-leaks', label: 'Threads and leaks' },
    { id: 'blocking', label: 'Blocking' },
    { id: 'security-sinks', label: 'Security sinks' },
  ] as const;

  const SENSOR_ORDER = [
    'network',
    'files',
    'processes',
    'environment',
    'thread-activity',
    'thread-locals',
    'resources',
    'blocking',
    'security-sinks',
  ];

  interface ColumnConfig {
    target: string;
    count: string;
    parameter?: boolean;
    origin?: boolean;
    failed?: boolean;
    failedLabel?: string;
    exits?: boolean;
    time?: string;
    network?: boolean;
    threads?: boolean;
    resources?: boolean;
  }

  const SENSOR_COLUMNS: Record<string, ColumnConfig> = {
    processes: { target: 'Command', count: 'Starts', failed: true, exits: true, time: 'Lifetime (total / max ms)' },
    network: { target: 'Host / name', count: 'Count', failed: true, network: true, time: 'Time (total / max ms)' },
    files: { target: 'Path pattern', count: 'Operations', failed: true, origin: true, time: 'Time (total / max ms)' },
    environment: { target: 'Name', count: 'Reads', origin: true },
    'thread-activity': {
      target: 'Thread / executor',
      count: 'Started',
      origin: true,
      threads: true,
      failed: true,
      failedLabel: 'Reclaimed without shutdown',
      time: 'Executor lifetime (total / max ms)',
    },
    'thread-locals': { target: 'Thread local (holder)', count: 'Times left set', origin: true },
    resources: {
      target: 'Resource',
      count: 'Resources',
      origin: true,
      resources: true,
      failed: true,
      failedLabel: 'Reclaimed without close()',
    },
    blocking: {
      target: 'Event loop / operation',
      count: 'Calls',
      failed: true,
      failedLabel: 'Interrupted or failed',
      time: 'Blocked (total / max ms)',
    },
    'security-sinks': { target: 'Sink (value redacted) or check', count: 'Times', parameter: true, origin: true },
  };

  const EMPTY_TEXT: Record<string, string> = {
    processes: 'No process started yet in this run.',
    network: 'No connection, datagram, or name lookup recorded yet in this run.',
    files: 'No file has been opened yet in this run.',
    environment: 'No environment variable or system property has been read yet in this run.',
    blocking: 'No blocking call has started on an event loop yet in this run.',
    'thread-activity': 'No thread has been started and no executor created yet in this run.',
    'thread-locals': 'No thread local has been left set by a request or a job yet in this run.',
    resources: 'No resource has been left open after its request or reclaimed without close() in this run.',
    'security-sinks':
      'No request input has reached a command or a file path in this run.',
  };

  const SCOPE_LABELS: Record<string, string> = {
    route: 'Route',
    execution: 'Execution',
    startup: 'Startup',
    thread: 'Thread',
    unattributed: 'Unattributed',
    other: 'Other',
  };

  const SCOPE_ORDER: Record<string, number> = {
    route: 0,
    execution: 1,
    startup: 2,
    thread: 3,
    unattributed: 4,
    other: 99,
  };

  const ORIGIN_LABELS: Record<string, string> = {
    application: 'Application',
    library: 'Library',
    'class-path': 'Class path',
    jdk: 'JDK',
    logging: 'Logging',
    unknown: 'Unknown',
  };

  const RESOURCE_ORIGINS: Record<string, string> = {
    application: 'Opened by the application',
    library: 'Opened by a library the application called',
  };

  const LOCATION_LABELS: Record<string, string> = {
    'working-directory': 'Working directory',
    'temporary-directory': 'Temporary directory',
    home: 'Home',
    system: 'System',
    'java-home': 'Java home',
    elsewhere: 'Elsewhere',
  };

  const STATE_LABELS: Record<string, string> = {
    recording: 'Recording',
    installing: 'Installing',
    'self-test-failed': 'Self-test failed',
    disabled: 'Disabled',
    'not-claimed': 'Not claimed',
    unavailable: 'Unavailable',
    'not-available': 'Not available',
    'not-applicable': 'Not applicable',
  };

  const GROUPED_APART = new Set(['class-path', 'jdk', 'logging']);
  const THREADS_APART = new Set(['library', 'jdk']);

  let summary = $state<SideEffectsReport | null>(null);
  let loading = $state(true);
  let error = $state<string | null>(null);

  let activeTab = $state<string>(GROUPS[0].id);
  let sensorReports = $state<Record<string, SideEffectsSensorReport>>({});
  let sensorLoading = $state<Record<string, boolean>>({});
  let sensorErrors = $state<Record<string, string | null>>({});

  function groupIdFor(label: string): string {
    return (
      GROUPS.find((group) => group.label === label)?.id ??
      String(label || '')
        .toLowerCase()
        .replace(/\s+/g, '-')
    );
  }

  function sensorOrder(id: string): number {
    const index = SENSOR_ORDER.indexOf(id);
    return index < 0 ? SENSOR_ORDER.length : index;
  }

  const activeGroup = $derived(GROUPS.find((g) => g.id === activeTab) ?? GROUPS[0]);

  const sensorsByGroup = $derived.by(() => {
    const map = new Map<string, SideEffectsSensor[]>(GROUPS.map((g) => [g.id, []]));
    for (const s of summary?.sensors ?? []) {
      const gid = groupIdFor(s.group);
      if (!map.has(gid)) map.set(gid, []);
      map.get(gid)!.push(s);
    }
    for (const list of map.values()) {
      list.sort((a, b) => sensorOrder(a.id) - sensorOrder(b.id));
    }
    return map;
  });

  function sensorsForGroup(id: string): SideEffectsSensor[] {
    return sensorsByGroup.get(id) ?? [];
  }

  const recordingSensors = $derived(
    (summary?.sensors ?? []).filter((s) => s.state === 'recording').length,
  );

  function canLoadSensor(sensor: SideEffectsSensor): boolean {
    return sensor.state !== 'not-available';
  }

  function columnsOf(sensor: SideEffectsSensor): ColumnConfig {
    return SENSOR_COLUMNS[sensor.id] ?? { target: 'Target', count: 'Count', failed: true };
  }

  function scopeLabel(scope: string): string {
    return SCOPE_LABELS[scope] ?? scope ?? 'Unknown';
  }

  function attribution(row: SideEffectsRow): string {
    return row.attribution || (row.scope === 'other' ? 'Other activity' : '—');
  }

  function originLabel(origin: string | null, sensor: string): string {
    if (!origin) return '—';
    if (sensor === 'resources' && RESOURCE_ORIGINS[origin]) return RESOURCE_ORIGINS[origin];
    return ORIGIN_LABELS[origin] ?? origin;
  }

  function locationLabel(location: string | null): string {
    if (!location) return '';
    return LOCATION_LABELS[location] ?? location;
  }

  function stateOf(sensor: SideEffectsSensor): { label: string } {
    return { label: STATE_LABELS[sensor.state] ?? sensor.state ?? 'Unknown' };
  }

  function emptyText(sensor: SideEffectsSensor): string {
    return EMPTY_TEXT[sensor.id] ?? `No ${sensor.label.toLowerCase()} row has been recorded yet.`;
  }

  function formatNumber(n: number | bigint): string {
    return Number(n).toLocaleString();
  }

  function formatMillis(ms: number | null | undefined): string {
    if (ms == null) return '0 ms';
    return ms < 1000 ? `${ms} ms` : `${(ms / 1000).toFixed(1)} s`;
  }

  function formatLifetime(row: SideEffectsRow): string {
    return `${formatMillis(row.totalMillis)} / ${formatMillis(row.maxMillis)}`;
  }

  function formatTimestamp(epochMillis: number): string {
    if (!epochMillis) return '—';
    return new Date(epochMillis).toLocaleString();
  }

  function formatSeen(epochMillis: number): string {
    if (!epochMillis) return '—';
    const diffSec = Math.max(0, Math.floor((Date.now() - epochMillis) / 1000));
    if (diffSec < 60) return `${diffSec}s ago`;
    const diffMin = Math.floor(diffSec / 60);
    if (diffMin < 60) return `${diffMin}m ago`;
    const diffHours = Math.floor(diffMin / 60);
    return `${diffHours}h ago`;
  }

  function perRequest(row: SideEffectsRow): string {
    if (!row.requests) return '—';
    const average = row.count / row.requests;
    return Number.isInteger(average) ? formatNumber(average) : average.toFixed(1);
  }

  function groupedApart(row: SideEffectsRow): boolean {
    if (row.sensor === 'thread-locals') return row.origin === 'unknown';
    if (row.sensor === 'security-sinks') return row.origin === 'library';
    return row.sensor === 'thread-activity' ? THREADS_APART.has(row.origin ?? '') : GROUPED_APART.has(row.origin ?? '');
  }

  function apartLabel(sensor: SideEffectsSensor): string {
    if (sensor.id === 'thread-locals') return 'Holders not resolved';
    if (sensor.id === 'security-sinks') return 'Requested by libraries';
    return sensor.id === 'thread-activity' ? 'Libraries and the JDK' : 'Class path, JDK, and logging';
  }

  function sensorRows(report: SideEffectsSensorReport | null): SideEffectsRow[] {
    return [...(report?.rows ?? [])].sort((a, b) => {
      const byScope = (SCOPE_ORDER[a.scope] ?? 50) - (SCOPE_ORDER[b.scope] ?? 50);
      if (byScope !== 0) return byScope;
      return [a.attribution ?? '', a.target ?? '', a.callSite ?? '']
        .join('|')
        .localeCompare([b.attribution ?? '', b.target ?? '', b.callSite ?? ''].join('|'));
    });
  }

  function sections(report: SideEffectsSensorReport | null) {
    const rows = sensorRows(report);
    const own = rows.filter((r) => !groupedApart(r));
    const apart = rows.filter(groupedApart);
    const list = [];
    if (own.length || !apart.length) list.push({ id: 'own', apart: false, rows: own });
    if (apart.length) list.push({ id: 'apart', apart: true, rows: apart });
    return list;
  }

  function rowKey(row: SideEffectsRow): string {
    return [
      row.scope,
      row.attribution,
      row.sensor,
      row.kind,
      row.target,
      row.callSite,
      row.insideMethod,
      row.origin,
      row.location,
      row.client,
      row.capture,
      row.parameter,
      row.firstSeen,
    ].join('|');
  }

  async function loadSensor(sensor: SideEffectsSensor, append = false) {
    const existing = sensorReports[sensor.id];
    const shown = existing?.rows?.length || 0;
    const offset = append ? shown : 0;
    const limit = append ? 50 : Math.max(50, shown);
    sensorLoading[sensor.id] = true;
    try {
      const report = await get<SideEffectsSensorReport>('side-effects/sensor', {
        sensor: sensor.id,
        offset,
        limit,
      });
      sensorErrors[sensor.id] = null;
      sensorReports[sensor.id] = {
        ...report,
        rows: append ? [...(existing?.rows ?? []), ...(report.rows ?? [])] : (report.rows ?? []),
      };
    } catch (e) {
      sensorErrors[sensor.id] = errorText(e);
    } finally {
      sensorLoading[sensor.id] = false;
    }
  }

  async function loadGroupSensors(groupId: string) {
    const sensors = sensorsForGroup(groupId).filter(canLoadSensor);
    await Promise.all(
      sensors.map((s) => {
        if (sensorReports[s.id] || sensorLoading[s.id]) return Promise.resolve();
        return loadSensor(s, false);
      }),
    );
  }

  function selectTab(id: string) {
    if (activeTab === id) return;
    activeTab = id;
    void loadGroupSensors(id);
  }

  async function loadSummary() {
    loading = true;
    error = null;
    try {
      const res = await get<SideEffectsReport>('side-effects');
      summary = res;
      if (res.available) {
        await loadGroupSensors(activeTab);
      }
    } catch (e) {
      error = errorText(e);
    } finally {
      loading = false;
    }
  }

  loadSummary();
</script>

{#snippet tableSnippet(sensor: SideEffectsSensor, rows: SideEffectsRow[])}
  <div class="table-responsive">
    <table class="side-effects-table">
      <thead>
        <tr>
          <th scope="col">Attribution</th>
          <th scope="col">{columnsOf(sensor).target}</th>
          {#if columnsOf(sensor).parameter}
            <th scope="col">Parameter</th>
          {/if}
          {#if columnsOf(sensor).network}
            <th scope="col">Client</th>
            <th scope="col">Captured</th>
          {/if}
          <th scope="col">Call site</th>
          {#if columnsOf(sensor).origin}
            <th scope="col">Origin</th>
          {/if}
          <th scope="col" class="num">{columnsOf(sensor).count}</th>
          {#if columnsOf(sensor).threads}
            <th scope="col" class="num">Per request</th>
            <th scope="col" class="num">Left running</th>
            <th scope="col" class="num">Shut down</th>
          {/if}
          {#if columnsOf(sensor).resources}
            <th scope="col" class="num">Open after request</th>
            <th scope="col" class="num">Closed after request</th>
          {/if}
          {#if columnsOf(sensor).failed}
            <th scope="col" class="num">{columnsOf(sensor).failedLabel || 'Failed'}</th>
          {/if}
          {#if columnsOf(sensor).exits}
            <th scope="col" class="num">Exits</th>
          {/if}
          {#if columnsOf(sensor).network}
            <th scope="col" class="num">Connected</th>
          {/if}
          {#if columnsOf(sensor).time}
            <th scope="col" class="num">{columnsOf(sensor).time}</th>
          {/if}
          <th scope="col">Last seen</th>
          <th scope="col">Requests</th>
        </tr>
      </thead>
      <tbody>
        {#each rows as row (rowKey(row))}
          <tr class:side-effects-row-other={row.scope === 'other'}>
            <td>
              <span class="tag {row.scope === 'other' ? 'muted' : ''}">{scopeLabel(row.scope)}</span>
              <div class="sm muted mt-1">{attribution(row)}</div>
            </td>
            <td class="side-effects-target">
              <code>{row.target || '—'}</code>
              <div class="sm muted">
                {#if row.kind}<span>{row.kind}</span>{/if}
                {#if row.location}
                  <span class="tag side-effects-location ms-1">{locationLabel(row.location)}</span>
                {/if}
              </div>
              {#if row.detail}
                <div class="sm mt-1 side-effects-detail">{row.detail}</div>
              {/if}
            </td>
            {#if columnsOf(sensor).parameter}
              <td>
                {#if row.parameter}
                  <code class="side-effects-parameter">{row.parameter}</code>
                {:else}
                  <span class="muted">—</span>
                {/if}
              </td>
            {/if}
            {#if columnsOf(sensor).network}
              <td>{row.client || 'unrecognized'}</td>
              <td>{row.capture || '—'}</td>
            {/if}
            <td class="side-effects-call-site">
              {#if row.callSite}
                <code>{row.callSite}</code>
              {:else if row.sensor === 'thread-locals'}
                <span class="muted side-effects-set-during">set during the request</span>
              {:else}
                <span class="muted">—</span>
              {/if}
              {#if row.insideMethod}
                <div class="sm muted">inside {row.insideMethod}</div>
              {/if}
            </td>
            {#if columnsOf(sensor).origin}
              <td>
                {#if row.origin}
                  <span class="tag side-effects-origin">{originLabel(row.origin, row.sensor)}</span>
                {:else}
                  <span class="muted">—</span>
                {/if}
              </td>
            {/if}
            <td class="num">{formatNumber(row.count)}</td>
            {#if columnsOf(sensor).threads}
              <td class="num">{perRequest(row)}</td>
              <td class="num">{row.leftRunning || 0}</td>
              <td class="num">{row.kind === 'executor' ? formatNumber(row.completed) : '—'}</td>
            {/if}
            {#if columnsOf(sensor).resources}
              <td class="num">{row.leftRunning || 0}</td>
              <td class="num">{formatNumber(row.completed)}</td>
            {/if}
            {#if columnsOf(sensor).failed}
              <td class="num">{formatNumber(row.failed)}</td>
            {/if}
            {#if columnsOf(sensor).exits}
              <td class="num">
                {formatNumber(row.completed)}
                {#if row.nonZeroExits > 0}
                  <span class="tag warn ms-1">{row.nonZeroExits} non-zero</span>
                {/if}
                {#if row.lastExitStatus != null}
                  <span class="muted sm ms-1">last {row.lastExitStatus}</span>
                {/if}
              </td>
            {/if}
            {#if columnsOf(sensor).network}
              <td class="num">{row.kind === 'connect' ? formatNumber(row.completed) : '—'}</td>
            {/if}
            {#if columnsOf(sensor).time}
              <td class="num">{formatLifetime(row)}</td>
            {/if}
            <td>
              <span>{formatSeen(row.lastSeen)}</span>
              <div class="sm muted">{formatTimestamp(row.lastSeen)}</div>
            </td>
            <td>
              {#if row.exemplarRequestIds && row.exemplarRequestIds.length > 0}
                {#each row.exemplarRequestIds as id, idx}
                  <a href={`#/activity?request=${encodeURIComponent(id)}`}><code>{id}</code></a>{idx < row.exemplarRequestIds.length - 1 ? ', ' : ''}
                {/each}
              {:else}
                <span class="muted">—</span>
              {/if}
            </td>
          </tr>
        {/each}
      </tbody>
    </table>
  </div>
{/snippet}

<PanelShell
  title={panel?.title || 'Side Effects'}
  {loading}
  {error}
  onretry={loadSummary}
  panel={panel}
>
  {#if summary && !summary.available}
    <div class="empty side-effects-unavailable" role="alert">
      <p class="lead">Side Effects unavailable</p>
      <p>{summary.unavailableReason}</p>
    </div>
  {:else if summary}
    <section class="side-effects-summary" aria-labelledby="side-effects-headline">
      <h2 id="side-effects-headline">
        {formatNumber(recordingSensors)}
        {recordingSensors === 1 ? 'sensor is' : 'sensors are'} recording side effects
      </h2>
      <p class="muted sm">
        sharpit groups observations by route, thread family, target, and call site. Process rows show only the
        executable name, network rows a host and port, file rows a path pattern, and environment rows a name:
        arguments, bytes sent or received, file contents, and values are never recorded. Blocking rows show calls
        that blocked an event loop, reported, never refused. Thread activity rows show the threads and executors a
        route started, and those still running when its request ended; never what a thread holds.
      </p>
      {#if summary.limitations && summary.limitations.length > 0}
        <details class="side-effects-limitations">
          <summary>What these sensors cannot see ({summary.limitations.length})</summary>
          <ul>
            {#each summary.limitations as limitation}
              <li>{limitation}</li>
            {/each}
          </ul>
        </details>
      {/if}
    </section>

    <div role="tablist" class="tabs" aria-label="Side Effects sensor groups">
      {#each GROUPS as group}
        <button
          role="tab"
          id={`side-effects-tab-${group.id}`}
          aria-controls={`side-effects-panel-${group.id}`}
          aria-selected={activeTab === group.id}
          onclick={() => selectTab(group.id)}
        >
          {group.label}
        </button>
      {/each}
    </div>

    <div
      id={`side-effects-panel-${activeGroup.id}`}
      aria-labelledby={`side-effects-tab-${activeGroup.id}`}
      role="tabpanel"
      tabindex="0"
    >
      {#each sensorsForGroup(activeGroup.id) as sensor (sensor.id)}
        <section class="side-effects-sensor" aria-labelledby={`side-effects-sensor-${sensor.id}`}>
          <header class="sensor-head">
            <div>
              <h2 id={`side-effects-sensor-${sensor.id}`}>{sensor.label}</h2>
              {#if sensor.reason && sensor.state !== 'not-available'}
                <p class="sm muted">{sensor.reason}</p>
              {/if}
            </div>
            <span class="tag side-effects-state">{stateOf(sensor).label}</span>
          </header>

          {#if sensor.state === 'not-available'}
            <div class="side-effects-empty">
              <p class="muted">{sensor.reason || 'Not available in this version.'}</p>
            </div>
          {:else}
            {#if sensor.state !== 'recording'}
              <div class="side-effects-state-note notice warn">
                <strong>{stateOf(sensor).label}.</strong>
                {sensor.reason || 'This sensor is not recording rows right now.'}
              </div>
            {/if}

            {#if sensorErrors[sensor.id]}
              <p class="notice danger" role="alert">{sensorErrors[sensor.id]}</p>
            {:else if sensorLoading[sensor.id] && !sensorReports[sensor.id]}
              <div class="empty" role="status"><p class="muted">Loading…</p></div>
            {:else if sensorReports[sensor.id]}
              {#if !sensorRows(sensorReports[sensor.id]).length && sensor.state === 'recording'}
                <div class="side-effects-empty">
                  <p class="muted">{emptyText(sensor)}</p>
                </div>
              {:else if sensorRows(sensorReports[sensor.id]).length}
                {#each sections(sensorReports[sensor.id]) as sec (sec.id)}
                  {#if sec.apart}
                    <details class="side-effects-apart">
                      <summary class="sm">{apartLabel(sensor)} ({formatNumber(sec.rows.length)}), grouped apart</summary>
                      {@render tableSnippet(sensor, sec.rows)}
                    </details>
                  {:else}
                    {@render tableSnippet(sensor, sec.rows)}
                  {/if}
                {/each}
                {#if sensorReports[sensor.id]?.page?.hasMore}
                  <div class="more">
                    <button
                      class="side-effects-load-more"
                      disabled={sensorLoading[sensor.id]}
                      onclick={() => loadSensor(sensor, true)}
                    >
                      Load more
                    </button>
                  </div>
                {/if}
              {/if}
            {/if}
          {/if}
        </section>
      {/each}
    </div>
  {/if}
</PanelShell>

<style>
  .tabs {
    display: flex;
    gap: var(--s2);
    padding: var(--s2) var(--s4);
    border-bottom: 1px solid var(--line);
    overflow-x: auto;
  }
  .tabs button {
    border: 0;
    background: none;
    border-bottom: 2px solid transparent;
    border-radius: 0;
    padding: 0 var(--s2);
    height: 32px;
    font-weight: 500;
  }
  .tabs button[aria-selected='true'] {
    border-bottom-color: var(--accent);
    color: var(--accent);
    font-weight: 600;
  }
  .side-effects-summary {
    padding: var(--s4);
    border-bottom: 1px solid var(--line);
  }
  .side-effects-summary h2 {
    margin: 0 0 var(--s1);
  }
  .side-effects-sensor {
    padding: var(--s4);
    border-bottom: 1px solid var(--line);
  }
  .sensor-head {
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    margin-bottom: var(--s2);
  }
  .sensor-head h2 {
    margin: 0;
  }
  .side-effects-limitations {
    margin-top: var(--s3);
  }
  .side-effects-limitations summary {
    cursor: pointer;
    color: var(--muted);
  }
  .side-effects-limitations ul {
    margin: var(--s2) 0 0;
    padding-left: var(--s4);
  }
  .side-effects-apart {
    margin-top: var(--s3);
  }
  .side-effects-apart summary {
    cursor: pointer;
    color: var(--muted);
    margin-bottom: var(--s2);
  }
  .side-effects-table {
    margin-top: var(--s2);
  }
  .ms-1 {
    margin-left: var(--s1);
  }
  .mt-1 {
    margin-top: var(--s1);
  }
  .table-responsive {
    overflow-x: auto;
  }
</style>
