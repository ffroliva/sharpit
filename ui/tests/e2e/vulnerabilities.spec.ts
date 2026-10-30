// Spec §10 check 6: every vulnerabilities state. Never-scanned is the real server; the scan states are stubbed with
// page.route on top of the server's own report, so no scan ever reaches OSV.dev and the shapes stay the contract's.
import { expect, test, type Page, type Route } from '@playwright/test';
import { openPanel } from './support';

type Report = {
  scanningEnabled: boolean;
  total: number;
  vulnerable: number;
  severityCounts: { severity: string; count: number }[];
  scan: Record<string, unknown>;
  dependencies: { packageName: string; vulnerabilityCount: number; highestSeverity: string; vulnerabilities: unknown[] }[];
};

const ADVISORY = 'GHSA-e2e0-0000-0001';

/** The server's never-scanned report turned into a finished scan with one HIGH finding on its first package. */
function scanned(base: Report, dismissed: boolean): Report {
  const report = structuredClone(base);
  const dep = report.dependencies[0]!;
  dep.vulnerabilities = [
    {
      id: ADVISORY,
      summary: 'Example advisory for the end-to-end run',
      details: null,
      severity: 'HIGH',
      score: 7.5,
      aliases: ['CVE-2099-0001'],
      references: [`https://osv.dev/vulnerability/${ADVISORY}`],
      fixedVersions: ['99.0.0'],
      fixAvailable: true,
      epssScore: null,
      epssPercentile: null,
      dismissed,
    },
  ];
  dep.vulnerabilityCount = dismissed ? 0 : 1;
  dep.highestSeverity = dismissed ? 'NONE' : 'HIGH';
  report.vulnerable = dismissed ? 0 : 1;
  report.severityCounts = report.severityCounts.map((c) => ({ ...c, count: !dismissed && c.severity === 'HIGH' ? 1 : 0 }));
  report.scan = {
    ...report.scan,
    status: 'SCANNED',
    message: `Scanned ${report.total} packages with OSV.dev.`,
    scannedAt: Date.now(),
    packagesScanned: report.total,
    vulnerabilitiesFound: dismissed ? 0 : 1,
  };
  return report;
}

/** Serve `GET api/vulnerabilities` as `make(serverReport)`; returns the server's own report. */
async function stubReport(page: Page, make: (base: Report) => Report): Promise<void> {
  await page.route('**/api/vulnerabilities', async (route) => {
    const response = await route.fetch();
    await route.fulfill({ response, json: make((await response.json()) as Report) });
  });
}

async function serverReport(page: Page): Promise<Report> {
  return (await (await page.request.get('api/vulnerabilities')).json()) as Report;
}

const panel = (page: Page) => page.locator('main .panel');
const scanButton = (page: Page) => page.getByRole('button', { name: /^Scan/ });

test.describe('§10.6 vulnerabilities states', () => {
  test('never scanned (the real server): the inventory and a Scan button, nothing sent', async ({ page }) => {
    const posts: string[] = [];
    page.on('request', (r) => r.method() === 'POST' && posts.push(r.url()));
    await openPanel(page, 'vulnerabilities');
    await expect(panel(page)).toHaveAttribute('data-phase', 'never-scanned');
    await expect(page.locator('main')).toContainText('Not scanned yet');
    await expect(page.locator('main')).toContainText('Nothing leaves this machine until you press Scan.');
    const total = (await serverReport(page)).total;
    await expect(page.locator('main table tbody tr')).toHaveCount(total);
    await expect(scanButton(page)).toHaveText('Scan with OSV.dev');
    await expect(scanButton(page)).toBeEnabled();
    expect(posts).toEqual([]);
  });

  test('scanning, then results', async ({ page }) => {
    const base = await serverReport(page);
    let release!: () => void;
    const held = new Promise<void>((resolve) => (release = resolve));
    await page.route('**/api/vulnerabilities/scan', async (route: Route) => {
      await held;
      await route.fulfill({ json: scanned(base, false) });
    });
    await openPanel(page, 'vulnerabilities');
    await scanButton(page).click();
    await expect(panel(page)).toHaveAttribute('data-phase', 'scanning');
    await expect(scanButton(page)).toHaveText('Scanning…');
    await expect(scanButton(page)).toBeDisabled();
    await expect(page.locator('main')).toContainText(`Scanning ${base.total} packages with OSV.dev`);
    release();
    await expect(panel(page)).toHaveAttribute('data-phase', 'results');
    await expect(page.locator('main')).toContainText(`1 of ${base.total} packages have 1 known vulnerability`);
    await expect(page.locator('main tbody tr', { hasText: ADVISORY })).toContainText('HIGH');
    await expect(scanButton(page)).toHaveText('Scan again');
  });

  test('busy: a 409 shows the server text and keeps the inventory', async ({ page }) => {
    const busy = {
      error: 'sharpit action already in progress',
      operation: 'vulnerabilities.scan',
      activeOperation: 'vulnerabilities.scan',
      message: "Operation 'vulnerabilities.scan' cannot start while 'vulnerabilities.scan' is in progress.",
    };
    await page.route('**/api/vulnerabilities/scan', (route) => route.fulfill({ status: 409, json: busy }));
    await openPanel(page, 'vulnerabilities');
    await scanButton(page).click();
    await expect(page.getByRole('status')).toHaveText(busy.message);
    await expect(panel(page)).toHaveAttribute('data-phase', 'never-scanned');
  });

  test('failed: an OSV error report shows the reason and Scan again', async ({ page }) => {
    const base = await serverReport(page);
    const failed = {
      ...base,
      scan: { ...base.scan, status: 'ERROR', message: 'OSV scan failed: connection refused', scannedAt: Date.now() },
    };
    await page.route('**/api/vulnerabilities/scan', (route) => route.fulfill({ json: failed }));
    await openPanel(page, 'vulnerabilities');
    await scanButton(page).click();
    await expect(panel(page)).toHaveAttribute('data-phase', 'failed');
    await expect(page.getByRole('alert')).toContainText('Scan failed');
    await expect(page.getByRole('alert')).toContainText('OSV scan failed: connection refused');
    await expect(scanButton(page)).toHaveText('Scan again');
  });

  test('results, dismissed, restored', async ({ page }) => {
    let dismissed = false;
    await stubReport(page, (base) => scanned(base, dismissed));
    await page.route('**/api/dismissed-rules/**', async (route) => {
      const rule = decodeURIComponent(new URL(route.request().url()).pathname.split('/dismissed-rules/')[1]!);
      expect(rule).toMatch(new RegExp(`^${ADVISORY}::pypi:`));
      dismissed = route.request().method() === 'POST';
      await route.fulfill({ json: { dismissed: dismissed ? [rule] : [] } });
    });
    await openPanel(page, 'vulnerabilities');
    await expect(panel(page)).toHaveAttribute('data-phase', 'results');
    const row = page.locator('main tbody tr', { hasText: ADVISORY });

    await row.getByRole('button', { name: new RegExp(`^Dismiss ${ADVISORY} in `) }).click();
    await expect(row).toHaveClass(/dismissed/);
    await expect(row.locator('.tag', { hasText: 'dismissed' })).toBeVisible();
    await expect(page.locator('main')).toContainText('No known vulnerabilities');

    await row.getByRole('button', { name: new RegExp(`^Restore ${ADVISORY} in `) }).click();
    await expect(row).not.toHaveClass(/dismissed/);
    await expect(page.locator('main')).toContainText('have 1 known vulnerability');
  });
});
