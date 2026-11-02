// @vitest-environment jsdom
import { expect, it } from 'vitest';
import SqlalchemyStatistics from '../../src/views/SqlalchemyStatistics.svelte';
import { harness, json, panel, until } from './support';

const stats = (over: object = {}) => ({
  sessionOpenCount: null, sessionCloseCount: null, flushCount: null, connectCount: null, transactionCount: null,
  successfulTransactionCount: null, entityLoadCount: null, entityFetchCount: null, entityInsertCount: null,
  entityUpdateCount: null, entityDeleteCount: null, collectionLoadCount: null, collectionFetchCount: null,
  collectionRecreateCount: null, collectionUpdateCount: null, collectionRemoveCount: null,
  queryExecutionCount: 7, queryExecutionMaxTime: 12, queryExecutionMaxTimeQueryString: 'select ?',
  statementCount: 9, nPlusOneWindow: 'retained SQL Trace window (9 statements)', nPlusOne: [], ...over,
});
const report = (over: object = {}) => ({ available: true, enableAvailable: false, unavailableReason: null, statistics: stats(), ...over });
const h = harness();
const text = () => h.text().replace(/\s+/g, ' ');
const mount = () => h.mount(SqlalchemyStatistics, { panel: panel('sqlalchemy-statistics', { title: 'SQLAlchemy Statistics' }) });

it('a null counter reads "not measured" with the reason as a tooltip, never 0', async () => {
  h.route((url) => (url === 'api/sqlalchemy-statistics' ? json(200, report()) : undefined));
  mount();
  await until(() => expect(text()).toContain('not measured'));
  expect(text()).not.toMatch(/Flushes 0/);
  expect(document.querySelector('[title^="SQLAlchemy reports SQL statements"]')).not.toBeNull();
});

it('the N+1 table links the route to HTTP Exchanges', async () => {
  const hit = { method: 'GET', route: 'app:list_pets', routeReason: null, sql: 'select * from pets where owner_id = ?', executionsPerRequest: 6, requests: 1, threshold: 5 };
  h.route((url) => (url === 'api/sqlalchemy-statistics' ? json(200, report({ statistics: stats({ nPlusOne: [hit] }) })) : undefined));
  mount();
  await until(() => expect(document.querySelector('a[href^="#/http-exchanges"]')).not.toBeNull());
  expect(document.querySelector('a')?.getAttribute('href')).toContain('app%3Alist_pets');
});

it('enableAvailable false shows no enable button', async () => {
  h.route((url) => (url === 'api/sqlalchemy-statistics' ? json(200, report()) : undefined));
  mount();
  await until(() => expect(text()).toContain('SELECT statements'));
  expect(document.querySelector('button[data-enable]')).toBeNull();
  expect(text()).not.toMatch(/enable/i);
});
