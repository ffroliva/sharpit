// @vitest-environment jsdom
import { flushSync } from 'svelte';
import { expect, it } from 'vitest';
import HttpProbe from '../../src/views/HttpProbe.svelte';
import { harness, json, page, panel, readOnly, until } from './support';

const result = { status: 200, statusText: 'OK', headers: { 'content-type': 'application/json' }, body: '{"a":1}', durationMs: 7, error: null, truncated: false };
const mappings = { total: 1, mappings: [{ method: 'GET', pattern: '/owners/{id}', handler: 'app.owner', produces: null, consumes: null }], page: page(1) };
const h = harness();

function serve(reply: () => Response = () => json(200, result)) {
  h.route((url, init) => {
    if (url.startsWith('api/mappings/flat')) return json(200, mappings);
    if (url === 'api/http-probe' && init?.method === 'POST') return reply();
    return undefined;
  });
}
const type = (sel: string, value: string, ev = 'input') => {
  const el = h.target.querySelector<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>(sel)!;
  el.value = value;
  el.dispatchEvent(new Event(ev, { bubbles: true }));
  flushSync();
};
const send = () => [...h.target.querySelectorAll('button')].find((b) => b.textContent === 'Send')!;
const body = (n = 0) => JSON.parse(String(h.fetchMock.mock.calls.filter(([, i]) => i?.method === 'POST')[n]![1]!.body));

it('offers route suggestions from mappings', async () => {
  serve();
  h.mount(HttpProbe, { panel: panel('http-probe') });
  await until(() => expect(h.target.querySelectorAll('datalist option')).toHaveLength(1));
  expect(h.target.querySelector<HTMLOptionElement>('datalist option')!.value).toBe('/owners/{id}');
});

it('sends method, path, headers and body, and shows status, timing, headers and the pretty body', async () => {
  serve();
  h.mount(HttpProbe, { panel: panel('http-probe') });
  type('select[aria-label="Method"]', 'POST', 'change');
  type('input[aria-label="Path"]', '/owners');
  type('textarea[aria-label="Headers"]', 'X-Test: 1\naccept: application/json');
  type('textarea[aria-label="Body"]', '{"x":1}');
  send().click();
  await until(() => expect(h.text()).toContain('200 OK'));
  expect(body()).toEqual({ method: 'POST', path: '/owners', headers: { 'X-Test': '1', accept: 'application/json' }, body: '{"x":1}' });
  expect(h.text()).toContain('7 ms');
  expect(h.text()).toContain('content-type');
  expect(h.target.querySelector('pre.body')?.textContent).toBe('{\n  "a": 1\n}');
});

it('keeps history as method and path only, never headers or the body', async () => {
  serve();
  h.mount(HttpProbe, { panel: panel('http-probe') });
  type('input[aria-label="Path"]', '/owners');
  type('textarea[aria-label="Headers"]', 'authorization: Bearer s3cret');
  type('textarea[aria-label="Body"]', 'password=hunter2');
  send().click();
  await until(() => expect(h.text()).toContain('200 OK'));
  const stored = JSON.stringify(Object.fromEntries(Object.entries(sessionStorage)));
  expect(stored).toContain('/owners');
  expect(stored).not.toContain('s3cret');
  expect(stored).not.toContain('hunter2');
  expect(stored).not.toContain('authorization');
  expect(JSON.parse(sessionStorage.getItem('sharpit.probe.history')!)).toEqual([{ method: 'GET', path: '/owners' }]);
});

it('a report-style error and a truncated body are shown, and the body is text, never HTML', async () => {
  serve(() => json(200, { ...result, status: 500, statusText: 'Internal Server Error', body: '<script>alert(1)</script>', error: 'HTTP Probe timed out after 10s', truncated: true }));
  h.mount(HttpProbe, { panel: panel('http-probe') });
  type('input[aria-label="Path"]', '/slow');
  send().click();
  await until(() => expect(h.text()).toContain('HTTP Probe timed out after 10s'));
  expect(h.text()).toContain('truncated');
  expect(h.target.querySelector('pre.body script')).toBeNull();
  expect(h.target.querySelector('pre.body')?.textContent).toBe('<script>alert(1)</script>');
});

it('shows the server error for a refused request', async () => {
  serve(() => json(400, { error: 'HTTP Probe cannot target sharpit itself' }));
  h.mount(HttpProbe, { panel: panel('http-probe') });
  type('input[aria-label="Path"]', '/sharpit/api/panels');
  send().click();
  await until(() => expect(h.target.querySelector('[role="alert"]')?.textContent).toContain('cannot target sharpit itself'));
});

it('a read-only panel disables Send with the reason', async () => {
  serve();
  h.mount(HttpProbe, { panel: readOnly('http-probe') });
  type('input[aria-label="Path"]', '/owners');
  expect(send().disabled).toBe(true);
  expect(send().title).toContain('Read-only');
});

it('is pre-filled from a replay link (q = "METHOD /path")', async () => {
  serve();
  h.mount(HttpProbe, { panel: panel('http-probe'), q: 'DELETE /owners/3' });
  expect(h.target.querySelector<HTMLInputElement>('input[aria-label="Path"]')!.value).toBe('/owners/3');
  expect(h.target.querySelector<HTMLSelectElement>('select[aria-label="Method"]')!.value).toBe('DELETE');
});
