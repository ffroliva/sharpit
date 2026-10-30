// @vitest-environment jsdom
import { flushSync, mount, unmount } from 'svelte';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import Config from '../../src/views/Config.svelte';

const fetchMock = vi.fn<typeof fetch>();
const json = (body: unknown) => new Response(JSON.stringify(body), { status: 200, headers: { 'content-type': 'application/json' } });
const prop = (name: string, value: unknown, source: string, more: Record<string, unknown> = {}) => ({
  name, value, source, origin: null, masked: false, override: false, description: null, defaultValue: null, ...more,
});
const properties = [
  prop('APP_NAME', 'fastapi-sample', 'default (Settings)', { defaultValue: 'fastapi-sample' }),
  prop('COMSPEC', 'C:\Windows\cmd.exe', 'systemEnvironment'),
  prop('DEBUG', 'false', 'systemEnvironment', { defaultValue: false }),
  prop('JWT_ISSUER', 'acme', 'systemEnvironment', { description: 'examples/fastapi_sample/app.py:88', defaultValue: 'fastapi-sample' }),
  prop('PATH', '/usr/bin', 'systemEnvironment'),
];
const report = {
  activeProfiles: [], sources: ['systemEnvironment', 'default (Settings)'], properties,
  propertySuggestions: [{ name: 'JWT_SECRET', type: null, description: 'examples/fastapi_sample/app.py:96', defaultValue: '******' }],
  page: { total: 5, matched: 5, offset: 0, limit: 200, returned: 5, hasMore: false }, overrideCount: 0,
};

let target: HTMLElement;
let component: ReturnType<typeof mount> | null = null;
beforeEach(() => {
  fetchMock.mockReset().mockImplementation(() => Promise.resolve(json(report)));
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

const names = () => [...target.querySelectorAll('tbody tr:not(.group) td:first-child .name')].map((n) => n.textContent);
const until = (fn: () => void) => vi.waitFor(fn, { timeout: 1000, interval: 5 });

it("lists the app's own settings first, with OS environment variables collapsed last behind a count", async () => {
  component = mount(Config, { target, props: {} });
  flushSync();
  await until(() => expect(names()).toContain('APP_NAME'));
  const groups = [...target.querySelectorAll('tbody tr.group')].map((g) => g.textContent!.replace(/\s+/g, ' ').trim());
  expect(groups[0]).toMatch(/^Your application/);
  expect(groups.at(-1)).toMatch(/Other environment variables \(2\)/);
  // declared keys, read keys and the unset suggestion; none of the machine's own variables
  expect(names()).toEqual(['APP_NAME', 'DEBUG', 'JWT_ISSUER', 'JWT_SECRET']);

  const toggle = target.querySelector<HTMLButtonElement>('tr.group button[aria-expanded="false"]')!;
  toggle.click();
  flushSync();
  expect(names()).toEqual(['APP_NAME', 'DEBUG', 'JWT_ISSUER', 'JWT_SECRET', 'COMSPEC', 'PATH']);
  expect(toggle.getAttribute('aria-expanded')).toBe('true');
});

it('shows where a key is read and what an unset key would default to', async () => {
  component = mount(Config, { target, props: {} });
  flushSync();
  await until(() => expect(names()).toContain('JWT_SECRET'));
  const row = (name: string) => [...target.querySelectorAll('tbody tr')].find((r) => r.querySelector('.name')?.textContent === name)!;
  expect(row('JWT_ISSUER').textContent).toContain('read at examples/fastapi_sample/app.py:88');
  expect(row('JWT_SECRET').textContent).toContain('read at examples/fastapi_sample/app.py:96');
  expect(row('JWT_SECRET').textContent).toMatch(/not set.*default \*{6}/);
  expect(row('DEBUG').querySelector('.tag.ok')?.textContent).toBe('won'); // the environment beat the code's default
});
