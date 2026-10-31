// @vitest-environment jsdom
import { expect, it } from 'vitest';
import Activity from '../../src/views/Activity.svelte';
import { FakeEventSource, harness, json, until } from './support';

const entry = {
  id: 'r1', type: 'REQUEST', timestamp: 1_700_000_000_000, severity: 'SLOW', summary: 'GET /owners', detail: null, durationMs: 1500,
  correlationId: 'r1', method: 'GET', path: '/owners', status: 200, thread: null, profileable: true, parentId: null,
  securedPrincipal: null, sqlNPlusOneSuspected: true,
};
const kpis = { requestsPerMinute: 12, errorRatePercent: 0, p50LatencyMs: 3, p95LatencyMs: 40, slowestEndpoint: '/owners', slowestEndpointMs: 1500 };
const report = (entries: unknown[]) => ({ available: true, entries, typeCounts: {}, kpis, sources: ['http-exchanges'], warnings: [], pageInfo: null });
const profile = {
  available: true, unavailableReason: null, request: { ...entry, method: 'GET' }, sql: [],
  sqlGroups: [{ sql: 'SELECT * FROM pet WHERE owner_id = ?', category: 'SELECT', executions: 7, totalDurationMillis: 21, maxDurationMillis: 4, potentialNPlusOne: true, callSites: ['app.py:30'] }],
  sqlCorrelationApproximate: false, exceptions: [], security: [], trace: null,
  timing: { totalMs: 1500, sqlMs: 21, sqlCount: 7, sqlPercent: 1.4 }, notes: [],
};

const h = harness();
const isFeed = (url: string) => url === 'api/activity' || url.startsWith('api/activity?');

it('shows a loading state, then the empty state when nothing was captured', async () => {
  h.route((url) => (isFeed(url) ? json(200, report([])) : undefined));
  h.mount(Activity);
  expect(h.text()).toContain('Loading');
  await until(() => expect(h.text()).toContain('No requests captured yet'));
});

it('shows the error state with a retry', async () => {
  h.route(() => json(500, { error: 'boom' }));
  h.mount(Activity);
  await until(() => expect(h.target.querySelector('[role="alert"]')?.textContent).toContain('Could not load'));
  expect(h.target.querySelector('button')?.textContent).toBe('Retry');
});

it('lists the feed with the KPI strip and marks a slow request and a suspected N+1', async () => {
  h.route((url) => (isFeed(url) ? json(200, report([entry])) : undefined));
  h.mount(Activity);
  await until(() => expect(h.text()).toContain('GET /owners'));
  expect(h.text()).toContain('slow');
  expect(h.text()).toContain('N+1');
  expect(h.text()).toContain('40 ms'); // p95
});

it('opens the request profile with the N+1 group on top, and renders SQL as text', async () => {
  h.route((url) => {
    if (url.startsWith('api/activity/request/r1')) return json(200, { ...profile, sqlGroups: [{ ...profile.sqlGroups[0], sql: '<img src=x onerror=alert(1)>' }] });
    return isFeed(url) ? json(200, report([entry])) : undefined;
  });
  h.mount(Activity);
  await until(() => expect(h.text()).toContain('GET /owners'));
  [...h.target.querySelectorAll('button')].find((b) => b.textContent?.includes('GET /owners'))!.click();
  await until(() => expect(h.text()).toContain('7 executions'));
  expect(h.text()).toContain('potential N+1');
  expect(h.target.querySelector('img')).toBeNull();
  expect(h.text()).toContain('<img src=x onerror=alert(1)>');
});

it('reloads on a stream tick, and sends the route filter as q', async () => {
  h.route((url) => (isFeed(url) ? json(200, report([entry])) : undefined));
  h.mount(Activity, { q: 'abc' });
  await until(() => expect(h.text()).toContain('GET /owners'));
  expect(h.calls('GET')[0]).toContain('q=abc');
  const before = h.calls('GET').length;
  FakeEventSource.last.emit('update');
  await until(() => expect(h.calls('GET').length).toBe(before + 1));
  expect(FakeEventSource.last.url).toBe('api/activity/stream');
});
