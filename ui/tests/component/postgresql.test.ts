// @vitest-environment jsdom
import { expect, it } from 'vitest';
import PostgreSql from '../../src/views/PostgreSql.svelte';
import { harness, json, panel, readOnly, until } from './support';

const NOT_READ_MESSAGE = 'The database has not been read yet. Run PostgreSQL read in the panel.';
const base = { localOnly: true, disclaimer: 'Read-only reads of pg_stat_* views.', truncated: false, diagnostics: [], limitations: [] };
const notRead = { ...base, status: 'NOT_READ', message: NOT_READ_MESSAGE, readAt: null, databasesRead: 0, databases: [] };
const section = (id: string, status: string, reason: string | null = null, hint: string | null = null, rowCount = 1) => ({
  id, title: id === 'statements' ? 'Statement ranking' : id === 'vacuum' ? 'Autovacuum health' : id, status, reason, hint, rowCount, truncated: false,
});
const database = (changes: object[]) => ({
  name: 'postgresql+psycopg://db:5432/app', databaseName: 'app', serverVersion: '16.4', serverMajorVersion: 16, role: 'app',
  monitoringRole: true, status: 'PARTIAL', message: null,
  vitalSigns: { databaseName: 'app', cacheHitRatio: 0.99, rollbackRatio: 0, connections: 3, maxConnections: 100, deadlocks: 0 },
  sections: [
    section('statements', 'SKIPPED', 'The pg_stat_statements extension is not installed on this server.', 'CREATE EXTENSION pg_stat_statements;', 0),
    section('vacuum', 'AVAILABLE', null, 'Autovacuum "due" is computed against the live-tuple estimate.'),
  ],
  sessions: [], statements: [], indexes: [], tables: [], vacuum: [], replication: null, settings: [], changes, truncated: false,
});
const read = (changes: object[]) => ({ ...base, status: 'PARTIAL', message: 'Some results are incomplete.', readAt: 1_761_811_200_000, databasesRead: 1, databases: [database(changes)] });
const h = harness();
const text = () => h.text().replace(/\s+/g, ' ');
const button = () => [...h.target.querySelectorAll('button')].find((b) => /Read PostgreSQL/.test(b.textContent ?? ''));

it('NOT_READ shows the message and the read button, and nothing reads on open', async () => {
  h.route((url) => (url === 'api/postgresql' ? json(200, notRead) : undefined));
  h.mount(PostgreSql, { panel: panel('postgresql') });
  await until(() => expect(text()).toContain(NOT_READ_MESSAGE));
  expect(button()).toBeDefined();
  expect(h.calls('POST')).toEqual([]);
});

it('a read renders each section with its status, reason and hint', async () => {
  let current: object = notRead;
  h.route((url, init) => {
    if (url === 'api/postgresql') return json(200, current);
    if (url === 'api/postgresql/read' && init?.method === 'POST') return json(200, (current = read([])));
    return undefined;
  });
  h.mount(PostgreSql, { panel: panel('postgresql') });
  await until(() => expect(button()).toBeDefined());
  button()!.click();
  await until(() => expect(text()).toContain('Statement ranking'));
  expect(text()).toContain('SKIPPED');
  expect(text()).toContain('The pg_stat_statements extension is not installed on this server.');
  expect(text()).toContain('CREATE EXTENSION pg_stat_statements;');
  expect(text()).toContain('Autovacuum "due" is computed against the live-tuple estimate.');
  expect(h.calls('POST')).toEqual(['api/postgresql/read']);
});

it('changes render only when the read carries them (the second read)', async () => {
  h.route((url) => (url === 'api/postgresql' ? json(200, read([])) : undefined));
  h.mount(PostgreSql, { panel: panel('postgresql') });
  await until(() => expect(text()).toContain('Statement ranking'));
  expect(text()).not.toContain('Since the previous read');
  h.route((url) => (url === 'api/postgresql' ? json(200, read([{ metric: 'Deadlocks', previous: '0', current: '3', direction: 'UP' }])) : undefined));
  h.mount(PostgreSql, { panel: panel('postgresql') });
  await until(() => expect(text()).toContain('Since the previous read'));
  expect(text()).toContain('Deadlocks');
  expect(text()).toContain('0 → 3');
});

it('read-only hides the read button and says why', async () => {
  h.route((url) => (url === 'api/postgresql' ? json(200, notRead) : undefined));
  h.mount(PostgreSql, { panel: readOnly('postgresql') });
  await until(() => expect(text()).toContain(NOT_READ_MESSAGE));
  expect(button()).toBeUndefined();
  expect(text()).toContain('Read-only: SHARPIT_READ_ONLY=true');
});
