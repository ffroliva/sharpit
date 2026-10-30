// @vitest-environment jsdom
import { flushSync, mount, unmount } from 'svelte';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import Loggers from '../../src/views/Loggers.svelte';
import type { Panel } from '../../src/lib/types';

const fetchMock = vi.fn<typeof fetch>();
const panel: Panel = {
  id: 'loggers', title: 'Loggers', available: true, unavailableReason: null, enabled: true, readOnly: false, readOnlyReason: null,
};
const rows = [{ name: 'app', configuredLevel: null, effectiveLevel: 'WARNING' }];

function json(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), { status, headers: { 'content-type': 'application/json' } });
}

let target: HTMLElement;
let component: ReturnType<typeof mount> | null = null;

beforeEach(() => {
  fetchMock.mockReset().mockImplementation((input, init) =>
    Promise.resolve(
      init?.method === 'POST'
        ? json(500, { error: 'Logging is locked' })
        : json(200, {
            loggers: rows, availableLevels: ['ERROR', 'WARNING', 'DEBUG'],
            page: { total: 1, matched: 1, offset: 0, limit: 200, returned: 1, hasMore: false },
          }),
    ),
  );
  vi.stubGlobal('fetch', fetchMock);
  target = document.createElement('div');
  document.body.append(target);
});
afterEach(() => {
  if (component) unmount(component);
  component = null;
  target.remove();
  vi.unstubAllGlobals();
});

it('a failed level change puts the select back to the level actually configured', async () => {
  component = mount(Loggers, { target, props: { panel } });
  flushSync();
  const select = () => target.querySelector<HTMLSelectElement>('#level-app')!;
  await vi.waitFor(() => expect(select().options.length).toBe(4), { timeout: 1000, interval: 5 });
  select().value = 'DEBUG';
  select().dispatchEvent(new Event('change', { bubbles: true }));
  await vi.waitFor(() => expect(target.querySelector('[role="alert"]')?.textContent).toBe('Logging is locked'), {
    timeout: 1000, interval: 5,
  });
  expect(fetchMock.mock.calls.some(([url, init]) => url === 'api/loggers/app' && init?.method === 'POST')).toBe(true);
  expect(select().value).toBe('');
});
