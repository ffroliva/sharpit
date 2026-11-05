// @vitest-environment jsdom
import { expect, it } from 'vitest';
import FastapiSecurity from '../../src/views/FastapiSecurity.svelte';
import { harness, json, panel, until } from './support';

const chain = {
  order: 0, requestMatcher: 'any request', requestMatcherType: 'ASGI middleware stack',
  filters: ['TrustedHostMiddleware', 'CORSMiddleware'], csrfEnabled: false, corsEnabled: true, sessionManagementPresent: false,
};
const report = {
  springSecurityPresent: true, chains: [chain], limitations: [],
  auth: { authenticationProviderTypes: ['fastapi.security.oauth2.OAuth2PasswordBearer'], userDetailsServiceTypes: [], configuredUsername: null },
};
const row = (method: string, pattern: string, rule: string, over: object = {}) => ({
  method, pattern, handler: 'app:h', secured: rule !== 'unsecured', rule, roles: [], chainIndex: 0,
  matcherDescription: 'any request', description: null, bestEffort: false, ...over,
});
const endpoints = {
  springSecurityPresent: true, handlerMappingAvailable: true, total: 3,
  endpoints: [row('GET', '/health', 'unsecured'), row('GET', '/items', 'authenticated'), row('ANY', '/legacy/{path}', 'unknown', { bestEffort: true })],
};
const h = harness();
const text = () => h.text().replace(/\s+/g, ' ');
const mount = () => h.mount(FastapiSecurity, { panel: panel('fastapi-security', { title: 'FastAPI Security' }) });
const asked: string[] = [];
const routes = (url: string) => {
  asked.push(url);
  if (url === 'api/fastapi-security') return json(200, report);
  if (url === 'api/fastapi-security/endpoints') return json(200, endpoints);
  if (url.startsWith('api/fastapi-security/explain')) {
    return json(200, { matched: true, bestEffort: false, chainIndex: 0, matcherDescription: 'any request', filters: [], rule: 'authenticated', roles: [], pattern: '/items' });
  }
  return undefined;
};

it('lists the middleware stack outermost first with its CORS tag', async () => {
  h.route(routes);
  mount();
  await until(() => expect(text()).toContain('TrustedHostMiddleware'));
  expect([...document.querySelectorAll('ol li')].map((li) => li.textContent)).toEqual(['TrustedHostMiddleware', 'CORSMiddleware']);
  expect(text()).toContain('CORS');
});

it('filters the endpoint table by rule', async () => {
  h.route(routes);
  mount();
  await until(() => expect(document.querySelectorAll('tbody tr')).toHaveLength(3));
  const select = document.querySelector('select[aria-label="Rule"]') as HTMLSelectElement;
  select.value = 'authenticated';
  select.dispatchEvent(new Event('change'));
  await until(() => expect(document.querySelectorAll('tbody tr')).toHaveLength(1));
  expect(document.querySelector('tbody tr')?.textContent).toContain('/items');
});

it('marks a best-effort endpoint', async () => {
  h.route(routes);
  mount();
  await until(() => expect(document.querySelectorAll('tbody tr')).toHaveLength(3));
  const legacy = [...document.querySelectorAll('tbody tr')].find((tr) => tr.textContent?.includes('/legacy'));
  expect(legacy?.textContent).toContain('best effort');
});

it('the explain form sends method and path and shows the rule', async () => {
  h.route(routes);
  mount();
  await until(() => expect(document.querySelector('input[aria-label="Path"]')).not.toBeNull());
  const input = document.querySelector('input[aria-label="Path"]') as HTMLInputElement;
  input.value = '/items';
  input.dispatchEvent(new Event('input'));
  (document.querySelector('form') as HTMLFormElement).dispatchEvent(new Event('submit', { cancelable: true }));
  await until(() => expect(text()).toContain('Matched /items: authenticated'));
  expect(asked).toContain('api/fastapi-security/explain?method=GET&path=%2Fitems');
});

it('lists two endpoint rows with the same method and pattern', async () => {
  const twice = { ...endpoints, total: 2, endpoints: [row('GET', '/dup', 'unknown'), row('GET', '/dup', 'unknown')] };
  h.route((url) => (url === 'api/fastapi-security/endpoints' ? json(200, twice) : routes(url)));
  mount();
  await until(() => expect(document.querySelectorAll('tbody tr')).toHaveLength(2));
});

it('shows a repeated limitation once per occurrence', async () => {
  const why = 'Mounted application at /legacy has no inspectable routes.';
  const repeated = { ...report, limitations: [why, why] };
  h.route((url) => (url === 'api/fastapi-security' ? json(200, repeated) : routes(url)));
  mount();
  await until(() => expect(document.querySelectorAll('p.warn')).toHaveLength(2));
});

it('an app without FastAPI security shows the reason', async () => {
  const reason = 'FastAPI security dependencies are not available: the app is not a FastAPI app';
  h.route((url) => {
    if (url === 'api/fastapi-security') return json(200, { springSecurityPresent: false, chains: [], auth: null, limitations: [reason] });
    if (url === 'api/fastapi-security/endpoints') return json(200, { springSecurityPresent: false, total: 0, endpoints: [] });
    return undefined;
  });
  mount();
  await until(() => expect(text()).toContain(reason));
});
