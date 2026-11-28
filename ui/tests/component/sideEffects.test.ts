// @vitest-environment jsdom
import { expect, it } from 'vitest';
import SideEffects from '../../src/views/SideEffects.svelte';
import { harness, json, panel, until } from './support';

const GROUPS: [string, string][] = [
  ['network', 'Network'],
  ['files', 'Files and processes'],
  ['processes', 'Files and processes'],
  ['environment', 'Environment'],
  ['thread-activity', 'Threads and leaks'],
  ['thread-locals', 'Threads and leaks'],
  ['resources', 'Threads and leaks'],
  ['blocking', 'Blocking'],
  ['security-sinks', 'Security sinks'],
];

function sensor(id: string, group: string, state = 'not-available', extra: Record<string, unknown> = {}) {
  return {
    id,
    group,
    label: id,
    state,
    reason: state === 'not-available' ? 'Not available in this version.' : null,
    rows: 0,
    occurrences: 0,
    dropped: 0,
    hooks: [],
    toggle: null,
    ...extra,
  };
}

function sensors(overrides: Record<string, Record<string, unknown>> = {}) {
  return GROUPS.map(([id, group]) => sensor(id, group, undefined, overrides[id] ?? {})).map((entry) => ({
    ...entry,
    state: entry.state ?? 'not-available',
    reason: entry.reason ?? (entry.state === 'not-available' ? 'Not available in this version.' : null),
  }));
}

function summary(overrides: Record<string, unknown> = {}) {
  const { sensors: sensorOverrides = {}, ...rest } = overrides as any;
  return {
    available: true,
    unavailableReason: null,
    sensors: sensors(sensorOverrides),
    limitations: ['Only operations that pass through installed hooks are visible.'],
    ...rest,
  };
}

function sensorReport(id: string, rows: unknown[] = [], overrides: Record<string, unknown> = {}) {
  return {
    available: true,
    unavailableReason: null,
    sensor: sensor(
      id,
      id === 'processes' || id === 'files'
        ? 'Files and processes'
        : id === 'security-sinks'
          ? 'Security sinks'
          : 'Network',
      'recording',
    ),
    rows,
    page: { total: rows.length, matched: rows.length, offset: 0, limit: 50, returned: rows.length, hasMore: false },
    limitations: [],
    ...overrides,
  };
}

function row(overrides: Record<string, unknown> = {}) {
  return {
    scope: 'route',
    attribution: 'GET /api/export',
    sensor: 'processes',
    kind: 'process',
    target: 'python',
    callSite: 'demo.export:run_report',
    insideMethod: null,
    origin: null,
    location: null,
    count: 3,
    failed: 1,
    completed: 2,
    nonZeroExits: 1,
    lastExitStatus: 2,
    totalMillis: 165,
    maxMillis: 150,
    firstSeen: Date.now() - 120_000,
    lastSeen: Date.now() - 45_000,
    exemplarRequestIds: ['00000000000000aa', '00000000000000bb'],
    client: null,
    capture: null,
    capturedBy: null,
    leftRunning: 0,
    requests: 0,
    parameter: null,
    detail: null,
    ...overrides,
  };
}

const h = harness();
const tab = (name: string) =>
  [...h.target.querySelectorAll<HTMLElement>('[role="tab"]')].find((t) => t.textContent?.trim() === name)!;

it('shows security-sinks rows with the parameter name and the fact, never as a vulnerability', async () => {
  // adapted from: SideEffects.test.js:873
  const sink = row({
    sensor: 'security-sinks',
    kind: 'command',
    target: 'sh -c {name}',
    location: null,
    parameter: 'name',
    detail:
      'Request input reached this command unchanged: the value of `name` appeared as an argument. Check that it is validated. Seen in one request so far.',
    count: 1,
    failed: 0,
    completed: 0,
    nonZeroExits: 0,
    lastExitStatus: null,
  });

  h.route((url) => {
    if (url === 'api/side-effects') {
      return json(200, summary({ sensors: { 'security-sinks': { state: 'recording', reason: null } } }));
    }
    if (url.startsWith('api/side-effects/sensor') && url.includes('sensor=security-sinks')) {
      return json(200, sensorReport('security-sinks', [sink]));
    }
    return undefined;
  });

  h.mount(SideEffects, { panel: panel('side-effects', { title: 'Side Effects' }) });

  await until(() => expect(tab('Security sinks')).toBeDefined());
  tab('Security sinks')?.click();

  await until(() => expect(h.target.querySelector('.side-effects-table')).not.toBeNull());
  const table = h.target.querySelector('.side-effects-table')!;
  expect(table.textContent).toContain('Parameter');
  expect(h.target.querySelector('.side-effects-parameter')?.textContent).toBe('name');
  expect(table.textContent).toContain('sh -c {name}');
  expect(h.target.querySelector('.side-effects-detail')?.textContent).toContain('Check that it is validated.');
  expect(table.textContent?.toLowerCase()).not.toContain('vulnerab');
  expect(table.textContent).not.toContain('Failed');
});

it('renders the sensor tabs and not-available sensors without sensor fetches', async () => {
  // adapted from: SideEffects.test.js:153
  h.route((url) => {
    if (url === 'api/side-effects') {
      return json(200, summary());
    }
    return undefined;
  });

  h.mount(SideEffects, { panel: panel('side-effects', { title: 'Side Effects' }) });

  await until(() => expect(h.target.querySelectorAll('[role="tab"]')).toHaveLength(6));
  const tabTexts = [...h.target.querySelectorAll<HTMLElement>('[role="tab"]')].map((t) => t.textContent?.trim());
  expect(tabTexts).toEqual([
    'Network',
    'Files and processes',
    'Environment',
    'Threads and leaks',
    'Blocking',
    'Security sinks',
  ]);
  expect(h.text()).toContain('Not available in this version.');

  for (const label of ['Files and processes', 'Environment', 'Threads and leaks', 'Blocking', 'Security sinks']) {
    tab(label).click();
    await until(() => expect(h.text()).toContain('Not available in this version.'));
  }

  const sensorCalls = h.calls('GET').filter((url) => url.includes('side-effects/sensor'));
  expect(sensorCalls).toEqual([]);
});

it('shows file rows by pattern and location', async () => {
  // adapted from: SideEffects.test.js:757
  const report = row({
    sensor: 'files',
    kind: 'write',
    target: './target/report-{n}.csv',
    origin: 'application',
    location: 'working-directory',
    callSite: 'app.writer:write',
    completed: 0,
    nonZeroExits: 0,
    lastExitStatus: null,
  });

  h.route((url) => {
    if (url === 'api/side-effects') {
      return json(
        200,
        summary({
          sensors: {
            files: { state: 'recording', reason: null },
            processes: { state: 'recording', reason: null },
          },
        }),
      );
    }
    if (url.startsWith('api/side-effects/sensor') && url.includes('sensor=files')) {
      return json(200, sensorReport('files', [report]));
    }
    if (url.startsWith('api/side-effects/sensor') && url.includes('sensor=processes')) {
      return json(200, sensorReport('processes', []));
    }
    return undefined;
  });

  h.mount(SideEffects, { panel: panel('side-effects', { title: 'Side Effects' }) });

  await until(() => expect(tab('Files and processes')).toBeDefined());
  tab('Files and processes')?.click();

  await until(() => expect(h.target.querySelector('.side-effects-table')).not.toBeNull());
  const table = h.target.querySelector('.side-effects-table')!;
  expect(table.textContent).toContain('Path pattern');
  expect(table.textContent).toContain('Operations');
  expect(table.textContent).toContain('./target/report-{n}.csv');
  expect(h.target.querySelector('.side-effects-location')?.textContent).toBe('Working directory');
  expect(h.target.querySelector('.side-effects-origin')?.textContent).toBe('Application');
});

it('renders row text as text, never as HTML', async () => {
  // scenario row 25
  const xssRow = row({
    sensor: 'security-sinks',
    kind: 'command',
    target: '<img src=x onerror=alert(1)>',
    parameter: 'name',
    detail: 'Detail with <script>alert(2)</script>',
  });

  h.route((url) => {
    if (url === 'api/side-effects') {
      return json(200, summary({ sensors: { 'security-sinks': { state: 'recording', reason: null } } }));
    }
    if (url.startsWith('api/side-effects/sensor') && url.includes('sensor=security-sinks')) {
      return json(200, sensorReport('security-sinks', [xssRow]));
    }
    return undefined;
  });

  h.mount(SideEffects, { panel: panel('side-effects', { title: 'Side Effects' }) });

  await until(() => expect(tab('Security sinks')).toBeDefined());
  tab('Security sinks')?.click();
  await until(() => expect(h.target.querySelector('.side-effects-table')).not.toBeNull());

  expect(h.target.querySelector('img')).toBeNull();
  expect(h.target.querySelector('script')).toBeNull();
  expect(h.text()).toContain('<img src=x onerror=alert(1)>');
  expect(h.text()).toContain('<script>alert(2)</script>');
});

it('shows the empty state and the limitations', async () => {
  h.route((url) => {
    if (url === 'api/side-effects') {
      return json(
        200,
        summary({
          sensors: {
            processes: { state: 'recording', reason: null },
            files: { state: 'recording', reason: null },
          },
          limitations: [
            'Only operations that pass through installed hooks are visible.',
            'Second limitation text.',
          ],
        }),
      );
    }
    if (url.startsWith('api/side-effects/sensor') && url.includes('sensor=files')) {
      return json(200, sensorReport('files', []));
    }
    if (url.startsWith('api/side-effects/sensor') && url.includes('sensor=processes')) {
      return json(200, sensorReport('processes', []));
    }
    return undefined;
  });

  h.mount(SideEffects, { panel: panel('side-effects', { title: 'Side Effects' }) });

  await until(() => expect(h.target.querySelector('.side-effects-limitations')).not.toBeNull());
  const limitations = h.target.querySelector('.side-effects-limitations')!;
  expect(limitations.querySelector('summary')?.textContent).toContain('What these sensors cannot see (2)');
  const lis = [...limitations.querySelectorAll('li')].map((li) => li.textContent);
  expect(lis).toEqual([
    'Only operations that pass through installed hooks are visible.',
    'Second limitation text.',
  ]);

  await until(() => expect(tab('Files and processes')).toBeDefined());
  tab('Files and processes')?.click();
  await until(() => expect(h.text()).toContain('No file has been opened yet in this run.'));
  expect(h.text()).toContain('No process started yet in this run.');
});

it('names only what the security sinks tab checks when it has no rows', async () => {
  h.route((url) => {
    if (url === 'api/side-effects') {
      return json(200, summary({ sensors: { 'security-sinks': { state: 'recording', reason: null } } }));
    }
    if (url.startsWith('api/side-effects/sensor') && url.includes('sensor=security-sinks')) {
      return json(200, sensorReport('security-sinks', []));
    }
    return undefined;
  });

  h.mount(SideEffects, { panel: panel('side-effects', { title: 'Side Effects' }) });

  await until(() => expect(tab('Security sinks')).toBeDefined());
  tab('Security sinks')?.click();

  await until(() =>
    expect(h.text()).toContain('No request input has reached a command or a file path in this run.'),
  );
  expect(h.text()).not.toContain('SQL text');
});
