// @vitest-environment jsdom
import { expect, it } from 'vitest';
import MySql from '../../src/views/MySql.svelte';
import { harness, json, panel, readOnly, until } from './support';

const NOT_READ_MESSAGE = 'No MySQL read has run. Run MySQL read explicitly to contact existing JDBC datasources.';
const base = {
  localOnly: true,
  disclaimer: 'Explicit, bounded READ ONLY observations of MySQL metadata.',
  truncated: false,
  diagnostics: [],
  limitations: [],
};
const notRead = {
  ...base,
  status: 'NOT_READ',
  message: NOT_READ_MESSAGE,
  readStartedAt: null,
  readAt: null,
  dataSourcesRead: 0,
  dataSources: [],
};

const section = (id: string, status: string, reason: string | null = null, hint: string | null = null, rowCount = 1) => ({
  id,
  title: id === 'statements' ? 'Top normalized statements' : id === 'sessions' ? 'Active sessions' : id,
  status,
  reason,
  hint,
  rowCount,
  truncated: false,
});

const dataSource = (changes: object[]) => ({
  name: 'mysql+pymysql://db:3306/app',
  databaseName: 'app',
  status: 'PARTIAL',
  message: null,
  capabilities: {
    serverVersion: '8.4.0',
    serverComment: 'MySQL Community Server',
    isMariaDb: false,
    performanceSchema: true,
  },
  sections: [
    section('statements', 'AVAILABLE', null, null, 10),
    section('lock-waits', 'AVAILABLE', null, null, 0),
  ],
  sessions: [],
  statements: [{ schema_name: 'app', digest: 'abc', digest_text: 'SELECT 1', count_star: 1 }],
  indexes: [],
  tables: [],
  lockWaits: [],
  replicationChannels: [],
  metrics: [{ id: 'threads_connected', label: 'Threads connected', value: 5, unit: '', scope: 'GLOBAL', source: 'STATUS' }],
  settings: [],
  changes,
  truncated: false,
});

const read = (changes: object[]) => ({
  ...base,
  status: 'PARTIAL',
  message: 'Some results are incomplete.',
  readStartedAt: 1_761_811_200_000,
  readAt: 1_761_811_201_000,
  dataSourcesRead: 1,
  dataSources: [dataSource(changes)],
});

const h = harness();
const text = () => h.text().replace(/\s+/g, ' ');
const button = () => [...h.target.querySelectorAll('button')].find((b) => /Read MySQL/.test(b.textContent ?? ''));

it('NOT_READ shows the message and the read button, and nothing reads on open', async () => {
  h.route((url) => (url === 'api/mysql' ? json(200, notRead) : undefined));
  h.mount(MySql, { panel: panel('mysql') });
  await until(() => expect(text()).toContain(NOT_READ_MESSAGE));
  expect(button()).toBeDefined();
  expect(h.calls('POST')).toEqual([]);
});

it('a read renders each section with its status, reason and hint', async () => {
  let current: object = notRead;
  h.route((url, init) => {
    if (url === 'api/mysql') return json(200, current);
    if (url === 'api/mysql/read' && init?.method === 'POST') return json(200, (current = read([])));
    return undefined;
  });
  h.mount(MySql, { panel: panel('mysql') });
  await until(() => expect(button()).toBeDefined());
  button()!.click();
  await until(() => expect(text()).toContain('Top normalized statements'));
  expect(text()).toContain('AVAILABLE');
  expect(text()).toContain('Threads connected: 5');
  expect(h.calls('POST')).toEqual(['api/mysql/read']);
});

it('changes render only when the read carries them (the second read)', async () => {
  h.route((url) => (url === 'api/mysql' ? json(200, read([])) : undefined));
  h.mount(MySql, { panel: panel('mysql') });
  await until(() => expect(text()).toContain('Top normalized statements'));
  expect(text()).not.toContain('Since the previous read');
  h.route((url) =>
    url === 'api/mysql'
      ? json(200, read([{ metric: 'Threads connected', previous: '5', current: '8', direction: 'UP' }]))
      : undefined
  );
  h.mount(MySql, { panel: panel('mysql') });
  await until(() => expect(text()).toContain('Since the previous read'));
  expect(text()).toContain('Threads connected');
  expect(text()).toContain('5 → 8');
});

it('read-only hides the read button and says why', async () => {
  h.route((url) => (url === 'api/mysql' ? json(200, notRead) : undefined));
  h.mount(MySql, { panel: readOnly('mysql') });
  await until(() => expect(text()).toContain(NOT_READ_MESSAGE));
  expect(button()).toBeUndefined();
  expect(text()).toContain('Read-only: SHARPIT_READ_ONLY=true');
});

it('renders the section rows and limitations from the POST answer without a second GET', async () => {
  const withRows = {
    ...read([]),
    limitations: ['mysql+pymysql://db:3306/app/statements: row limit reached (100 rows retained)'],
    dataSources: [
      {
        ...dataSource([]),
        tables: [{ table_schema: 'app', table_name: 'orders', data_length: 16384 }],
        settings: [{ name: 'max_connections', value: '151', scope: 'GLOBAL', source: 'VARIABLES' }],
      },
    ],
  };
  h.route((url, init) => {
    if (url === 'api/mysql') return json(200, notRead);
    if (url === 'api/mysql/read' && init?.method === 'POST') return json(200, withRows);
    return undefined;
  });
  h.mount(MySql, { panel: panel('mysql') });
  await until(() => expect(button()).toBeDefined());
  button()!.click();
  await until(() => expect(text()).toContain('orders'));
  expect(text()).toContain('max_connections');
  expect(text()).toContain('row limit reached');
  expect(h.calls('GET')).toEqual(['api/mysql']);
});
