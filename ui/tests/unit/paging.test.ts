import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { PAGE_SIZE, ServerPage } from '../../src/lib/paging';
import loggers from '../../../tests/fixtures/bootui/loggers.json';

type Logger = (typeof loggers.loggers)[number];
const fetchMock = vi.fn<typeof fetch>();

// Serves the golden loggers fixture with the contract's paging rules (offset/limit slice, hasMore).
function serveLoggers(input: RequestInfo | URL): Promise<Response> {
  const url = new URL(String(input), 'http://x/sharpit/');
  const offset = Number(url.searchParams.get('offset'));
  const limit = Number(url.searchParams.get('limit'));
  const all = loggers.loggers;
  const slice = all.slice(offset, offset + limit);
  const page = { total: all.length, matched: all.length, offset, limit, returned: slice.length, hasMore: offset + slice.length < all.length };
  return Promise.resolve(new Response(JSON.stringify({ ...loggers, loggers: slice, page }), { headers: { 'content-type': 'application/json' } }));
}

beforeEach(() => {
  fetchMock.mockReset().mockImplementation(serveLoggers);
  vi.stubGlobal('fetch', fetchMock);
});
afterEach(() => vi.unstubAllGlobals());

describe('ServerPage', () => {
  it('pages of 200', () => expect(PAGE_SIZE).toBe(200));

  it('loads the first page with offset 0 and limit 200, omitting empty params', async () => {
    expect(loggers.loggers.length).toBeGreaterThan(2 * PAGE_SIZE); // fixture is big enough to need three pages
    const p = await ServerPage.load<Logger>('loggers', 'loggers', { q: '' });
    expect(fetchMock.mock.calls[0]![0]).toBe('api/loggers?offset=0&limit=200');
    expect(p.items).toHaveLength(200);
    expect(p.items[0]).toEqual(loggers.loggers[0]);
    expect(p.hasMore).toBe(true);
    expect(p.matched).toBe(loggers.loggers.length);
    expect(p.total).toBe(loggers.loggers.length);
  });

  it('more() appends from offset = items loaded until hasMore is false, keeping params', async () => {
    let p = await ServerPage.load<Logger>('loggers', 'loggers', { q: 'org' });
    const first = p;
    p = await p.more();
    expect(fetchMock.mock.calls[1]![0]).toBe('api/loggers?q=org&offset=200&limit=200');
    expect(p.items).toHaveLength(400);
    expect(first.items).toHaveLength(200); // immutable: the old page is untouched
    while (p.hasMore) p = await p.more();
    expect(p.items).toEqual(loggers.loggers);
    expect(p.hasMore).toBe(false);
    const calls = fetchMock.mock.calls.length;
    expect(await p.more()).toBe(p); // nothing more to fetch
    expect(fetchMock.mock.calls.length).toBe(calls);
  });
});

describe('ServerPage.more concurrency', () => {
  it('concurrent more() calls share one request and one result', async () => {
    const p = await ServerPage.load<Logger>('loggers', 'loggers');
    const calls = fetchMock.mock.calls.length;
    const [a, b] = await Promise.all([p.more(), p.more()]);
    expect(fetchMock.mock.calls.length).toBe(calls + 1);
    expect(a).toBe(b);
    expect(a.items).toHaveLength(400);
  });
});

describe('ServerPage.loadAll', () => {
  it('loads every page', async () => {
    const all = await ServerPage.loadAll<Logger>('loggers', 'loggers', 5000);
    expect(all.length).toBe(loggers.loggers.length);
  });

  it('stops at the row cap', async () => {
    const all = await ServerPage.loadAll<Logger>('loggers', 'loggers', PAGE_SIZE);
    expect(all.length).toBe(PAGE_SIZE);
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it('stops on an empty page even when the server says hasMore', async () => {
    const page = { total: 9, matched: 9, offset: 0, limit: PAGE_SIZE, returned: 0, hasMore: true };
    fetchMock.mockImplementation(() =>
      Promise.resolve(new Response(JSON.stringify({ loggers: [], page }), { headers: { 'content-type': 'application/json' } })),
    );
    expect(await ServerPage.loadAll<Logger>('loggers', 'loggers', 5000)).toEqual([]);
    expect(fetchMock).toHaveBeenCalledTimes(2); // first page and one more, then it gives up
  });
});
