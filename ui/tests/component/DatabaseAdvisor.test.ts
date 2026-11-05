// @vitest-environment jsdom
import { expect, it } from 'vitest';
import DatabaseAdvisor from '../../src/views/DatabaseAdvisor.svelte';
import { harness, json, panel, until } from './support';

const SEVERITIES = ['CRITICAL', 'HIGH', 'MEDIUM', 'LOW', 'INFO'];
const scanned = (status: string) => status !== 'NOT_SCANNED';
const report = (status: string) => ({
  localOnly: true, disclaimer: 'Read-only schema introspection.', dataSourceNames: scanned(status) ? ['db'] : [],
  dataSources: scanned(status)
    ? [{ name: 'db', product: 'SQLite', dialect: 'sqlite', identifierCase: null, status: 'PARTIAL', message: null, tablesAnalyzed: 2, truncated: true }]
    : [],
  tablesAnalyzed: scanned(status) ? 2 : 0, rulesEvaluated: scanned(status) ? 13 : 0, violationsFound: scanned(status) ? 1 : 0,
  rulesSkipped: 0, rulesErrored: 0, truncated: scanned(status),
  severityCounts: SEVERITIES.map((severity) => ({ severity, count: severity === 'MEDIUM' && scanned(status) ? 1 : 0 })),
  scan: { analyzer: 'sharpit Database Advisor', status, message: scanned(status) ? 'done' : 'Database Advisor has not run yet.',
    scannedAt: scanned(status) ? 1_761_811_200_000 : null },
  results: scanned(status)
    ? [{ id: 'DB-SCHEMA-001', name: 'Tables without a primary key', category: 'Schema', severity: 'MEDIUM', description: 'd',
        status: 'VIOLATION', violationCount: 1, sampleViolations: ['Datasource `db`: table `audit_log` has no primary key.'],
        recommendation: 'r', learnMoreUrl: null, dismissed: false }]
    : [],
  diagnostics: scanned(status)
    ? [{ source: 'db', level: 'WARNING', message: 'A scan bound was reached, so some tables, columns or indexes were not read.' },
       { source: 'DB-POOL-001', level: 'INFO', message: 'Skipped: no server.' }]
    : [],
  evidence: { usable: scanned(status), coverageComplete: false, limitations: [] },
  violationDetails: { scanId: 'scan1', total: 1, retained: 1, retentionLimit: 10000, truncated: false, locationNotes: [], changes: null },
  suppression: { suppressedFindings: 0, incompleteRules: [], findings: [], omitted: 0 },
});
const h = harness();
const button = (name: RegExp) => [...h.target.querySelectorAll('button')].find((b) => name.test(b.getAttribute('aria-label') ?? b.textContent ?? ''))!;
const text = () => h.text().replace(/\s+/g, ' ');

it('before the first scan: "Not scanned yet" and nothing is scanned on open', async () => {
  h.route((url) => (url === 'api/database-advisor' ? json(200, report('NOT_SCANNED')) : undefined));
  h.mount(DatabaseAdvisor, { panel: panel('database-advisor') });
  await until(() => expect(text()).toContain('Not scanned yet'));
  expect(h.calls('POST')).toEqual([]);
  expect(button(/^Run Database checks/)).toBeTruthy();
});

it('Run Database checks posts database-advisor/scan and shows the findings and each datasource', async () => {
  h.route((url, init) => {
    if (url === 'api/database-advisor') return json(200, report('NOT_SCANNED'));
    if (url === 'api/database-advisor/scan' && init?.method === 'POST') return json(200, report('SCANNED'));
    return undefined;
  });
  h.mount(DatabaseAdvisor, { panel: panel('database-advisor') });
  await until(() => expect(text()).toContain('Not scanned yet'));
  button(/^Run Database checks/).click();
  await until(() => expect(text()).toContain('DB-SCHEMA-001'));
  expect(text()).toContain('db SQLite PARTIAL 2 tables');
});

it('lists warning diagnostics and leaves informational ones out of the list', async () => {
  h.route((url) => (url === 'api/database-advisor' ? json(200, report('SCANNED')) : undefined));
  h.mount(DatabaseAdvisor, { panel: panel('database-advisor') });
  await until(() => expect(text()).toContain('A scan bound was reached'));
  expect(text()).not.toContain('Skipped: no server.');
  const diagnostics = h.target.querySelector('section[aria-label="Diagnostics"]');
  expect(diagnostics).not.toBeNull();
  expect(diagnostics!.closest('.panel-body')).not.toBeNull();
});

it('View violations reads the paged endpoint with the scan id', async () => {
  h.route((url) => {
    if (url === 'api/database-advisor') return json(200, report('SCANNED'));
    if (url.startsWith('api/database-advisor/rules/DB-SCHEMA-001/violations')) {
      return json(200, { scanId: 'scan1', ruleId: 'DB-SCHEMA-001', violationCount: 1, retainedCount: 1, truncated: false,
        violations: ['table `audit_log` has no primary key'], page: { total: 1, matched: 1, offset: 0, limit: 100, returned: 1, hasMore: false } });
    }
    return undefined;
  });
  h.mount(DatabaseAdvisor, { panel: panel('database-advisor') });
  await until(() => expect(text()).toContain('DB-SCHEMA-001'));
  button(/^View violations for DB-SCHEMA-001/).click();
  await until(() => expect(h.calls('GET')).toContain('api/database-advisor/rules/DB-SCHEMA-001/violations?scanId=scan1&offset=0&limit=100'));
});
