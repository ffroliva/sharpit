// @vitest-environment jsdom
import { readFileSync } from 'node:fs';
import { expect, it } from 'vitest';
import { PANEL_04_IDS } from '../../src/lib/panels04';
import type { Panel04Id } from '../../src/lib/types';
import { harness, panel } from './support';

/** Each 0.4 panel's placeholder view (F1b); its owning lane replaces only this file and flips its two flag files. */
const VIEWS: Record<Panel04Id, string> = {
  data: 'Data',
  transactions: 'Transactions',
  postgresql: 'PostgreSql',
  mysql: 'MySql',
  traces: 'Traces',
  security: 'Security',
  'security-logs': 'SecurityLogs',
  'database-advisor': 'DatabaseAdvisor',
  architecture: 'Architecture',
  'sqlalchemy-statistics': 'SqlalchemyStatistics',
  'fastapi-security': 'FastapiSecurity',
  fastapi: 'Fastapi',
};
const modules = import.meta.glob<{ default: Parameters<ReturnType<typeof harness>['mount']>[0] }>('../../src/views/*.svelte', {
  eager: true,
});
const app = readFileSync('src/App.svelte', 'utf8'); // vitest runs from ui/
const h = harness();

it('names a placeholder view for every 0.4 panel', () => {
  expect(Object.keys(VIEWS).sort()).toEqual([...PANEL_04_IDS].sort());
});

it.each(Object.entries(VIEWS))('renders the %s placeholder with its panel title', (id, view) => {
  const module = modules[`../../src/views/${view}.svelte`];
  expect(module, view).toBeDefined();
  h.mount(module!.default, { panel: panel(id, { title: `${view} title` }) });
  expect(h.target.textContent).toContain(`${view} title`);
});

it('routes every 0.4 placeholder in App.svelte only behind its implemented flag', () => {
  for (const [id, view] of Object.entries(VIEWS)) {
    expect(app, view).toContain(`import ${view} from './views/${view}.svelte';`);
    expect(app, view).toContain(`current.id === '${id}' && panelImplemented('${id}')}<${view} panel={current} />`);
  }
});
