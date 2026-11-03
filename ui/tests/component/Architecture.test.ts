// @vitest-environment jsdom
import { expect, it } from 'vitest';
import Architecture from '../../src/views/Architecture.svelte';
import { harness, json, panel, until } from './support';

const SEVERITIES = ['CRITICAL', 'HIGH', 'MEDIUM', 'LOW', 'INFO'];
const rule = (id: string, severity: string, dismissed: boolean) => ({
  id,
  name: `${id} name`,
  category: 'Layering',
  severity,
  description: `${id} description`,
  status: 'FAILED',
  violationCount: 1,
  sampleViolations: ['app.api -> app.storage'],
  recommendation: 'Do not import storage from api',
  learnMoreUrl: null,
  dismissed,
});
const report = (status: string, dismissed = false) => ({
  localOnly: true,
  disclaimer: 'Heuristic rules.',
  basePackages: ['app'],
  classesAnalyzed: 10,
  rulesEvaluated: 20,
  violationsFound: dismissed ? 0 : 1,
  severityCounts: SEVERITIES.map((severity) => ({
    severity,
    count: severity === 'HIGH' && !dismissed && status === 'SCANNED' ? 1 : 0,
  })),
  scan: {
    analyzer: 'BootUI ArchUnit hygiene',
    status,
    message: status === 'NOT_SCANNED' ? 'Architecture rules have not run yet.' : 'done',
    scannedAt: status === 'NOT_SCANNED' ? null : 1_761_811_200_000,
  },
  results: status === 'NOT_SCANNED' ? [] : [rule('ARCH-PKG-001', 'HIGH', dismissed)],
  evidence: { usable: status !== 'NOT_SCANNED', coverageComplete: true, limitations: [] },
  violationDetails: { scanId: 'scan1', total: 1, retained: 1, retentionLimit: 10000, truncated: false },
});
const h = harness();
const button = (name: RegExp) =>
  [...h.target.querySelectorAll('button')].find((b) => name.test(b.getAttribute('aria-label') ?? b.textContent ?? ''))!;
const text = () => h.text().replace(/\s+/g, ' ');
const score = () => h.target.querySelector('[data-score]')?.getAttribute('data-score');

it('before the first scan: "Not scanned yet" and nothing is scanned on open', async () => {
  h.route((url) => (url === 'api/architecture' ? json(200, report('NOT_SCANNED')) : undefined));
  h.mount(Architecture, { panel: panel('architecture') });
  await until(() => expect(text()).toContain('Not scanned yet'));
  expect(h.calls('POST')).toEqual([]);
  expect(button(/^(Scan|Run architecture checks)/).disabled).toBe(false);
});

it('Scan posts architecture/scan and shows findings with score', async () => {
  h.route((url, init) => {
    if (url === 'api/architecture') return json(200, report('NOT_SCANNED'));
    if (url === 'api/architecture/scan' && init?.method === 'POST') return json(200, report('SCANNED'));
    return undefined;
  });
  h.mount(Architecture, { panel: panel('architecture') });
  await until(() => expect(text()).toContain('Not scanned yet'));
  button(/^(Scan|Run architecture checks)/).click();
  await until(() => expect(text()).toContain('ARCH-PKG-001'));
  expect(score()).toBe('90');
});

it('dismiss and restore go through dismissed-rules', async () => {
  let dismissed = false;
  h.route((url, init) => {
    if (url === 'api/architecture') return json(200, report('SCANNED', dismissed));
    if (url === 'api/dismissed-rules/ARCH-PKG-001') {
      dismissed = init?.method === 'POST';
      return json(200, { dismissed: dismissed ? ['ARCH-PKG-001'] : [] });
    }
    return undefined;
  });
  h.mount(Architecture, { panel: panel('architecture') });
  await until(() => expect(score()).toBe('90'));
  button(/^Dismiss ARCH-PKG-001/).click();
  await until(() => expect(score()).toBe('100'));
});
