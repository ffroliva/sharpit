// @vitest-environment jsdom
import { flushSync, mount, unmount } from 'svelte';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import AdvisorPanel from '../../src/components/AdvisorPanel.svelte';
import { ApiError } from '../../src/lib/api';
import { until } from './support';

const rule = (id: string, severity: string, over: object = {}) => ({
  id, name: `${id} name`, category: 'Naming', severity, description: `${id} description`, status: 'FAILED',
  violationCount: 2, sampleViolations: [`${id} sample 1`, `${id} sample 2`], recommendation: `Fix ${id}`,
  learnMoreUrl: null, dismissed: false, ...over,
});
const counts = (high: number, medium: number) => ['CRITICAL', 'HIGH', 'MEDIUM', 'LOW', 'INFO'].map((severity) => ({
  severity, count: severity === 'HIGH' ? high : severity === 'MEDIUM' ? medium : 0,
}));
const scanned = (dismissHigh = false) => ({
  scan: { status: 'SCANNED', message: 'done', scannedAt: 1_761_811_200_000 },
  severityCounts: dismissHigh ? counts(0, 2) : counts(2, 2),
  evidence: { usable: true, coverageComplete: true, limitations: [] },
  violationDetails: { scanId: 'abc', total: 4, retained: 4, retentionLimit: 10000, truncated: false },
  results: [rule('RAPI-NAME-001', 'HIGH', { dismissed: dismissHigh }), rule('RAPI-RESP-001', 'MEDIUM')],
});
const notScanned = () => ({
  scan: { status: 'NOT_SCANNED', message: 'Not run yet.', scannedAt: null },
  severityCounts: counts(0, 0), evidence: { usable: false, coverageComplete: false, limitations: [] }, results: [],
});

let target: HTMLElement;
let component: ReturnType<typeof mount> | null = null;
let props: Record<string, any> = {};
function render(over: Record<string, unknown>) {
  props = {
    title: 'REST API', report: scanned(), loadError: null, readOnlyReason: null,
    onScan: vi.fn(async () => {}), onDismiss: vi.fn(async () => {}), onRestore: vi.fn(async () => {}),
    loadViolations: vi.fn(async () => ({ violations: [], page: { hasMore: false, offset: 0, returned: 0 } })),
    ...over,
  };
  component = mount(AdvisorPanel, { target, props });
  flushSync();
}
const text = () => target.textContent!.replace(/\s+/g, ' ');
const button = (name: RegExp) => [...target.querySelectorAll('button')].find((b) => name.test(b.getAttribute('aria-label') ?? b.textContent ?? ''))!;
const score = () => target.querySelector('[data-score]')?.getAttribute('data-score');
const phase = () => target.querySelector('[data-phase]')?.getAttribute('data-phase');

beforeEach(() => {
  target = document.createElement('div');
  document.body.append(target);
});
afterEach(() => {
  if (component) unmount(component);
  component = null;
  target.remove();
});

it('shows the score, the severity counts and each failing rule with its samples', () => {
  render({});
  expect(phase()).toBe('results');
  expect(score()).toBe('74'); // 100 - 2 HIGH x 10 - 2 MEDIUM x 3
  expect(text()).toContain('HIGH 2');
  expect(text()).toContain('RAPI-NAME-001');
  expect(text()).toContain('RAPI-NAME-001 sample 1');
  expect(text()).toContain('Fix RAPI-RESP-001');
});

it('never scanned: says so, shows no score, and Scan calls onScan', async () => {
  render({ report: notScanned() });
  expect(phase()).toBe('never-scanned');
  expect(text()).toContain('Not scanned yet');
  button(/^Scan/).click();
  await until(() => expect(props.onScan).toHaveBeenCalledTimes(1));
});

it('busy (409) shows the server message; another error shows the failed state', async () => {
  const onScan = vi.fn()
    .mockRejectedValueOnce(new ApiError(409, { message: 'Scan already running.' }))
    .mockRejectedValueOnce(new ApiError(500, { error: 'Internal Server Error' }));
  render({ report: notScanned(), onScan });
  button(/^Scan/).click();
  await until(() => expect(target.querySelector('[role="status"]')?.textContent).toBe('Scan already running.'));
  expect(phase()).toBe('never-scanned');
  button(/^Scan/).click();
  await until(() => expect(phase()).toBe('failed'));
  expect(target.querySelector('[role="alert"]')?.textContent).toContain('Internal Server Error');
});

it('dismiss calls onDismiss with the rule id; a dismissed rule hides until "Show dismissed", then offers Restore', async () => {
  render({});
  button(/^Dismiss RAPI-NAME-001/).click();
  await until(() => expect(props.onDismiss).toHaveBeenCalledWith('RAPI-NAME-001'));
  component && unmount(component);
  render({ report: scanned(true) });
  expect(score()).toBe('94'); // the server's recomputed counts: the dismissed HIGH no longer costs points
  expect(text()).not.toContain('RAPI-NAME-001 description');
  (target.querySelector('input[type="checkbox"]') as HTMLInputElement).click();
  flushSync();
  expect(text()).toContain('RAPI-NAME-001 description');
  button(/^Restore RAPI-NAME-001/).click();
  await until(() => expect(props.onRestore).toHaveBeenCalledWith('RAPI-NAME-001'));
});

it('a failed dismiss reports the action error and keeps the report', async () => {
  render({ onDismiss: vi.fn(async () => { throw new ApiError(403, { error: 'Panel is read-only' }); }) });
  button(/^Dismiss RAPI-NAME-001/).click();
  await until(() => expect(target.querySelector('[role="alert"]')?.textContent).toContain('Dismiss failed: Panel is read-only'));
  expect(text()).toContain('RAPI-NAME-001 description');
});

it('read-only: Scan and Dismiss are disabled and the reason is shown', () => {
  render({ readOnlyReason: 'Read-only: SHARPIT_READ_ONLY=true' });
  expect(text()).toContain('Read-only: SHARPIT_READ_ONLY=true');
  expect(button(/^Scan/).disabled).toBe(true);
  expect(button(/^Dismiss RAPI-NAME-001/).disabled).toBe(true);
});

it('View violations pages through loadViolations', async () => {
  const loadViolations = vi.fn()
    .mockResolvedValueOnce({ violations: ['GET /a', 'GET /b'], page: { hasMore: true, offset: 0, returned: 2 } })
    .mockResolvedValueOnce({ violations: ['GET /c'], page: { hasMore: false, offset: 2, returned: 1 } });
  render({ loadViolations });
  button(/^View violations for RAPI-NAME-001/).click();
  await until(() => expect(text()).toContain('GET /b'));
  expect(loadViolations).toHaveBeenCalledWith('RAPI-NAME-001', 0);
  button(/^Load more/).click();
  await until(() => expect(text()).toContain('GET /c'));
  expect(loadViolations).toHaveBeenLastCalledWith('RAPI-NAME-001', 2);
  expect(button(/^Load more/)).toBeUndefined();
});

it('load failure shows the error', () => {
  render({ report: null, loadError: 'boom' });
  expect(phase()).toBe('load-failed');
  expect(target.querySelector('[role="alert"]')?.textContent).toContain('boom');
});

it('loading before the report arrives', () => {
  render({ report: null });
  expect(phase()).toBe('loading');
});

it('reopening a rule before the first page returns lists the rows once (final-review F2a)', async () => {
  const pending: Array<(p: object) => void> = [];
  const loadViolations = vi.fn(() => new Promise<any>((resolve) => pending.push(resolve)));
  render({ loadViolations });
  button(/^View violations for RAPI-NAME-001/).click(); // open
  button(/^View violations for RAPI-NAME-001/).click(); // close
  button(/^View violations for RAPI-NAME-001/).click(); // reopen: two requests in flight
  const page = { violations: ['GET /a', 'GET /b'], page: { hasMore: false, offset: 0, returned: 2 } };
  pending.forEach((resolve) => resolve(page));
  await until(() => expect(text()).toContain('GET /b'));
  expect(target.querySelectorAll('.violations li')).toHaveLength(2);
});

it('scanning again closes the open rule and drops its in-flight page (final-review F2c)', async () => {
  let resolveFirst!: (p: object) => void;
  const loadViolations = vi.fn(() => new Promise<any>((resolve) => (resolveFirst = resolve)));
  render({ loadViolations });
  button(/^View violations for RAPI-NAME-001/).click();
  button(/^Scan again/).click();
  await until(() => expect(props.onScan).toHaveBeenCalled());
  resolveFirst({ violations: ['OLD scan row'], page: { hasMore: true, offset: 0, returned: 1 } });
  await new Promise((r) => setTimeout(r, 20));
  expect(text()).not.toContain('OLD scan row');
  expect(button(/^View violations for RAPI-NAME-001/).getAttribute('aria-expanded')).toBe('false');
});
