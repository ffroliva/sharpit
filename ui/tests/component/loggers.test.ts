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

it('a level change reloads the visible rows, so descendants show their new effective level', async () => {
  let level: string | null = null;
  const listed = () => [
    { name: 'app', configuredLevel: level, effectiveLevel: level ?? 'WARNING' },
    { name: 'app.db', configuredLevel: null, effectiveLevel: level ?? 'WARNING' },
  ];
  fetchMock.mockImplementation((_input, init) => {
    if (init?.method === 'POST') {
      level = JSON.parse(String(init.body)).level;
      return Promise.resolve(json(200, listed()[0]));
    }
    return Promise.resolve(json(200, {
      loggers: listed(), availableLevels: ['CRITICAL', 'ERROR', 'WARNING', 'DEBUG', 'NOTSET'],
      page: { total: 2, matched: 2, offset: 0, limit: 200, returned: 2, hasMore: false },
    }));
  });
  component = mount(Loggers, { target, props: { panel } });
  flushSync();
  const select = () => target.querySelector<HTMLSelectElement>('#level-app')!;
  const effective = (name: string) => target.querySelector(`#level-${CSS.escape(name)}`)!.closest('tr')!.children[1]!.textContent;
  await vi.waitFor(() => expect(select().options.length).toBe(5), { timeout: 1000, interval: 5 });

  // NOTSET is how Python spells inherit: one option, which names the level it inherits
  expect([...select().options].map((o) => o.textContent)).toEqual(['inherit (WARNING)', 'CRITICAL', 'ERROR', 'WARNING', 'DEBUG']);

  select().focus();
  select().value = 'ERROR';
  select().dispatchEvent(new Event('change', { bubbles: true }));
  await vi.waitFor(() => expect(effective('app.db')).toBe('ERROR'), { timeout: 1000, interval: 5 });
  expect(document.activeElement).toBe(select()); // never dropped to <body> while the change is pending
  expect(select().value).toBe('ERROR');
});

it('the filter goes into the URL hash, and the count is not announced while it loads', async () => {
  history.replaceState(null, '', '#/loggers');
  component = mount(Loggers, { target, props: { panel } });
  flushSync();
  const count = () => target.querySelector('.count')!;
  await vi.waitFor(() => expect(count().textContent).toContain('1 of 1'), { timeout: 1000, interval: 5 });
  const filter = target.querySelector<HTMLInputElement>('.panel-filter')!;
  filter.value = 'app.db';
  filter.dispatchEvent(new Event('input', { bubbles: true }));
  flushSync();
  expect(count().getAttribute('aria-busy')).toBe('true'); // screen readers hold the "…" placeholder back
  await vi.waitFor(() => expect(location.hash).toBe('#/loggers?q=app.db'), { timeout: 1000, interval: 5 });
  await vi.waitFor(() => expect(count().getAttribute('aria-busy')).toBe('false'), { timeout: 1000, interval: 5 });
});
