// @vitest-environment jsdom
import { expect, it } from 'vitest';
import Traces from '../../src/views/Traces.svelte';
import { harness, json, panel, until } from './support';

const summary = {
  traceId: 'c9bdc3cbe2a6ed25ef75355d78db82b4', rootSpanName: 'GET /owners', httpPath: '/owners', services: ['api'],
  startEpochNanos: 1_000, endEpochNanos: 48_969_600, durationNanos: 48_968_600, spanCount: 2, hasError: false, hasAi: false,
};
const report = (over: object = {}) => ({ enabled: true, unavailableReason: null, retained: 1, capacity: 1000, traces: [summary], ...over });
const span = (id: string, parent: string | null, start: number, duration: number) => ({
  traceId: summary.traceId, spanId: id, parentSpanId: parent, name: `span ${id}`, kind: 'SERVER', serviceName: 'api',
  scope: 'tests', startEpochNanos: start, endEpochNanos: start + duration, durationNanos: duration, statusCode: 'UNSET',
  statusMessage: null, attributes: [{ key: 'http.route', type: 'STRING', value: '/owners' }], events: [],
});
const h = harness();
const text = () => h.text().replace(/\s+/g, ' ');
const mount = () => h.mount(Traces, { panel: panel('traces', { title: 'Traces' }) });

it('lists traces with nanoseconds rendered as milliseconds', async () => {
  h.route((url) => (url === 'api/traces' ? json(200, report()) : undefined));
  mount();
  await until(() => expect(text()).toContain('GET /owners'));
  expect(text()).toContain('49.0 ms');
});

it('opens a trace as a waterfall of its spans', async () => {
  h.route((url) => {
    if (url === 'api/traces') return json(200, report());
    if (url === `api/traces/${summary.traceId}`) return json(200, { traceId: summary.traceId, spans: [span('a', null, 0, 40_000_000), span('b', 'a', 10_000_000, 20_000_000)] });
    return undefined;
  });
  mount();
  await until(() => expect(text()).toContain('GET /owners'));
  (document.querySelector('button.link') as HTMLButtonElement).click();
  await until(() => expect(document.querySelectorAll('.bar')).toHaveLength(2));
  expect((document.querySelectorAll('.bar')[1] as HTMLElement).style.left).toBe('25%');
  expect(text()).toContain('20.0 ms');
});

it('shows the reason when traces are unavailable', async () => {
  const reason = 'OpenTelemetry SDK is not imported by this application';
  h.route((url) => (url === 'api/traces' ? json(200, report({ enabled: false, unavailableReason: reason, traces: [] })) : undefined));
  mount();
  await until(() => expect(text()).toContain(reason));
});

it('shows span status and event details', async () => {
  const richSpan = {
    ...span('a', null, 0, 40_000_000),
    statusCode: 'ERROR', statusMessage: 'unique violation detail',
    events: [{ name: 'exception', timeOffsetNanos: 5, attributes: [{ key: 'exception.type', type: 'STRING', value: 'ValueError' }] }],
  };
  h.route((url) => {
    if (url === 'api/traces') return json(200, report());
    if (url === `api/traces/${summary.traceId}`) return json(200, { traceId: summary.traceId, spans: [richSpan] });
    return undefined;
  });
  mount();
  await until(() => expect(text()).toContain('GET /owners'));
  (document.querySelector('button.link') as HTMLButtonElement).click();
  await until(() => expect(text()).toContain('unique violation detail'));
  expect(text()).toContain('exception');
  expect(text()).toContain('ValueError');
});

it('ignores a stale detail response after another trace was opened', async () => {
  const second = { ...summary, traceId: 'another-trace' };
  const pending = new Map<string, (response: Response) => void>();
  h.fetchMock.mockImplementation((input) => {
    const url = String(input);
    if (url === 'api/traces') return Promise.resolve(json(200, report({ traces: [summary, second] })));
    return new Promise((resolve) => pending.set(url, resolve));
  });
  mount();
  await until(() => expect(document.querySelectorAll('button.link')).toHaveLength(2));
  const buttons = document.querySelectorAll('button.link');
  (buttons[0] as HTMLButtonElement).click();
  (buttons[1] as HTMLButtonElement).click();
  pending.get(`api/traces/${second.traceId}`)?.(json(200, { traceId: second.traceId, spans: [span('new', null, 0, 1)] }));
  await until(() => expect(text()).toContain('span new'));
  pending.get(`api/traces/${summary.traceId}`)?.(json(200, { traceId: summary.traceId, spans: [span('stale', null, 0, 1)] }));
  await new Promise((resolve) => setTimeout(resolve, 0));
  expect(text()).toContain('span new');
  expect(text()).not.toContain('span stale');
});
