// @vitest-environment jsdom
import { expect, it, vi } from 'vitest';
import Health from '../../src/views/Health.svelte';
import { harness, json, panel, readOnly, until } from './support';

const node = (name: string, status: string, over: object = {}) => ({
  name, status, details: null, components: [], available: true, unavailableReason: null, guidanceReason: null, setup: [], ...over,
});
const tree = node('application', 'UP', { details: { checkedAt: 1_700_000_000_000 }, components: [node('db', 'UP', { components: [node('main', 'DOWN', { details: { error: 'refused' } })] })] });
const serve = (root: object) => (url: string, init?: RequestInit) => {
  if (url === 'api/health') return json(200, root);
  if (url === 'api/health/check' && init?.method === 'POST') return json(200, root);
  return undefined;
};
const h = harness();
const runChecks = () => [...h.target.querySelectorAll('button')].find((b) => b.textContent === 'Run checks')!;

it('shows loading, then the tree with status words', async () => {
  h.route(serve(tree));
  h.mount(Health, { panel: panel('health') });
  expect(h.text()).toContain('Loading');
  await until(() => expect(h.text()).toContain('refused'));
  expect(h.text()).toContain('DOWN');
  expect(h.text()).toContain('main');
});

it('a writable panel posts health/check once on open and again on each refresh', async () => {
  h.route(serve(tree));
  h.mount(Health, { panel: panel('health') });
  await until(() => expect(h.text()).toContain('refused'));
  expect(h.calls('POST')).toEqual(['api/health/check']);
  runChecks().click();
  await until(() => expect(h.calls('POST')).toHaveLength(2));
});

it('never re-runs the checks on a timer', async () => {
  const timer = vi.spyOn(globalThis, 'setInterval');
  h.route(serve(tree));
  h.mount(Health, { panel: panel('health') });
  await until(() => expect(h.text()).toContain('refused'));
  expect(timer).not.toHaveBeenCalled();
  timer.mockRestore();
});

it('a read-only panel never posts: it shows the cache and a disabled button with the reason', async () => {
  h.route(serve(tree));
  h.mount(Health, { panel: readOnly('health') });
  await until(() => expect(h.text()).toContain('refused'));
  expect(h.calls('POST')).toEqual([]);
  expect(runChecks().disabled).toBe(true);
  expect(runChecks().title).toContain('Read-only');
});

it('shows the setup steps when there is nothing to check', async () => {
  const empty = node('application', 'DISABLED', {
    available: false, unavailableReason: 'No engines and no health checks',
    setup: [{ title: 'Register your database engines', description: 'Pings each engine.', snippets: ['sharpit.install(app, engines=[engine])'] }],
  });
  h.route(serve(empty));
  h.mount(Health, { panel: panel('health') });
  await until(() => expect(h.text()).toContain('Register your database engines'));
  expect(h.text()).toContain('sharpit.install(app, engines=[engine])');
  expect(h.text()).toContain('No engines and no health checks');
});

it('shows the error state', async () => {
  h.route(() => json(500, { error: 'x' }));
  h.mount(Health, { panel: readOnly('health') });
  await until(() => expect(h.target.querySelector('[role="alert"]')?.textContent).toContain('Could not load'));
});
