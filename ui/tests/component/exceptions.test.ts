// @vitest-environment jsdom
import { expect, it } from 'vitest';
import Exceptions from '../../src/views/Exceptions.svelte';
import { FakeEventSource, harness, json, panel, readOnly, until } from './support';

const group = {
  id: 'g1', exceptionClassName: 'app.errors.Boom', message: 'it broke', count: 14, firstSeen: 1_700_000_000_000, lastSeen: 1_700_000_100_000,
  location: 'app.py:10', applicationException: true, lastThread: 'MainThread', lastRequestMethod: 'GET', lastRequestPath: '/boom',
  lastHandler: null, lastSource: 'request', lastTraceId: 't1', status: 'OPEN', regressionCount: 0, errorContract: null,
};
const detail = {
  group,
  frames: [
    { declaringClass: 'app.views', methodName: 'boom', fileName: 'views.py', lineNumber: 10, applicationFrame: true },
    { declaringClass: 'starlette.routing', methodName: 'run', fileName: 'routing.py', lineNumber: 5, applicationFrame: false },
  ],
  causes: [{ exceptionClassName: 'builtins.KeyError', message: 'cause text', frames: [], commonFrames: 0 }],
  occurrences: [{ timestamp: 1_700_000_100_000, thread: 'MainThread', requestMethod: 'GET', requestPath: '/boom', handler: null, source: 'request', traceId: 'trace-9' }],
};
const report = (groups: unknown[]) => ({ available: true, unavailableReason: null, maxGroups: 100, totalExceptions: groups.length, groups });
const serve = (groups: unknown[]) => (url: string, init?: RequestInit) => {
  if (url === 'api/exceptions' && (init?.method ?? 'GET') === 'GET') return json(200, report(groups));
  if (url === 'api/exceptions/g1') return json(200, detail);
  if (url === 'api/exceptions/g1/status') return json(200, { ...group, status: 'ACKNOWLEDGED' });
  if (url === 'api/exceptions' && init?.method === 'DELETE') return new Response(null, { status: 204 });
  return undefined;
};

const h = harness();

it('shows loading, then the good-news empty state', async () => {
  h.route(serve([]));
  h.mount(Exceptions, { panel: panel('exceptions') });
  expect(h.text()).toContain('Loading');
  await until(() => expect(h.text()).toContain('No exceptions captured. That is good news.'));
});

it('shows the error state', async () => {
  h.route(() => json(503, { error: 'x' }));
  h.mount(Exceptions, { panel: panel('exceptions') });
  await until(() => expect(h.target.querySelector('[role="alert"]')?.textContent).toContain('Could not load'));
});

it('lists groups with count, status and the application badge, and reloads on a stream tick', async () => {
  h.route(serve([group]));
  h.mount(Exceptions, { panel: panel('exceptions') });
  await until(() => expect(h.text()).toContain('app.errors.Boom'));
  expect(h.text()).toContain('14');
  expect(h.text()).toContain('OPEN');
  expect(h.text()).toContain('application');
  FakeEventSource.last.emit('update');
  await until(() => expect(h.calls('GET').length).toBe(2));
  expect(FakeEventSource.last.url).toBe('api/exceptions/stream');
});

it('opens the detail: application frames highlighted, causes, occurrences linking to the request', async () => {
  h.route(serve([group]));
  h.mount(Exceptions, { panel: panel('exceptions') });
  await until(() => expect(h.text()).toContain('app.errors.Boom'));
  [...h.target.querySelectorAll('button')].find((b) => b.textContent?.includes('app.errors.Boom'))!.click();
  await until(() => expect(h.text()).toContain('views.py:10'));
  expect(h.target.querySelectorAll('li.app')).toHaveLength(1);
  expect(h.text()).toContain('cause text');
  expect(h.target.querySelector('a[href="#/activity?q=trace-9"]')).not.toBeNull();
});

it('a writable panel acknowledges a group and clears all', async () => {
  h.route(serve([group]));
  h.mount(Exceptions, { panel: panel('exceptions') });
  await until(() => expect(h.text()).toContain('app.errors.Boom'));
  [...h.target.querySelectorAll('button')].find((b) => b.textContent === 'Acknowledge')!.click();
  await until(() => expect(h.calls('POST')).toEqual(['api/exceptions/g1/status']));
  expect(JSON.parse(String(h.fetchMock.mock.calls.find(([, i]) => i?.method === 'POST')![1]!.body))).toEqual({ status: 'ACKNOWLEDGED' });
  [...h.target.querySelectorAll('button')].find((b) => b.textContent === 'Clear all')!.click();
  await until(() => expect(h.calls('DELETE')).toEqual(['api/exceptions']));
});

it('a read-only panel disables the actions and says why', async () => {
  h.route(serve([group]));
  h.mount(Exceptions, { panel: readOnly('exceptions') });
  await until(() => expect(h.text()).toContain('app.errors.Boom'));
  const buttons = [...h.target.querySelectorAll('button')].filter((b) => ['Acknowledge', 'Resolve', 'Clear all'].includes(b.textContent ?? ''));
  expect(buttons.length).toBe(3);
  for (const b of buttons) {
    expect(b.disabled).toBe(true);
    expect(b.title).toContain('Read-only');
  }
  expect(h.text()).toContain('Read-only: SHARPIT_READ_ONLY=true');
});

it('a detail that cannot be loaded does not stay on Loading', async () => {
  h.route((url, init) => (url === 'api/exceptions/g1' ? json(404, { error: 'gone' }) : serve([group])(url, init)));
  h.mount(Exceptions, { panel: panel('exceptions') });
  await until(() => expect(h.text()).toContain('app.errors.Boom'));
  [...h.target.querySelectorAll('button')].find((b) => b.textContent === 'app.errors.Boom')!.click();
  await until(() => expect(h.target.querySelector('[role="alert"]')).not.toBeNull());
  expect(h.text()).not.toContain('Loading…');
});
