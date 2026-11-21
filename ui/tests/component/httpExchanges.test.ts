// @vitest-environment jsdom
import { expect, it, vi } from 'vitest';
import HttpExchanges from '../../src/views/HttpExchanges.svelte';
import { FakeEventSource, harness, json, page, until } from './support';

const row = {
  id: 'req1', timestamp: '2026-10-31T12:00:00Z', method: 'GET', path: '/owners', query: 'a=1', uri: '/owners?a=1', status: 500,
  statusFamily: '5xx', durationMs: 12, responseSizeBytes: 2048, remoteAddress: '127.0.0.1', principal: null, sessionId: null, traceId: '4bf92f3577b34da6a3ce929d0e0e4736',
  requestHeaders: [{ name: 'authorization', values: ['******'], masked: true }], responseHeaders: [{ name: 'content-type', values: ['text/html'], masked: false }],
};
const report = (exchanges: unknown[]) => ({ total: exchanges.length, recorded: exchanges.length, hiddenSelf: 0, exchanges, page: page(exchanges.length), unavailableReason: null });

const h = harness();
const isExchangeList = (url: string) => url === 'api/http-exchanges' || url.startsWith('api/http-exchanges?');

it('shows the loading skeleton, then the empty state', async () => {
  h.route((url) => (isExchangeList(url) ? json(200, report([])) : undefined));
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
  h.route((url) => (isExchangeList(url) ? json(200, report([row])) : undefined));
  h.mount(HttpExchanges);
  await until(() => expect(h.target.querySelector('button[aria-label="Details for GET /owners?a=1"]')).not.toBeNull());
});

it('colours the status by family and opens a sheet with masked headers and the two links', async () => {
  h.route((url) => (isExchangeList(url) ? json(200, report([row])) : undefined));
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
  h.route((url) => (isExchangeList(url) ? json(200, report([row])) : undefined));
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
  h.route((url) => isExchangeList(url) ? new Promise<Response>(() => {}) : undefined);
  h.mount(HttpExchanges);
  await until(() => expect(h.calls('GET').filter(isExchangeList)).toHaveLength(1));
  await until(() => expect(FakeEventSource.last).toBeDefined());
  FakeEventSource.last.emit('update');
  await new Promise((resolve) => setTimeout(resolve, 10));
  expect(h.calls('GET').filter(isExchangeList)).toHaveLength(1);
});

it('live ticks do not refetch an error, and Retry recovers', async () => {
  h.route((url) => isExchangeList(url) ? json(503, { error: 'offline' }) : undefined);
  h.mount(HttpExchanges);
  await until(() => expect(h.target.querySelector('[role="alert"]')?.textContent).toContain('Could not load'));
  await until(() => expect(FakeEventSource.last).toBeDefined());
  const failedRequests = h.calls('GET').filter(isExchangeList).length;
  FakeEventSource.last.emit('update');
  await new Promise((resolve) => setTimeout(resolve, 10));
  expect(h.calls('GET').filter(isExchangeList)).toHaveLength(failedRequests);

  h.route((url) => isExchangeList(url) ? json(200, report([])) : undefined);
  [...h.target.querySelectorAll<HTMLButtonElement>('button')].find((button) => button.textContent === 'Retry')!.click();
  await until(() => expect(h.target.querySelector('[role="alert"]')).toBeNull());
});

const routeRankingReport = {
    available: true,
    unavailableReason: null,
    window: { retainedExchanges: 3, bufferSize: 200, evicted: 0, hiddenSelfExchanges: 0, summarizedExchanges: 3, timedExchanges: 3, oldestTimestamp: 1, newestTimestamp: 3, totalDurationMs: 60 },
    routes: [
      { id: 'GET /owners', method: 'GET', route: '/owners', routeSource: 'FRAMEWORK_TEMPLATE', requests: 2, status2xx: 2, status3xx: 0, status4xx: 0, status5xx: 0, statusOther: 0, errorCount: 0, timedRequests: 2, avgDurationMs: 10, p50DurationMs: 10, totalDurationMs: 20, p95DurationMs: 10, p99DurationMs: 10, maxDurationMs: 10, shareOfRetainedTimePercent: 33.3, topFor: ['REQUESTS', 'P95_DURATION'] },
      { id: 'POST /pets', method: 'POST', route: '/pets', routeSource: 'MASKED_PATH', requests: 1, status2xx: 0, status3xx: 0, status4xx: 0, status5xx: 1, statusOther: 0, errorCount: 1, timedRequests: 1, avgDurationMs: 40, p50DurationMs: 40, totalDurationMs: 40, p95DurationMs: 40, p99DurationMs: 40, maxDurationMs: 40, shareOfRetainedTimePercent: 66.7, topFor: ['TOTAL_DURATION', 'P95_DURATION', 'MAX_DURATION', 'ERROR_COUNT'] },
    ],
    topPerCriterion: 25,
    routesTruncated: false,
    distinctRoutes: 2,
    notes: ['Figures use retained exchanges.'],
};

function mountRankedRoutes() {
  h.route((url) => {
    if (url.startsWith('api/http-exchanges/routes')) return json(200, routeRankingReport);
    if (isExchangeList(url)) return json(200, report([row]));
    return undefined;
  });
  h.mount(HttpExchanges);
}

// ported: HttpExchangesTest.ranks routes over the stated window and labels how each route was resolved
it('ranks routes by the selected metric', async () => {
  mountRankedRoutes();
  await until(() => expect(h.target.querySelector('[aria-label="Rank routes by"]')).not.toBeNull());
  const ranking = h.target.querySelector<HTMLSelectElement>('[aria-label="Rank routes by"]')!;
  await until(() => expect([...h.target.querySelectorAll('[data-route-id]')].map((el) => el.getAttribute('data-route-id'))).toEqual(['GET /owners']));
  ranking.value = 'p95DurationMs';
  ranking.dispatchEvent(new Event('change', { bubbles: true }));
  await until(() => expect([...h.target.querySelectorAll('[data-route-id]')].map((el) => el.getAttribute('data-route-id'))).toEqual(['POST /pets', 'GET /owners']));
});

// ported: HttpExchangesTest.says a route that scores zero is not ranked rather than cut off
it('shows unranked routes when no route scores for the selected metric', async () => {
  const routes = { ...routeRankingReport, routes: routeRankingReport.routes.map((route) => ({ ...route, errorCount: 0, topFor: ['REQUESTS'] })) };
  h.route((url) => url.startsWith('api/http-exchanges/routes') ? json(200, routes) : isExchangeList(url) ? json(200, report([row])) : undefined);
  h.mount(HttpExchanges);
  const ranking = h.target.querySelector<HTMLSelectElement>('[aria-label="Rank routes by"]')!;
  await until(() => expect(ranking).not.toBeNull());
  ranking.value = 'errorCount';
  ranking.dispatchEvent(new Event('change', { bubbles: true }));
  await until(() => expect(h.text()).toContain('listed unranked'));
  expect(h.target.querySelectorAll('[data-route-id]')).toHaveLength(2);
});

// ported: HttpExchangesTest.contains request details in the route drawer; every-close-path focus restoration is adapted for the native dialog.
it('closes the route exchanges drawer with Escape, Close, and backdrop while restoring focus', async () => {
  mountRankedRoutes();
  const ranking = () => h.target.querySelector<HTMLSelectElement>('[aria-label="Rank routes by"]')!;
  await until(() => expect(ranking()).not.toBeNull());
  ranking().value = 'totalDurationMs';
  ranking().dispatchEvent(new Event('change', { bubbles: true }));
  await until(() => expect(h.target.querySelector('[aria-label="Show the retained exchanges of POST /pets"]')).not.toBeNull());
  const opener = h.target.querySelector<HTMLButtonElement>('[aria-label="Show the retained exchanges of POST /pets"]')!;
  opener.focus();
  opener.click();
  await until(() => expect(h.target.querySelector('dialog[open]')?.textContent).toContain('POST /pets'));
  const drawer = h.target.querySelector<HTMLDialogElement>('dialog[open]')!;
  expect(drawer.getAttribute('aria-labelledby')).toBe('route-drawer-title');
  expect(drawer.getAttribute('aria-describedby')).toBe('route-drawer-route');
  expect(drawer.querySelector<HTMLButtonElement>('[aria-label="Close route exchanges"]')).toBe(document.activeElement);
  await until(() => expect(h.calls('GET').some((url) => url.includes('route=POST+%2Fpets'))).toBe(true));
  const escape = () => drawer.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));
  escape();
  await until(() => expect(h.target.querySelector('dialog[open]')).toBeNull());
  expect(document.activeElement).toBe(opener);
  opener.click();
  await until(() => expect(h.target.querySelector('dialog[open]')).not.toBeNull());
  h.target.querySelector<HTMLButtonElement>('[aria-label="Close route exchanges"]')!.click();
  await until(() => expect(h.target.querySelector('dialog[open]')).toBeNull());
  expect(document.activeElement).toBe(opener);
  opener.click();
  await until(() => expect(h.target.querySelector('dialog[open]')).not.toBeNull());
  const backdrop = h.target.querySelector<HTMLDialogElement>('dialog[open]')!;
  backdrop.dispatchEvent(new PointerEvent('pointerdown', { bubbles: true }));
  backdrop.dispatchEvent(new MouseEvent('click', { bubbles: true }));
  await until(() => expect(h.target.querySelector('dialog[open]')).toBeNull());
  expect(document.activeElement).toBe(opener);
});

it('refreshes route rankings after stream ticks and every 30 seconds', async () => {
  vi.useFakeTimers();
  let requests = 1;
  h.route((url) => url.startsWith('api/http-exchanges/routes')
    ? json(200, { ...routeRankingReport, routes: [{ ...routeRankingReport.routes[0], requests, topFor: ['REQUESTS'] }] })
    : isExchangeList(url) ? json(200, report([row])) : undefined);
  h.mount(HttpExchanges);
  await vi.waitFor(() => expect(h.target.querySelector('[data-route-id]')).not.toBeNull());
  requests = 2;
  const routeCalls = () => h.calls('GET').filter((url) => url.startsWith('api/http-exchanges/routes')).length;
  const initialRouteCalls = routeCalls();
  FakeEventSource.last.emit('update');
  await vi.waitFor(() => expect(routeCalls()).toBeGreaterThan(initialRouteCalls));
  await vi.waitFor(() => expect(h.target.querySelector('[data-route-id]')?.textContent).toContain('2'));
  requests = 3;
  const streamRouteCalls = routeCalls();
  await vi.advanceTimersByTimeAsync(30_000);
  await vi.waitFor(() => expect(routeCalls()).toBeGreaterThan(streamRouteCalls));
  await vi.waitFor(() => expect(h.target.querySelector('[data-route-id]')?.textContent).toContain('3'));
  vi.useRealTimers();
});
