// @vitest-environment jsdom
import { expect, it } from 'vitest';
import HttpExchanges from '../../src/views/HttpExchanges.svelte';
import { FakeEventSource, harness, json, page, until } from './support';

const row = {
  id: 'req1', timestamp: '2026-10-31T12:00:00Z', method: 'GET', path: '/owners', query: 'a=1', uri: '/owners?a=1', status: 500,
  statusFamily: '5xx', durationMs: 12, responseSizeBytes: 2048, remoteAddress: '127.0.0.1', principal: null, sessionId: null, traceId: '4bf92f3577b34da6a3ce929d0e0e4736',
  requestHeaders: [{ name: 'authorization', values: ['******'], masked: true }], responseHeaders: [{ name: 'content-type', values: ['text/html'], masked: false }],
};
const report = (exchanges: unknown[]) => ({ total: exchanges.length, recorded: exchanges.length, hiddenSelf: 0, exchanges, page: page(exchanges.length), unavailableReason: null });

const h = harness();

it('shows the loading skeleton, then the empty state', async () => {
  h.route((url) => (url.startsWith('api/http-exchanges') ? json(200, report([])) : undefined));
  h.mount(HttpExchanges);
  expect(h.target.querySelector('.skeleton')).not.toBeNull();
  await until(() => expect(h.text()).toContain('Call your app, then come back'));
});

it('shows the error state', async () => {
  h.route(() => json(500, { error: 'x' }));
  h.mount(HttpExchanges);
  await until(() => expect(h.target.querySelector('[role="alert"]')?.textContent).toContain('Could not load'));
});

it('details buttons are named by the request they open', async () => {
  h.route((url) => (url.startsWith('api/http-exchanges') ? json(200, report([row])) : undefined));
  h.mount(HttpExchanges);
  await until(() => expect(h.target.querySelector('button[aria-label="Details for GET /owners?a=1"]')).not.toBeNull());
});

it('colours the status by family and opens a sheet with masked headers and the two links', async () => {
  h.route((url) => (url.startsWith('api/http-exchanges') ? json(200, report([row])) : undefined));
  h.mount(HttpExchanges);
  await until(() => expect(h.text()).toContain('/owners'));
  expect(h.target.querySelector('td.danger')?.textContent).toBe('500');
  [...h.target.querySelectorAll('button')].find((b) => b.textContent === 'Details')!.click();
  await until(() => expect(h.text()).toContain('authorization'));
  expect(h.text()).toContain('masked');
  const links = [...h.target.querySelectorAll('a')];
  expect(links.find((a) => a.textContent === 'Open in Activity')?.getAttribute('href')).toBe('#/activity?q=req1');
  expect(links.find((a) => a.textContent === 'Replay in Probe')?.getAttribute('href')).toBe('#/http-probe?q=GET+%2Fowners');
});

it('sends the method and status class filters, and reloads on a stream tick', async () => {
  h.route((url) => (url.startsWith('api/http-exchanges') ? json(200, report([row])) : undefined));
  h.mount(HttpExchanges);
  await until(() => expect(h.text()).toContain('/owners'));
  const method = h.target.querySelector<HTMLSelectElement>('select[aria-label="Method"]')!;
  method.value = 'POST';
  method.dispatchEvent(new Event('change', { bubbles: true }));
  await until(() => expect(h.calls('GET').at(-1)).toContain('method=POST'));
  const before = h.calls('GET').length;
  FakeEventSource.last.emit('update');
  await until(() => expect(h.calls('GET').length).toBeGreaterThan(before));
  expect(FakeEventSource.last.url).toBe('api/activity/stream');
});

it('live ticks do not restart the initial load', async () => {
  h.route((url) => url.startsWith('api/http-exchanges') ? new Promise<Response>(() => {}) : undefined);
  h.mount(HttpExchanges);
  await until(() => expect(h.calls('GET').filter((url) => url.startsWith('api/http-exchanges?'))).toHaveLength(1));
  await until(() => expect(FakeEventSource.last).toBeDefined());
  FakeEventSource.last.emit('update');
  await new Promise((resolve) => setTimeout(resolve, 10));
  expect(h.calls('GET').filter((url) => url.startsWith('api/http-exchanges?'))).toHaveLength(1);
});

it('live ticks do not refetch an error, and Retry recovers', async () => {
  h.route((url) => url.startsWith('api/http-exchanges') ? json(503, { error: 'offline' }) : undefined);
  h.mount(HttpExchanges);
  await until(() => expect(h.target.querySelector('[role="alert"]')?.textContent).toContain('Could not load'));
  await until(() => expect(FakeEventSource.last).toBeDefined());
  const failedRequests = h.calls('GET').filter((url) => url.startsWith('api/http-exchanges')).length;
  FakeEventSource.last.emit('update');
  await new Promise((resolve) => setTimeout(resolve, 10));
  expect(h.calls('GET').filter((url) => url.startsWith('api/http-exchanges'))).toHaveLength(failedRequests);

  h.route((url) => url.startsWith('api/http-exchanges') ? json(200, report([])) : undefined);
  h.target.querySelector<HTMLButtonElement>('button')!.click();
  await until(() => expect(h.target.querySelector('[role="alert"]')).toBeNull());
});

const routeRankingReport = {
    available: true,
    unavailableReason: null,
    window: { retainedExchanges: 3, bufferSize: 200, evicted: 0, hiddenSelfExchanges: 0, summarizedExchanges: 3, timedExchanges: 3, oldestTimestamp: 1, newestTimestamp: 3, totalDurationMs: 60 },
    routes: [
      { id: 'GET /owners', method: 'GET', route: '/owners', routeSource: 'FRAMEWORK_TEMPLATE', requests: 2, errorCount: 0, timedRequests: 2, totalDurationMs: 20, p95DurationMs: 10, topFor: ['REQUESTS', 'TOTAL_DURATION', 'P95_DURATION'] },
      { id: 'POST /pets', method: 'POST', route: '/pets', routeSource: 'MASKED_PATH', requests: 1, errorCount: 1, timedRequests: 1, totalDurationMs: 40, p95DurationMs: 40, topFor: ['TOTAL_DURATION', 'P95_DURATION'] },
    ],
    topPerCriterion: 25,
    routesTruncated: false,
    distinctRoutes: 2,
    notes: ['Figures use retained exchanges.'],
};

function mountRankedRoutes() {
  h.route((url) => {
    if (url.startsWith('api/http-exchanges/routes')) return json(200, routeRankingReport);
    if (url.startsWith('api/http-exchanges')) return json(200, report([row]));
    return undefined;
  });
  h.mount(HttpExchanges);
}

it('ranks routes by the selected metric', async () => {
  mountRankedRoutes();
  await until(() => expect(h.target.querySelector('[aria-label="Rank routes by"]')).not.toBeNull());
  const ranking = h.target.querySelector<HTMLSelectElement>('[aria-label="Rank routes by"]')!;
  ranking.value = 'p95DurationMs';
  ranking.dispatchEvent(new Event('change', { bubbles: true }));
  await until(() => expect([...h.target.querySelectorAll('[data-route-id]')].map((el) => el.getAttribute('data-route-id'))).toEqual(['POST /pets', 'GET /owners']));
});

it('opens and closes the exchanges drawer for a ranked route', async () => {
  mountRankedRoutes();
  await until(() => expect(h.target.querySelector('[aria-label="View exchanges for POST /pets"]')).not.toBeNull());
  h.target.querySelector<HTMLButtonElement>('[aria-label="View exchanges for POST /pets"]')!.click();
  await until(() => expect(h.target.querySelector('dialog[open]')?.textContent).toContain('POST /pets'));
  await until(() => expect(h.calls('GET').some((url) => url.includes('route=POST+%2Fpets'))).toBe(true));
  h.target.querySelector<HTMLButtonElement>('[aria-label="Close route exchanges"]')!.click();
  await until(() => expect(h.target.querySelector('dialog[open]')).toBeNull());
});
