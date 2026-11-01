// @vitest-environment jsdom
import { expect, it } from 'vitest';
import RestApi from '../../src/views/RestApi.svelte';
import { harness, json, panel, readOnly, until } from './support';

const SEVERITIES = ['CRITICAL', 'HIGH', 'MEDIUM', 'LOW', 'INFO'];
const rule = (id: string, severity: string, dismissed: boolean) => ({
  id, name: `${id} name`, category: 'Naming', severity, description: `${id} description`, status: 'FAILED',
  violationCount: 1, sampleViolations: ['GET /getOwners'], recommendation: 'Use nouns', learnMoreUrl: null, dismissed,
});
const report = (status: string, dismissed = false) => ({
  localOnly: true, disclaimer: 'Heuristic rules.', basePackages: [], controllersAnalyzed: 1, handlersAnalyzed: 3,
  rulesEvaluated: 20, violationsFound: dismissed ? 0 : 1,
  severityCounts: SEVERITIES.map((severity) => ({ severity, count: severity === 'HIGH' && !dismissed && status === 'SCANNED' ? 1 : 0 })),
  scan: { analyzer: 'sharpit rest-api', status, message: status === 'NOT_SCANNED' ? 'REST API rules have not run yet.' : 'done', scannedAt: status === 'NOT_SCANNED' ? null : 1_761_811_200_000 },
  results: status === 'NOT_SCANNED' ? [] : [rule('RAPI-NAME-001', 'HIGH', dismissed)],
  evidence: { usable: status !== 'NOT_SCANNED', coverageComplete: true, limitations: [] },
  violationDetails: { scanId: 'scan1', total: 1, retained: 1, retentionLimit: 10000, truncated: false },
});
const h = harness();
const button = (name: RegExp) => [...h.target.querySelectorAll('button')].find((b) => name.test(b.getAttribute('aria-label') ?? b.textContent ?? ''))!;
const text = () => h.text().replace(/\s+/g, ' ');
const score = () => h.target.querySelector('[data-score]')?.getAttribute('data-score');

it('before the first scan: "Not scanned yet" and nothing is scanned on open', async () => {
  h.route((url) => (url === 'api/rest-api' ? json(200, report('NOT_SCANNED')) : undefined));
  h.mount(RestApi, { panel: panel('rest-api') });
  await until(() => expect(text()).toContain('Not scanned yet'));
  expect(h.calls('POST')).toEqual([]);
  expect(button(/^(Scan|Run REST API checks)/).disabled).toBe(false);
});

it('Scan posts rest-api/scan and shows the findings with the score', async () => {
  h.route((url, init) => {
    if (url === 'api/rest-api') return json(200, report('NOT_SCANNED'));
    if (url === 'api/rest-api/scan' && init?.method === 'POST') return json(200, report('SCANNED'));
    return undefined;
  });
  h.mount(RestApi, { panel: panel('rest-api') });
  await until(() => expect(text()).toContain('Not scanned yet'));
  button(/^(Scan|Run REST API checks)/).click();
  await until(() => expect(text()).toContain('RAPI-NAME-001'));
  expect(score()).toBe('90');
});

it('dismiss and restore go through dismissed-rules and the reloaded report changes the score', async () => {
  let dismissed = false;
  h.route((url, init) => {
    if (url === 'api/rest-api') return json(200, report('SCANNED', dismissed));
    if (url === 'api/dismissed-rules/RAPI-NAME-001') {
      dismissed = init?.method === 'POST';
      return json(200, { dismissed: dismissed ? ['RAPI-NAME-001'] : [] });
    }
    return undefined;
  });
  h.mount(RestApi, { panel: panel('rest-api') });
  await until(() => expect(score()).toBe('90'));
  button(/^Dismiss RAPI-NAME-001/).click();
  await until(() => expect(score()).toBe('100'));
  (h.target.querySelector('input[type="checkbox"]') as HTMLInputElement).click();
  await until(() => expect(button(/^Restore RAPI-NAME-001/)).toBeTruthy());
  button(/^Restore RAPI-NAME-001/).click();
  await until(() => expect(score()).toBe('90'));
  expect(h.calls('DELETE')).toEqual(['api/dismissed-rules/RAPI-NAME-001']);
});

it('View violations reads the paged endpoint with the scan id', async () => {
  h.route((url) => {
    if (url === 'api/rest-api') return json(200, report('SCANNED'));
    if (url.startsWith('api/rest-api/rules/RAPI-NAME-001/violations')) {
      return json(200, { scanId: 'scan1', ruleId: 'RAPI-NAME-001', violationCount: 1, retainedCount: 1, truncated: false,
        violations: ['GET /getOwners (main.get_owners)'], page: { total: 1, matched: 1, offset: 0, limit: 100, returned: 1, hasMore: false } });
    }
    return undefined;
  });
  h.mount(RestApi, { panel: panel('rest-api') });
  await until(() => expect(text()).toContain('RAPI-NAME-001'));
  button(/^View violations for RAPI-NAME-001/).click();
  await until(() => expect(text()).toContain('main.get_owners'));
  expect(h.calls('GET')).toContain('api/rest-api/rules/RAPI-NAME-001/violations?scanId=scan1&offset=0&limit=100');
});

it('read-only: Scan and Dismiss disabled with the reason', async () => {
  h.route((url) => (url === 'api/rest-api' ? json(200, report('SCANNED')) : undefined));
  h.mount(RestApi, { panel: readOnly('rest-api') });
  await until(() => expect(text()).toContain('RAPI-NAME-001'));
  expect(text()).toContain('Read-only: SHARPIT_READ_ONLY=true');
  expect(button(/^(Scan|Run REST API checks)/).disabled).toBe(true);
  expect(button(/^Dismiss RAPI-NAME-001/).disabled).toBe(true);
});

it('shows the error state', async () => {
  h.route(() => json(500, { error: 'Internal Server Error' }));
  h.mount(RestApi, { panel: panel('rest-api') });
  await until(() => expect(h.target.querySelector('[role="alert"]')?.textContent).toContain('Internal Server Error'));
});

it('dismisses one finding', async () => {
  const fingerprint = 'rest-api:RAPI-NAME-001:0123456789abcdef';
  let reloads = 0;
  h.route((url, init) => {
    if (url === 'api/rest-api') { reloads++; return json(200, report('SCANNED')); }
    if (url.startsWith('api/rest-api/rules/RAPI-NAME-001/violations')) {
      return json(200, { scanId: 'scan1', ruleId: 'RAPI-NAME-001', violationCount: 1, retainedCount: 1, truncated: false,
        violations: ['GET /getOwners (main.get_owners)'], fingerprints: [fingerprint],
        page: { total: 1, matched: 1, offset: 0, limit: 100, returned: 1, hasMore: false } });
    }
    if (url === `api/dismissed-rules/${encodeURIComponent(fingerprint)}` && init?.method === 'POST') return json(200, { dismissed: [fingerprint] });
    return undefined;
  });
  h.mount(RestApi, { panel: panel('rest-api') });
  await until(() => expect(text()).toContain('RAPI-NAME-001'));
  button(/^View violations for RAPI-NAME-001/).click();
  await until(() => expect(button(/^Dismiss finding/)).toBeTruthy());
  button(/^Dismiss finding/).click();
  await until(() => expect(h.calls('POST')).toContain(`api/dismissed-rules/${encodeURIComponent(fingerprint)}`));
  await until(() => expect(reloads).toBe(2)); // the report is reloaded so the panel counts follow
});

it('read-only: the finding action is disabled', async () => {
  h.route((url) => {
    if (url === 'api/rest-api') return json(200, report('SCANNED'));
    if (url.startsWith('api/rest-api/rules/RAPI-NAME-001/violations')) {
      return json(200, { scanId: 'scan1', ruleId: 'RAPI-NAME-001', violationCount: 1, retainedCount: 1, truncated: false,
        violations: ['GET /getOwners'], fingerprints: ['rest-api:RAPI-NAME-001:0123456789abcdef'],
        page: { total: 1, matched: 1, offset: 0, limit: 100, returned: 1, hasMore: false } });
    }
    return undefined;
  });
  h.mount(RestApi, { panel: readOnly('rest-api') });
  await until(() => expect(text()).toContain('RAPI-NAME-001'));
  button(/^View violations for RAPI-NAME-001/).click();
  await until(() => expect(button(/^Dismiss finding/)).toBeTruthy());
  expect(button(/^Dismiss finding/).disabled).toBe(true);
});

it('restores a dismissed finding', async () => {
  const fingerprint = 'rest-api:RAPI-NAME-001:0123456789abcdef';
  h.route((url, init) => {
    if (url === 'api/rest-api') return json(200, report('SCANNED'));
    if (url.startsWith('api/rest-api/rules/RAPI-NAME-001/violations')) {
      return json(200, { scanId: 'scan1', ruleId: 'RAPI-NAME-001', violationCount: 1, retainedCount: 1, truncated: false,
        violations: ['GET /getOwners (main.get_owners)'], fingerprints: [fingerprint],
        page: { total: 1, matched: 1, offset: 0, limit: 100, returned: 1, hasMore: false } });
    }
    if (url === `api/dismissed-rules/${encodeURIComponent(fingerprint)}`) return json(200, { dismissed: init?.method === 'POST' ? [fingerprint] : [] });
    return undefined;
  });
  h.mount(RestApi, { panel: panel('rest-api') });
  await until(() => expect(text()).toContain('RAPI-NAME-001'));
  button(/^View violations for RAPI-NAME-001/).click();
  await until(() => expect(button(/^Dismiss finding/)).toBeTruthy());
  button(/^Dismiss finding/).click();
  await until(() => expect(button(/^Restore finding/)).toBeTruthy());
  button(/^Restore finding/).click();
  await until(() => expect(h.calls('DELETE')).toEqual([`api/dismissed-rules/${encodeURIComponent(fingerprint)}`]));
  await until(() => expect(button(/^Dismiss finding/)).toBeTruthy());
});

it('remembers dismissed findings after reopening the drawer', async () => {
  const fingerprint = 'rest-api:RAPI-NAME-001:0123456789abcdef';
  let dismissed: string[] = [];
  h.route((url, init) => {
    if (url === 'api/rest-api') return json(200, report('SCANNED'));
    if (url.startsWith('api/rest-api/rules/RAPI-NAME-001/violations')) {
      return json(200, { scanId: 'scan1', ruleId: 'RAPI-NAME-001', violationCount: 1, retainedCount: 1, truncated: false,
        violations: ['GET /getOwners (main.get_owners)'], fingerprints: [fingerprint],
        page: { total: 1, matched: 1, offset: 0, limit: 100, returned: 1, hasMore: false } });
    }
    if (url === `api/dismissed-rules/${encodeURIComponent(fingerprint)}` && init?.method === 'POST') return json(200, { dismissed: (dismissed = [fingerprint]) });
    if (url === 'api/dismissed-rules') return json(200, { dismissed });
    return undefined;
  });
  h.mount(RestApi, { panel: panel('rest-api') });
  await until(() => expect(text()).toContain('RAPI-NAME-001'));
  button(/^View violations for RAPI-NAME-001/).click();
  await until(() => expect(button(/^Dismiss finding/)).toBeTruthy());
  button(/^Dismiss finding/).click();
  await until(() => expect(button(/^Restore finding/)).toBeTruthy());
  button(/^View violations for RAPI-NAME-001/).click(); // close
  await until(() => expect(button(/^Restore finding/)).toBeFalsy());
  button(/^View violations for RAPI-NAME-001/).click(); // reopen
  await until(() => expect(button(/^Restore finding/)).toBeTruthy());
});
