import { flushSync, mount, unmount } from 'svelte';
import { afterEach, beforeEach, vi } from 'vitest';
import type { Panel } from '../../src/lib/types';

export const panel = (id: string, over: Partial<Panel> = {}): Panel => ({
  id, title: id, available: true, unavailableReason: null, enabled: true, readOnly: false, readOnlyReason: null, ...over,
});
export const readOnly = (id: string): Panel => panel(id, { readOnly: true, readOnlyReason: 'Read-only: SHARPIT_READ_ONLY=true' });

export const json = (status: number, body: unknown): Response =>
  new Response(JSON.stringify(body), { status, headers: { 'content-type': 'application/json' } });

export const page = (n: number) => ({ total: n, matched: n, offset: 0, limit: 200, returned: n, hasMore: false });

export const until = (check: () => void) => vi.waitFor(check, { timeout: 1000, interval: 5 });

/** A stand-in for the browser's EventSource that the test drives by hand. */
export class FakeEventSource {
  static instances: FakeEventSource[] = [];
  readyState = 0;
  onopen: (() => void) | null = null;
  onerror: (() => void) | null = null;
  private listeners = new Map<string, ((e: { data: string; lastEventId: string }) => void)[]>();
  constructor(readonly url: string) {
    FakeEventSource.instances.push(this);
  }
  addEventListener(type: string, fn: (e: { data: string; lastEventId: string }) => void) {
    this.listeners.set(type, [...(this.listeners.get(type) ?? []), fn]);
  }
  close() {
    this.readyState = 2;
  }
  open() {
    this.readyState = 1;
    this.onopen?.();
  }
  emit(type: string, data = '{}', id = '') {
    for (const fn of this.listeners.get(type) ?? []) fn({ data, lastEventId: id });
  }
  /** `closed` true is a non-200 answer (503, 403): the browser gives up; false is a plain drop the browser retries. */
  fail(closed: boolean) {
    this.readyState = closed ? 2 : 0;
    this.onerror?.();
  }
  static get last() {
    return FakeEventSource.instances[FakeEventSource.instances.length - 1]!;
  }
}

export type Router = (url: string, init: RequestInit | undefined) => Response | undefined;

/** Mounts views in jsdom with `fetch` routed by `route` (undefined answers 404) and a fake EventSource. */
export function harness() {
  const fetchMock = vi.fn<typeof fetch>();
  const state = { target: null as unknown as HTMLElement, component: null as ReturnType<typeof mount> | null };
  beforeEach(() => {
    FakeEventSource.instances = [];
    vi.stubGlobal('fetch', fetchMock.mockReset());
    vi.stubGlobal('EventSource', FakeEventSource);
    sessionStorage.clear();
    state.target = document.createElement('div');
    document.body.append(state.target);
  });
  afterEach(() => {
    if (state.component) unmount(state.component);
    state.component = null;
    state.target.remove();
    vi.unstubAllGlobals();
  });
  return {
    fetchMock,
    get target() {
      return state.target;
    },
    route(route: Router) {
      fetchMock.mockImplementation((input, init) =>
        Promise.resolve(route(String(input), init) ?? json(404, { error: 'unrouted' })),
      );
    },
    mount(component: Parameters<typeof mount>[0], props: Record<string, unknown> = {}) {
      state.component = mount(component, { target: state.target, props });
      flushSync();
    },
    calls: (method: string) =>
      fetchMock.mock.calls.filter(([, init]) => (init?.method ?? 'GET') === method).map(([url]) => String(url)),
    text: () => state.target.textContent ?? '',
  };
}
