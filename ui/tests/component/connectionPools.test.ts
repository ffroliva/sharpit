// @vitest-environment jsdom
import { afterEach, expect, it, vi } from 'vitest';
import ConnectionPools from '../../src/views/ConnectionPools.svelte';
import { harness, json, until } from './support';

const pool = (name: string, over: object = {}) => ({
  beanName: name, poolName: name, jdbcUrl: name, username: null, driverClassName: 'sqlite+pysqlite (QueuePool)',
  minimumIdle: null, maximumPoolSize: 15, connectionTimeoutMs: 30000, idleTimeoutMs: null, maxLifetimeMs: null,
  validationTimeoutMs: null, keepaliveTimeMs: null, readOnly: false, autoCommit: false, available: true,
  unavailableReason: null, snapshot: { timestamp: 1, active: 2, idle: 3, total: 5, pending: null }, ...over,
});
const report = (pools: object[]) => ({ hikariPresent: true, total: pools.length, pools });
const h = harness();
const text = () => h.text().replace(/\s+/g, ' ');
afterEach(() => vi.useRealTimers());

it('one card per pool with active, idle and max; a pool without statistics shows its reason', async () => {
  h.route((url) => (url === 'api/database-connection-pools/pools'
    ? json(200, report([pool('main'), pool('other', { available: false, unavailableReason: 'NullPool keeps no pool statistics', snapshot: null })]))
    : undefined));
  h.mount(ConnectionPools);
  expect(text()).toContain('Loading');
  await until(() => expect(text()).toContain('main'));
  expect(text()).toMatch(/2\s*active/);
  expect(text()).toMatch(/3\s*idle/);
  expect(text()).toMatch(/max\s*15/);
  expect(text()).toContain('sqlite+pysqlite (QueuePool)');
  expect(text()).toContain('NullPool keeps no pool statistics');
});

it('polls each pool snapshot every 2 s while visible', async () => {
  vi.useFakeTimers({ toFake: ['setInterval', 'clearInterval'] });
  h.route((url) => {
    if (url === 'api/database-connection-pools/pools') return json(200, report([pool('main')]));
    if (url === 'api/database-connection-pools/pools/main/snapshot') return json(200, { timestamp: 2, active: 4, idle: 1, total: 5, pending: null });
    return undefined;
  });
  h.mount(ConnectionPools);
  await until(() => expect(text()).toMatch(/2\s*active/));
  vi.advanceTimersByTime(2000);
  await until(() => expect(text()).toMatch(/4\s*active/));
  expect(h.calls('GET')).toContain('api/database-connection-pools/pools/main/snapshot');
});

it('empty: no pools shows the engines= snippet', async () => {
  h.route((url) => (url === 'api/database-connection-pools/pools' ? json(200, report([])) : undefined));
  h.mount(ConnectionPools);
  await until(() => expect(text()).toContain('engines=['));
});

it('shows the error state', async () => {
  h.route(() => json(500, { error: 'x' }));
  h.mount(ConnectionPools);
  await until(() => expect(h.target.querySelector('[role="alert"]')?.textContent).toContain('Could not load'));
});
