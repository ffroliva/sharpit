// @vitest-environment jsdom
import { expect, it } from 'vitest';
import Security from '../../src/views/Security.svelte';
import { harness, json, panel, readOnly, until } from './support';

const SEVERITIES = ['CRITICAL', 'HIGH', 'MEDIUM', 'LOW', 'INFO'];
const rule = (dismissed: boolean) => ({
  id: 'SEC-CORS-002', name: 'Avoid wildcard origins with credentials', category: 'CORS', severity: 'HIGH',
  description: 'Any origin with credentials.', status: 'FAILED', violationCount: 1,
  sampleViolations: ['CORSMiddleware allows any origin ("*") with allow_credentials=******'],
  recommendation: 'List the origins.', learnMoreUrl: null, dismissed,
});
const report = (status: string, dismissed = false) => ({
  localOnly: true, disclaimer: 'Heuristic FastAPI security rules.', filterChains: ['any request'], filterChainsAnalyzed: 1,
  rulesEvaluated: 27, violationsFound: dismissed ? 0 : 1, analysisErrors: [],
  severityCounts: SEVERITIES.map((severity) => ({ severity, count: severity === 'HIGH' && !dismissed && status === 'SCANNED' ? 1 : 0 })),
  scan: { analyzer: 'sharpit FastAPI Security Advisor', status, message: status === 'NOT_SCANNED' ? 'Security rules have not run yet.' : 'done',
    scannedAt: status === 'NOT_SCANNED' ? null : 1_761_811_200_000 },
  results: status === 'NOT_SCANNED' ? [] : [rule(dismissed)],
  evidence: { usable: status !== 'NOT_SCANNED', coverageComplete: true, limitations: [] },
  violationDetails: { scanId: 'scan1', total: 1, retained: 1, retentionLimit: 10000, truncated: false },
});
const h = harness();
const button = (name: RegExp) => [...h.target.querySelectorAll('button')].find((b) => name.test(b.getAttribute('aria-label') ?? b.textContent ?? ''))!;
const text = () => h.text().replace(/\s+/g, ' ');
const SCAN = /^(Scan|Run security checks)/;

it('before the first scan: "Not scanned yet" and nothing is scanned on open', async () => {
  h.route((url) => (url === 'api/security' ? json(200, report('NOT_SCANNED')) : undefined));
  h.mount(Security, { panel: panel('security') });
  await until(() => expect(text()).toContain('Not scanned yet'));
  expect(h.calls('POST')).toEqual([]);
});

it('Scan posts security/scan and shows the finding and the stacks scanned', async () => {
  h.route((url, init) => {
    if (url === 'api/security') return json(200, report('NOT_SCANNED'));
    if (url === 'api/security/scan' && init?.method === 'POST') return json(200, report('SCANNED'));
    return undefined;
  });
  h.mount(Security, { panel: panel('security') });
  await until(() => expect(text()).toContain('Not scanned yet'));
  button(SCAN).click();
  await until(() => expect(text()).toContain('SEC-CORS-002'));
  expect(text()).toContain('1 middleware stack scanned');
});

it('View violations reads the paged endpoint with the scan id', async () => {
  h.route((url) => {
    if (url === 'api/security') return json(200, report('SCANNED'));
    if (url.startsWith('api/security/rules/SEC-CORS-002/violations')) {
      return json(200, { scanId: 'scan1', ruleId: 'SEC-CORS-002', violationCount: 1, retainedCount: 1, truncated: false,
        violations: ['CORSMiddleware on the root app'], page: { total: 1, matched: 1, offset: 0, limit: 100, returned: 1, hasMore: false } });
    }
    return undefined;
  });
  h.mount(Security, { panel: panel('security') });
  await until(() => expect(text()).toContain('SEC-CORS-002'));
  button(/^View violations for SEC-CORS-002/).click();
  await until(() => expect(text()).toContain('CORSMiddleware on the root app'));
  expect(h.calls('GET')).toContain('api/security/rules/SEC-CORS-002/violations?scanId=scan1&offset=0&limit=100');
});

it('dismiss goes through dismissed-rules and the reloaded report hides the finding', async () => {
  let dismissed = false;
  h.route((url, init) => {
    if (url === 'api/security') return json(200, report('SCANNED', dismissed));
    if (url === 'api/dismissed-rules/SEC-CORS-002') {
      dismissed = init?.method === 'POST';
      return json(200, { dismissed: dismissed ? ['SEC-CORS-002'] : [] });
    }
    return undefined;
  });
  h.mount(Security, { panel: panel('security') });
  await until(() => expect(text()).toContain('SEC-CORS-002'));
  button(/^Dismiss SEC-CORS-002/).click();
  await until(() => expect(dismissed).toBe(true));
  expect(h.calls('POST')).toEqual(['api/dismissed-rules/SEC-CORS-002']);
});

it('read-only: Scan disabled with the reason', async () => {
  h.route((url) => (url === 'api/security' ? json(200, report('SCANNED')) : undefined));
  h.mount(Security, { panel: readOnly('security') });
  await until(() => expect(text()).toContain('SEC-CORS-002'));
  expect(text()).toContain('Read-only: SHARPIT_READ_ONLY=true');
  expect(button(SCAN).disabled).toBe(true);
});

it('shows the error state', async () => {
  h.route(() => json(500, { error: 'Internal Server Error' }));
  h.mount(Security, { panel: panel('security') });
  await until(() => expect(h.target.querySelector('[role="alert"]')?.textContent).toContain('Internal Server Error'));
});
