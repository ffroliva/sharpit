// @vitest-environment jsdom
import { expect, it } from 'vitest';
import SqlTrace from '../../src/views/SqlTrace.svelte';
import { harness, json, panel, until } from './support';

const report = {
  available: true, unavailableReason: null, capturing: true, captureParameters: false, bufferSize: 200, totalCaptured: 3,
  slowQueryThresholdMillis: 100, dataSources: ['sqlite://'], stats: { evicted: 0 },
  entries: [{ id: 1, timestamp: '2026-10-31T12:00:00.000Z', sql: 'select ?', statementType: 'STATEMENT', category: 'SELECT',
    durationMillis: 3, success: true, errorMessage: null, affectedRows: null, batchSize: 0, connectionId: null,
    thread: 'MainThread', slow: false, parameters: [], traceId: null, callSite: null }],
  topStatements: [], warnings: [],
};
const statement = (id: string, over: object = {}) => ({
  id, sql: id, category: 'SELECT', executions: 1, totalDurationMillis: 1, maxDurationMillis: 1, avgDurationMillis: 1,
  errorCount: 0, p50DurationMillis: 1, p95DurationMillis: 1, p99DurationMillis: 1, shareOfRetainedTimePercent: 10,
  topFor: ['TOTAL_DURATION'], potentialNPlusOne: false, callSites: [], entryIds: [1], entryIdsTruncated: false, ...over,
});
const insights = {
  available: true, unavailableReason: null, capturing: true,
  window: { retainedStatements: 3, bufferSize: 200, evicted: 0, totalCaptured: 3, oldestTimestamp: 1, newestTimestamp: 2, totalDurationMillis: 9 },
  statements: [
    statement('select * from slow_total', { totalDurationMillis: 8, executions: 1 }),
    statement('select * from many_runs', { executions: 9, topFor: ['TOTAL_DURATION', 'EXECUTIONS'] }),
  ],
  topPerCriterion: 10, statementsTruncated: false, distinctStatements: 2,
  attribution: {
    available: true, unavailableReason: null, supportedCorrelations: ['TRACE_ID'], requestsConsidered: 2,
    routes: [{ id: 'GET /orders/{value}', method: 'GET', route: '/orders/{value}', routeSource: 'MASKED_PATH', requests: 2,
      executions: 4, totalDurationMillis: 6, maxDurationMillis: 2, avgDurationMillis: 1.5, errorCount: 0, distinctStatements: 1,
      shareOfRetainedTimePercent: 66.67, traceCorrelated: 4, threadCorrelated: 0, timeWindowCorrelated: 0,
      topStatements: [], topStatementsTruncated: false, entryIds: [1] }],
    routesTruncated: false, distinctRoutes: 1, attributedExecutions: 4,
    unattributed: { executions: 1, totalDurationMillis: 3, errorCount: 0, shareOfRetainedTimePercent: 33.33, reason: 'No captured request could have issued these statements.' },
    ambiguous: { executions: 0, totalDurationMillis: 0, errorCount: 0, shareOfRetainedTimePercent: 0, reason: 'ambiguous' },
    notes: ['Routes are grouped by masked path.'],
  },
  notes: ['Rankings cover the 3 statement executions currently retained.'],
};
const h = harness();
const text = () => h.text().replace(/\s+/g, ' ');
const tab = (name: string) => [...h.target.querySelectorAll('[role="tab"]')].find((b) => b.textContent?.includes(name)) as HTMLElement;
const rows = () => [...h.target.querySelectorAll('[data-testid="insight-statement"]')].map((r) => r.textContent?.trim().split(/\s/)[0]);

async function openInsights() {
  h.route((url) => (url === 'api/sql-trace' ? json(200, report) : url === 'api/sql-trace/insights' ? json(200, insights) : undefined));
  h.mount(SqlTrace, { panel: panel('sql-trace') });
  await until(() => expect(text()).toContain('Recent'));
  expect(tab('Insights')).toBeTruthy();
  tab('Insights').click();
  await until(() => expect(text()).toContain('select * from many_runs'));
}

it('Insights: notes and the window are shown', async () => {
  await openInsights();
  expect(text()).toContain('Rankings cover the 3 statement executions currently retained.');
  expect(h.calls('GET')).toContain('api/sql-trace/insights');
});

it('Insights: the criterion switcher re-ranks the statements', async () => {
  await openInsights();
  expect(rows()).toEqual(['select', 'select']);
  const select = h.target.querySelector('select[aria-label="Rank by"]') as HTMLSelectElement;
  select.value = 'EXECUTIONS';
  select.dispatchEvent(new Event('change'));
  await until(() => expect(h.target.querySelectorAll('[data-testid="insight-statement"]')).toHaveLength(1));
  expect(text()).toContain('select * from many_runs');
});

it('Insights: the route table and the unattributed bucket', async () => {
  await openInsights();
  expect(text()).toContain('GET /orders/{value}');
  expect(text()).toContain('66.67%');
  expect(text()).toContain('No captured request could have issued these statements.');
  expect(text()).toContain('Routes are grouped by masked path.');
});
