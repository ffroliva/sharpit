// @vitest-environment jsdom
import { expect, it } from 'vitest';
import Alembic from '../../src/views/Alembic.svelte';
import { harness, json, panel, readOnly, until } from './support';

const NEVER = 'sharpit never runs migrations';
const row = (version: string, state: string) => ({
  type: 'PYTHON', version, description: `rev ${version}`, script: `migrations/versions/${version}.py`, state,
  installedBy: null, installedOn: null, installedRank: null, executionTime: null, checksum: null,
});
const db = (name: string, current: string | null, states: string[], over: object = {}) => ({
  name, currentVersion: current, applied: states.filter((s) => s === 'Success').length,
  pending: states.filter((s) => s === 'Pending').length, total: states.length,
  migrations: states.map((s, i) => row(`000${i + 1}`, s)), migrateEnabled: false, migrateDisabledReason: NEVER,
  cleanEnabled: false, cleanDisabledReason: NEVER, checkedAt: current ? 1_761_811_200_000 : null, unavailableReason: null, ...over,
});
const report = (databases: object[]) => ({ alembicPresent: true, configPath: 'C:/app/alembic.ini', total: 3, heads: ['0003'], databases });
const notRead = report([db('(not read yet)', null, ['Unknown', 'Unknown', 'Unknown'])]);
const read = report([db('sqlite:///sample.db', '0002', ['Success', 'Success', 'Pending'])]);
const h = harness();
const text = () => h.text().replace(/\s+/g, ' ');
const button = () => [...h.target.querySelectorAll('button')].find((b) => /Read database version/.test(b.textContent ?? ''))!;

it('never read: the file history shows and nothing connects on open', async () => {
  h.route((url) => (url === 'api/alembic/migrations' ? json(200, notRead) : undefined));
  h.mount(Alembic, { panel: panel('alembic') });
  expect(text()).toContain('Loading');
  await until(() => expect(text()).toContain('rev 0003'));
  expect(text()).toContain('not read yet');
  expect(h.calls('POST')).toEqual([]);
});

it('"Read database version" posts refresh and highlights the pending revision', async () => {
  let current = notRead; // the server caches the read: GET answers it afterwards
  h.route((url, init) => {
    if (url === 'api/alembic/migrations') return json(200, current);
    if (url === 'api/alembic/refresh' && init?.method === 'POST') return json(200, (current = read));
    return undefined;
  });
  h.mount(Alembic, { panel: panel('alembic') });
  await until(() => expect(text()).toContain('rev 0003'));
  button().click();
  await until(() => expect(text()).toContain('1 pending'));
  expect(text()).toContain('0002');
  const pending = h.target.querySelector('tr.pending');
  expect(pending?.textContent).toContain('0003');
  expect(h.calls('POST')).toEqual(['api/alembic/refresh']);
});

it('no engine registered shows the engines= snippet', async () => {
  const none = report([db('(not read yet)', null, ['Unknown'], { unavailableReason: 'No database engine is registered yet: pass engines=[...] to install()' })]);
  h.route((url) => (url === 'api/alembic/migrations' ? json(200, none) : undefined));
  h.mount(Alembic, { panel: panel('alembic') });
  await until(() => expect(text()).toContain('sharpit.install(app, engines=[engine])'));
});

it('no alembic.ini found shows the setting', async () => {
  h.route((url) => (url === 'api/alembic/migrations' ? json(200, { alembicPresent: false, configPath: 'alembic.ini', total: 0, heads: [], databases: [] }) : undefined));
  h.mount(Alembic, { panel: panel('alembic') });
  await until(() => expect(text()).toContain('SHARPIT_ALEMBIC_CONFIG'));
});

it('read-only: the button is disabled with the reason', async () => {
  h.route((url) => (url === 'api/alembic/migrations' ? json(200, notRead) : undefined));
  h.mount(Alembic, { panel: readOnly('alembic') });
  await until(() => expect(text()).toContain('rev 0003'));
  expect(button().disabled).toBe(true);
  expect(text()).toContain('Read-only: SHARPIT_READ_ONLY=true');
});

it('shows the error state', async () => {
  h.route(() => json(500, { error: 'x' }));
  h.mount(Alembic, { panel: panel('alembic') });
  await until(() => expect(h.target.querySelector('[role="alert"]')?.textContent).toContain('Could not load'));
});
