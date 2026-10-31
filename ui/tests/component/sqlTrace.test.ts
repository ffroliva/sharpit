// @vitest-environment jsdom
import { expect, it } from 'vitest';
import SqlTrace from '../../src/views/SqlTrace.svelte';
import { FakeEventSource, harness, json, panel, readOnly, until } from './support';

const entry = (over: object = {}) => ({
  id: 1, timestamp: '2026-10-31T12:00:00.000Z', sql: 'SELECT id FROM pets WHERE owner_id = ?', statementType: 'PREPARED',
  category: 'SELECT', durationMillis: 3, success: true, errorMessage: null, affectedRows: null, batchSize: 1,
  connectionId: '0x1', thread: 'MainThread', slow: false, parameters: [], traceId: 'req1', callSite: 'app:owners:42', ...over,
});
const report = (over: object = {}) => ({
  available: true, unavailableReason: null, capturing: true, captureParameters: false, bufferSize: 200, totalCaptured: 2,
  slowQueryThresholdMillis: 100, dataSources: ['sqlite:///sample.db'],
  stats: { total: 2, slow: 1, failed: 1, evicted: 0 },
  entries: [entry(), entry({ id: 2, sql: 'SELECT py_sleep(?)', durationMillis: 300, slow: true, success: false, errorMessage: 'no such function' })],
  topStatements: [{ sql: 'SELECT id FROM pets WHERE owner_id = ?', category: 'SELECT', executions: 6, totalDurationMillis: 18, maxDurationMillis: 4, potentialNPlusOne: true, callSites: ['app:owners:42'] }],
  warnings: [], ...over,
});
const h = harness();
const text = () => h.text().replace(/\s+/g, ' ');
const button = (name: RegExp) => [...h.target.querySelectorAll('button')].find((b) => name.test(b.textContent ?? ''))!;
const tab = (name: string) => [...h.target.querySelectorAll('[role="tab"]')].find((b) => b.textContent?.includes(name)) as HTMLElement;

it('Recent: statements with duration, slow and failed badges, call site and a request link', async () => {
  h.route((url) => (url === 'api/sql-trace' ? json(200, report()) : undefined));
  h.mount(SqlTrace, { panel: panel('sql-trace') });
  expect(text()).toContain('Loading');
  await until(() => expect(text()).toContain('SELECT py_sleep(?)'));
  expect(text()).toContain('slow');
  expect(text()).toContain('failed');
  expect(text()).toContain('no such function');
  expect(text()).toContain('app:owners:42');
  expect(h.target.querySelector('a[href="#/activity?q=req1"]')).not.toBeNull();
  expect(FakeEventSource.last.url).toBe('api/sql-trace/stream');
});

it('Top statements: executions, totals and the N+1 badge', async () => {
  h.route((url) => (url === 'api/sql-trace' ? json(200, report()) : undefined));
  h.mount(SqlTrace, { panel: panel('sql-trace') });
  await until(() => expect(text()).toContain('SELECT py_sleep(?)'));
  tab('Top statements').click();
  await until(() => expect(text()).toContain('N+1'));
  expect(text()).toContain('6');
  expect(tab('Top statements').getAttribute('aria-selected')).toBe('true');
});

it('Pause posts recording false; Clear posts clear', async () => {
  let capturing = true;
  h.route((url, init) => {
    if (url === 'api/sql-trace') return json(200, report({ capturing }));
    if (url === 'api/sql-trace/recording' && init?.method === 'POST') return json(200, report({ capturing: (capturing = JSON.parse(String(init.body)).enabled) }));
    if (url === 'api/sql-trace/clear' && init?.method === 'POST') return json(200, report({ entries: [], topStatements: [] }));
    return undefined;
  });
  h.mount(SqlTrace, { panel: panel('sql-trace') });
  await until(() => expect(text()).toContain('SELECT py_sleep(?)'));
  button(/^Pause/).click();
  await until(() => expect(text()).toContain('Recording is paused'));
  const recording = h.fetchMock.mock.calls.find(([u]) => u === 'api/sql-trace/recording')!;
  expect(JSON.parse(String(recording[1]!.body))).toEqual({ enabled: false });
  button(/^Clear/).click();
  await until(() => expect(h.calls('POST')).toContain('api/sql-trace/clear'));
});

it('empty: SQLAlchemy not imported shows the reason', async () => {
  h.route((url) => (url === 'api/sql-trace' ? json(200, report({ available: false, unavailableReason: 'SQLAlchemy is not imported by this application', entries: [], topStatements: [] })) : undefined));
  h.mount(SqlTrace, { panel: panel('sql-trace') });
  await until(() => expect(text()).toContain('SQLAlchemy is not imported by this application'));
});

it('empty: no SQL yet', async () => {
  h.route((url) => (url === 'api/sql-trace' ? json(200, report({ entries: [], topStatements: [], totalCaptured: 0 })) : undefined));
  h.mount(SqlTrace, { panel: panel('sql-trace') });
  await until(() => expect(text()).toContain('No SQL captured yet'));
});

it('read-only: Pause and Clear disabled with the reason', async () => {
  h.route((url) => (url === 'api/sql-trace' ? json(200, report()) : undefined));
  h.mount(SqlTrace, { panel: readOnly('sql-trace') });
  await until(() => expect(text()).toContain('SELECT py_sleep(?)'));
  expect(text()).toContain('Read-only: SHARPIT_READ_ONLY=true');
  expect(button(/^Pause/).disabled).toBe(true);
  expect(button(/^Clear/).disabled).toBe(true);
});

it('shows the error state', async () => {
  h.route(() => json(500, { error: 'x' }));
  h.mount(SqlTrace, { panel: panel('sql-trace') });
  await until(() => expect(h.target.querySelector('[role="alert"]')?.textContent).toContain('Could not load'));
});
