// @vitest-environment jsdom
import { expect, it } from 'vitest';
import Fastapi from '../../src/views/Fastapi.svelte';
import { harness, json, panel, until } from './support';

const SEVERITIES = ['CRITICAL', 'HIGH', 'MEDIUM', 'LOW', 'INFO'];
const rule = {
  id: 'FASTAPI-ASYNC-002', name: 'Blocking call inside an async endpoint', category: 'Performance and concurrency',
  severity: 'HIGH', description: 'd', status: 'VIOLATION', violationCount: 1,
  sampleViolations: ['GET /slow (app.main:slow) calls time.sleep (line 7)'], recommendation: 'r', learnMoreUrl: null,
  dismissed: false, sampleLocations: [],
};
const report = (status: string) => ({
  localOnly: true, disclaimer: 'Bounded FastAPI route and source checks.', inspected: [], componentsAnalyzed: 2,
  rulesEvaluated: 10, violationsFound: status === 'SCANNED' ? 1 : 0,
  severityCounts: SEVERITIES.map((severity) => ({ severity, count: severity === 'HIGH' && status === 'SCANNED' ? 1 : 0 })),
  scan: { analyzer: 'sharpit FastAPI Advisor', status, message: 'm', scannedAt: status === 'NOT_SCANNED' ? null : 1_761_811_200_000 },
  results: status === 'NOT_SCANNED' ? [] : [rule],
  analysisErrors: [],
  evidence: { usable: status !== 'NOT_SCANNED', coverageComplete: true, limitations: [] },
  violationDetails: { scanId: 'scan1', total: 1, retained: 1, retentionLimit: 10000, truncated: false },
});
const h = harness();
const button = (name: RegExp) => [...h.target.querySelectorAll('button')].find((b) => name.test(b.getAttribute('aria-label') ?? b.textContent ?? ''))!;
const text = () => h.text().replace(/\s+/g, ' ');

it('opens on the cached report and never scans by itself', async () => {
  h.route((url) => (url === 'api/fastapi' ? json(200, report('NOT_SCANNED')) : undefined));
  h.mount(Fastapi, { panel: panel('fastapi', { title: 'FastAPI' }) });
  await until(() => expect(text()).toContain('Not scanned yet'));
  expect(h.calls('POST')).toEqual([]);
});

it('Run FastAPI checks posts fastapi/scan and lists the finding', async () => {
  h.route((url, init) => {
    if (url === 'api/fastapi') return json(200, report('NOT_SCANNED'));
    if (url === 'api/fastapi/scan' && init?.method === 'POST') return json(200, report('SCANNED'));
    return undefined;
  });
  h.mount(Fastapi, { panel: panel('fastapi', { title: 'FastAPI' }) });
  await until(() => expect(text()).toContain('Not scanned yet'));
  button(/^Run FastAPI checks/).click();
  await until(() => expect(text()).toContain('FASTAPI-ASYNC-002'));
  expect(text()).toContain('2 route handlers analysed');
});
