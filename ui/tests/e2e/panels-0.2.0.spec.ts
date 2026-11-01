// Spec §14.3 Playwright checks for the 0.2.0 panels, against the SQLAlchemy dogfood sample (playwright.sqla.config.ts):
// the production build under sharpit's CSP, real requests made by the test, axe in light and dark.
import AxeBuilder from '@axe-core/playwright';
import { expect, test, type Page } from '@playwright/test';
import { openPanel, settled } from './support';

const NEW_PANELS = [
  'activity', 'health', 'threads', 'log-tail', 'exceptions', 'http-exchanges', 'http-probe',
  'sql-trace', 'database-connection-pools', 'alembic', 'rest-api',
];
const main = (page: Page) => page.locator('main');
/** A request to the sample app itself (outside the /sharpit/ base URL). */
const hit = async (page: Page, path: string) => (await page.request.get(path)).status();

test('each new panel loads', async ({ page }) => {
  for (const id of NEW_PANELS) {
    await openPanel(page, id);
    await expect(main(page)).not.toContainText('is unavailable');
    await expect(main(page).locator('[role="alert"]')).toHaveCount(0);
  }
});

test('HTTP Exchanges shows a request made by the test', async ({ page }) => {
  expect(await hit(page, '/owners?from=e2e')).toBe(200);
  await openPanel(page, 'http-exchanges');
  await expect(main(page).locator('tbody tr', { hasText: '/owners?from=e2e' }).first()).toBeVisible();
});

test('an exception route appears in Exceptions and opens its detail', async ({ page }) => {
  expect(await hit(page, '/boom')).toBe(500);
  await openPanel(page, 'exceptions');
  await main(page).getByRole('button', { name: 'RuntimeError', exact: true }).click();
  const detail = page.getByRole('region', { name: 'Detail for RuntimeError' });
  await expect(detail).toBeVisible();
  await expect(detail).toContainText('create_app.<locals>.boom'); // the app's own frame
  await expect(main(page)).toContainText('unhandled error from /boom');
});

test('SQL Trace flags the N+1 route; Live Activity opens its profile with the N+1 group', async ({ page }) => {
  expect(await hit(page, '/owners/n-plus-one')).toBe(200);
  await openPanel(page, 'sql-trace');
  await page.getByRole('tab', { name: /^Top statements/ }).click();
  await expect(main(page).locator('tbody tr', { hasText: 'pets' }).locator('.tag', { hasText: 'N+1' })).toBeVisible();

  await openPanel(page, 'activity');
  await main(page).getByRole('button', { name: 'GET /owners/n-plus-one' }).first().click();
  const profile = page.getByRole('region', { name: 'Request profile' });
  await expect(profile).toContainText('potential N+1');
  await expect(profile).toContainText('pets');
});

test('Log Tail receives a live line within 2 s', async ({ page }) => {
  await openPanel(page, 'log-tail');
  await expect(main(page).getByText('Connecting…')).toHaveCount(0);
  expect(await hit(page, '/warn')).toBe(200);
  await expect(page.getByRole('list', { name: 'Log lines' })).toContainText('sample warning log message from /warn', { timeout: 2000 });
});

test('Alembic shows one pending revision after "Read database version"', async ({ page }) => {
  await openPanel(page, 'alembic');
  await page.getByRole('button', { name: 'Read database version' }).click();
  // the sample registers a sync and an async engine on one SQLite file: each database shows the same single pending row
  const databases = main(page).locator('section.block');
  await expect(databases.first()).toContainText('1 pending');
  const count = await databases.count();
  for (let i = 0; i < count; i++) {
    await expect(databases.nth(i)).toContainText('current 0002');
    await expect(databases.nth(i).locator('tr.pending')).toHaveCount(1);
    await expect(databases.nth(i).locator('tr.pending')).toContainText('0003');
  }
});

test('Health runs the checks', async ({ page }) => {
  await openPanel(page, 'health');
  const ran = page.waitForResponse((r) => r.url().endsWith('/api/health/check') && r.request().method() === 'POST');
  await page.getByRole('button', { name: 'Run checks' }).click();
  expect((await ran).status()).toBe(200);
  await settled(page);
  await expect(main(page).locator('li', { has: page.locator('span.mono', { hasText: /^user$/ }) }).first()).toContainText('UP');
});

test('Threads shows the event-loop task tab', async ({ page }) => {
  expect(await hit(page, '/sleeper')).toBe(200);
  await openPanel(page, 'threads');
  await page.getByRole('tab', { name: /^Tasks/ }).click();
  await expect(main(page)).toContainText('sleeper');
});

test('REST API scan shows findings; dismiss and restore change the score', async ({ page }) => {
  await openPanel(page, 'rest-api');
  await page.getByRole('button', { name: /^(Run REST API checks|Scan again)$/ }).click();
  await expect(main(page)).toContainText('RAPI-NAME-001');
  await expect(main(page)).toContainText('RAPI-RESP-001');
  const score = main(page).locator('[data-score]');
  const before = Number(await score.getAttribute('data-score'));

  // RAPI-NAME-001 is INFO (no penalty), so the score moves on RAPI-RESP-001 (LOW, 1 point)
  await page.getByRole('button', { name: 'Dismiss RAPI-RESP-001' }).click();
  await expect.poll(async () => Number(await score.getAttribute('data-score'))).toBeGreaterThan(before);
  await page.getByRole('checkbox', { name: /Show dismissed/ }).check();
  await page.getByRole('button', { name: 'Restore RAPI-RESP-001' }).click();
  await expect.poll(async () => Number(await score.getAttribute('data-score'))).toBe(before);
});

// 0.3.0: one finding, not the whole rule, is dismissed by its fingerprint, survives a reopened drawer, and is restored
test('REST API: dismiss one finding by fingerprint, reopen the drawer, restore it', async ({ page }) => {
  await openPanel(page, 'rest-api');
  await page.getByRole('button', { name: /^(Run REST API checks|Scan again)$/ }).click();
  await expect(main(page)).toContainText('RAPI-RESP-001');
  await page.getByRole('button', { name: 'View violations for RAPI-RESP-001' }).click();

  const dismiss = page.getByRole('button', { name: /^Dismiss finding rest-api:RAPI-RESP-001:[0-9a-f]{16}$/ }).first();
  const label = await dismiss.getAttribute('aria-label');
  const fingerprint = label!.replace('Dismiss finding ', '');
  await dismiss.click();
  const restore = page.getByRole('button', { name: `Restore finding ${fingerprint}` });
  await expect(restore).toBeVisible();

  // the dismissal is stored server-side: closing and reopening the drawer still offers the restore
  await page.getByRole('button', { name: 'View violations for RAPI-RESP-001' }).click();
  await page.getByRole('button', { name: 'View violations for RAPI-RESP-001' }).click();
  await expect(restore).toBeVisible();

  await restore.click();
  await expect(page.getByRole('button', { name: `Dismiss finding ${fingerprint}` })).toBeVisible();
});

test('HTTP Probe returns 200 for /owners and refuses /sharpit/api/panels', async ({ page }) => {
  await openPanel(page, 'http-probe');
  const path = page.getByRole('combobox', { name: 'Path' }); // a text input with route suggestions (datalist)
  await path.fill('/owners');
  await page.getByRole('button', { name: 'Send' }).click();
  await expect(page.getByRole('region', { name: 'Response' }).locator('h2 .mono')).toHaveText(/^200 /);

  await path.fill('/sharpit/api/panels');
  await page.getByRole('button', { name: 'Send' }).click();
  await expect(main(page).locator('.notice.danger[role="alert"]')).toHaveText('HTTP Probe cannot target sharpit itself');
});

for (const scheme of ['light', 'dark'] as const) {
  test(`axe finds no serious or critical violation on the new panels in the ${scheme} theme`, async ({ page }) => {
    await page.emulateMedia({ colorScheme: scheme, reducedMotion: 'reduce' });
    // data on every panel first, so axe sees the populated views, not only their empty states
    for (const path of ['/owners/n-plus-one', '/boom', '/warn', '/sleeper']) await hit(page, path);
    expect((await page.request.post('api/rest-api/scan')).ok()).toBe(true);
    expect((await page.request.post('api/alembic/refresh')).ok()).toBe(true);
    const found: string[] = [];
    for (const id of NEW_PANELS) {
      await openPanel(page, id);
      const { violations } = await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa']).analyze();
      for (const v of violations.filter((x) => x.impact === 'serious' || x.impact === 'critical')) {
        found.push(`${id}: ${v.id} (${v.impact}) x${v.nodes.length}: ${v.nodes.slice(0, 3).map((n) => n.target.join(' ')).join(' | ')}`);
      }
    }
    expect(found).toEqual([]);
  });
}
