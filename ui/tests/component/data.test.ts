// @vitest-environment jsdom
import { expect, it } from 'vitest';
import Data from '../../src/views/Data.svelte';
import { harness, json, panel, until } from './support';

const row = (name: string, over: object = {}) => ({
  beanName: name, repositoryInterface: `app.models.${name}`, domainType: `app.models.${name}`, idType: 'Integer',
  storeModule: 'SQLAlchemy', customImplementation: null, queryMethodCount: null, fragmentCount: null,
  table: `${name.toLowerCase()}s`, relationships: [{ name: 'pets', target: 'app.models.Pet', lazy: 'select' }], ...over,
});
const report = (rows: object[], over: object = {}) => ({ springDataPresent: true, total: rows.length, repositories: rows, ...over });
const h = harness();
const text = () => h.text().replace(/\s+/g, ' ');
const mountData = () => h.mount(Data, { panel: panel('data', { title: 'Data' }) });

it('lists one row per mapped class with its table; null counts render as a dash, never 0', async () => {
  h.route((url) => (url === 'api/data/repositories' ? json(200, report([row('Owner'), row('Pet', { relationships: null })])) : undefined));
  mountData();
  await until(() => expect(text()).toContain('Owner'));
  expect(text()).toContain('Pet');
  expect(text()).toContain('owners');
  expect(text()).toContain('—');
  expect(text()).not.toMatch(/\b0\b/);
});

it('shows the unavailable reason when springDataPresent is false', async () => {
  h.route((url) => (url === 'api/data/repositories'
    ? json(200, report([], { springDataPresent: false, unavailableReason: 'pass models= to sharpit.install' }))
    : undefined));
  mountData();
  await until(() => expect(text()).toContain('pass models= to sharpit.install'));
});

it('opening a row loads the detail and lists each relationship with its lazy mode', async () => {
  h.route((url) => {
    if (url === 'api/data/repositories') return json(200, report([row('Owner')]));
    if (url === 'api/data/repositories/Owner') {
      return json(200, { ...row('Owner'), methods: [{ name: 'pets', signature: 'pets -> Pet', origin: 'APPLICATION', query: null, nativeQuery: false, namedQuery: null }], fragments: [], unavailableReason: null });
    }
    return undefined;
  });
  mountData();
  await until(() => expect(text()).toContain('Owner'));
  (h.target.querySelector('button.row') as HTMLButtonElement).click();
  await until(() => expect(text()).toContain('pets -> Pet'));
  expect(text()).toContain('select');
});

it('shows the error state', async () => {
  h.route(() => json(500, { error: 'x' }));
  mountData();
  await until(() => expect(h.target.querySelector('[role="alert"]')?.textContent).toContain('Could not load'));
});
