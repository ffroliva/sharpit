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

const NULL_REASON = 'SQLAlchemy reports SQL statements, not ORM session or entity operations (transactions live in the transactions panel)';

it('the N+1 link filters HTTP Exchanges by the request path, not the endpoint name', async () => {
  const hit = { method: 'GET', route: 'app:list_pets', routePath: '/pets', routeReason: null, sql: 'select * from pets where owner_id = ?', executionsPerRequest: 6, requests: 1, threshold: 5 };
  h.route((url) => (url === 'api/sqlalchemy-statistics' ? json(200, report({ statistics: stats({ nPlusOne: [hit] }) })) : undefined));
  mount();
  await until(() => expect(document.querySelector('a[href^="#/http-exchanges"]')).not.toBeNull());
  expect(document.querySelector('a[href^="#/http-exchanges"]')?.getAttribute('href')).toBe('#/http-exchanges?q=%2Fpets');
});

it('the not-measured tooltip is the nullable.json reason', async () => {
  h.route((url) => (url === 'api/sqlalchemy-statistics' ? json(200, report()) : undefined));
  mount();
  await until(() => expect(text()).toContain('not measured'));
  expect(document.querySelector('dd.muted')?.getAttribute('title')).toBe(NULL_REASON);
});

it('a paused-recording warning is shown', async () => {
  const warning = 'SQL Trace recording is paused: these counters are frozen until it resumes.';
  h.route((url) => (url === 'api/sqlalchemy-statistics' ? json(200, report({ statistics: stats({ warnings: [warning] }) })) : undefined));
  mount();
  await until(() => expect(text()).toContain('SELECT statements'));
  expect(text()).toContain(warning);
});
