// @vitest-environment jsdom
import { flushSync, mount, unmount } from 'svelte';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import ServerStatus from '../../src/views/ServerStatus.svelte';
import type { Panel } from '../../src/lib/types';

const fetchMock = vi.fn<typeof fetch>();
const json = (body: unknown) => new Response(JSON.stringify(body), { status: 200, headers: { 'content-type': 'application/json' } });
const panel: Panel = {
  id: 'mcp-server', title: 'MCP server', available: true, unavailableReason: null, enabled: true, readOnly: false, readOnlyReason: null,
};
const status = (enabled: boolean) => ({
  enabled, configuredMode: 'OFF', overridden: enabled, serverName: 'sharpit', serverVersion: '0.1.0', endpoint: '/sharpit/api/mcp',
  protocolVersion: '2025-06-18', maxResults: 200, callCount: 0, totalLatencyMillis: 0, capacityRefusals: 0, timeouts: 0,
  responseLimitRefusals: 0, toolCount: 1,
  tools: [{
    name: 'get_config', panel: 'config', action: false, panelEnabled: true, panelReadOnly: false,
    description: 'Search effective configuration by name or value. Name search ignores case and treats `_` as `.`.',
  }],
});

let target: HTMLElement;
let component: ReturnType<typeof mount> | null = null;
beforeEach(() => {
  vi.stubGlobal('fetch', fetchMock);
  target = document.createElement('div');
  document.body.append(target);
});
afterEach(() => {
  if (component) unmount(component);
  component = null;
  target.remove();
  vi.unstubAllGlobals();
  fetchMock.mockReset();
});
const until = (fn: () => void) => vi.waitFor(fn, { timeout: 1000, interval: 5 });

it('the toggle keeps keyboard focus through the switch', async () => {
  let finish!: (r: Response) => void;
  fetchMock.mockResolvedValueOnce(json(status(false))).mockReturnValueOnce(new Promise<Response>((r) => (finish = r)));
  component = mount(ServerStatus, { target, props: { panel, kind: 'mcp-server' } });
  flushSync();
  const button = () => [...target.querySelectorAll('button')].find((b) => /^Turn|Switching/.test(b.textContent!.trim()))!;
  await until(() => expect(button()).toBeTruthy());
  button().focus();
  button().click();
  await until(() => expect(button().textContent!.trim()).toBe('Switching…'));
  expect(document.activeElement).toBe(button());
  expect(button().getAttribute('aria-disabled')).toBe('true');
  finish(json(status(true)));
  await until(() => expect(button().textContent!.trim()).toBe('Turn off'));
  expect(document.activeElement).toBe(button());
});

it('the CLI example says how to authenticate from outside the browser', async () => {
  fetchMock.mockResolvedValue(json({ ...status(true), endpoint: '/sharpit/api/cli' }));
  component = mount(ServerStatus, { target, props: { panel: { ...panel, id: 'cli', title: 'CLI' }, kind: 'cli' } });
  flushSync();
  await until(() => expect(target.textContent).toContain('curl -X POST'));
  expect(target.textContent).toContain('Authorization: Bearer $SHARPIT_AUTHENTICATION_TOKEN');
});

it('shows the developer an absolute endpoint, a connect command and one-line tool summaries', async () => {
  fetchMock.mockResolvedValue(json(status(true)));
  component = mount(ServerStatus, { target, props: { panel, kind: 'mcp-server' } });
  flushSync();
  await until(() => expect(target.textContent).toContain('get_config'));
  const url = `${location.origin}/sharpit/api/mcp`;
  expect(target.textContent).toContain(url);
  expect(target.textContent).toContain(`claude mcp add --transport http sharpit ${url}`);
  const summary = target.querySelector('details summary')!;
  expect(summary.textContent!.trim()).toBe('Search effective configuration by name or value.');
  expect(target.querySelector('details')!.textContent).toContain('treats _ as .');
});
