// Spec §10 acceptance checks 1-5, 7 and 9 against the real example app (6 and 8 have their own files).
import { expect, test } from '@playwright/test';
import { dataRows, openPanel, PANELS, settled, TOKEN } from './support';

const BULK = 'fastapi_sample.bulk.';

test('§10.1 the rail comes from the registry; unavailable and read-only panels show their reason', async ({ page }) => {
  await openPanel(page, 'overview');
  const rail = page.getByRole('navigation', { name: 'Panels' });
  const links = rail.getByRole('link');
  await expect(links).toHaveText(PANELS.map((p) => p.title));
  for (const p of PANELS) await expect(rail.getByRole('link', { name: p.title })).toHaveAttribute('href', `#/${p.id}`);

  // The example app has no unavailable or read-only panel, so the registry answer is the server's own with two flags flipped.
  const unavailable = 'MCP is off. Set SHARPIT_MCP_ENABLED=ON to enable it.';
  const readOnly = 'Read-only: SHARPIT_PANELS_LOGGERS_READ_ONLY=true';
  await page.route('**/api/panels', async (route) => {
    const response = await route.fetch();
    const body = (await response.json()) as { panels: Record<string, unknown>[] };
    for (const p of body.panels) {
      if (p.id === 'mcp-server') Object.assign(p, { available: false, unavailableReason: unavailable });
      if (p.id === 'loggers') Object.assign(p, { readOnly: true, readOnlyReason: readOnly });
    }
    await route.fulfill({ response, json: body });
  });
  await page.reload();
  await expect(rail.getByRole('link', { name: 'MCP Server' })).toHaveAccessibleDescription(unavailable);
  await expect(rail.getByRole('link', { name: 'Loggers' })).toHaveAccessibleDescription(readOnly);
  await expect(rail.getByRole('link', { name: 'Overview' })).toHaveAccessibleDescription('');

  await rail.getByRole('link', { name: 'MCP Server' }).click();
  await expect(page.locator('main')).toContainText('MCP Server is unavailable');
  await expect(page.locator('main')).toContainText(unavailable);
  await rail.getByRole('link', { name: 'Loggers' }).click();
  await settled(page);
  await expect(page.locator('main .notice')).toHaveText(readOnly);
  await expect(dataRows(page).first().locator('select')).toBeDisabled();
});

test('§10.2 Ctrl+K jumps to a panel, a logger and a config key; everything is reachable by keyboard', async ({ page }) => {
  await openPanel(page, 'overview');
  const palette = page.getByRole('dialog', { name: 'Go to' });
  const input = page.getByRole('combobox', { name: 'Go to a panel, logger or config key' });

  await page.keyboard.press('Control+K');
  await expect(palette).toBeVisible();
  await expect(input).toBeFocused();
  await page.keyboard.type('mappings');
  await page.keyboard.press('Enter');
  await expect(page).toHaveURL(/#\/mappings$/);
  await expect(palette).toBeHidden();

  await page.keyboard.press('Control+K');
  await page.keyboard.type(`${BULK}0007`);
  await expect(page.getByRole('dialog', { name: 'Go to' }).getByRole('option').first()).toHaveText(`${BULK}0007`);
  await page.keyboard.press('Enter');
  await expect(page).toHaveURL(new RegExp(`#/loggers\\?q=${BULK.replace(/\./g, '\\.')}0007$`));
  await settled(page);
  await expect(dataRows(page)).toHaveCount(1);

  await page.keyboard.press('Control+K');
  await page.keyboard.type('database_url');
  await expect(page.getByRole('dialog', { name: 'Go to' }).getByRole('option').first()).toBeVisible();
  await page.keyboard.press('Enter');
  await expect(page).toHaveURL(/#\/config\?q=/);
  await settled(page);
  await expect(dataRows(page).first()).toContainText(/database_url/i);

  // `/` focuses the panel filter
  await page.locator('main h1').click();
  await page.keyboard.press('/');
  await expect(page.locator('.panel-filter')).toBeFocused();

  // Tab from the top of a freshly loaded page reaches the skip link, every rail link, both rail tools and the panel's controls
  await openPanel(page, 'loggers');
  await page.reload(); // a hash change keeps focus where it was; a fresh document starts at the top
  await settled(page);
  const reached = new Set<string>();
  for (let i = 0; i < 20; i++) {
    await page.keyboard.press('Tab');
    reached.add(
      await page.evaluate(() => {
        const el = document.activeElement as HTMLElement | null;
        return el ? `${el.tagName.toLowerCase()}:${el.getAttribute('aria-label') ?? el.textContent?.trim() ?? ''}` : '';
      }),
    );
  }
  const seen = [...reached].join('\n');
  expect(seen).toContain('a:Skip to panel');
  for (const p of PANELS) expect(seen).toContain(`a:${p.title}`);
  expect(seen).toMatch(/button:Go to…/);
  expect(seen).toMatch(/button:Theme: system\. Switch theme/);
  expect(seen).toMatch(/input:/);
  expect(seen).toMatch(/select:/);
});

test('§10.3 tables filter as you type and page from the server, 200 rows a page', async ({ page }) => {
  const first = page.waitForRequest((r) => r.url().includes('/api/loggers?') && new URL(r.url()).searchParams.get('limit') !== '1');
  await openPanel(page, 'loggers');
  expect(new URL((await first).url()).searchParams.get('limit')).toBe('200');
  await expect(dataRows(page)).toHaveCount(200);
  const count = page.locator('main .count');
  const total = Number((await count.textContent())!.split(' of ')[1]);
  expect(total).toBeGreaterThan(1000);

  const more = page.getByRole('button', { name: 'Load 200 more' });
  const next = page.waitForRequest((r) => r.url().includes('offset=200'));
  await more.click();
  await next;
  await expect(dataRows(page)).toHaveCount(400);

  const filtered = page.waitForRequest((r) => r.url().includes(`q=${encodeURIComponent(`${BULK}00`)}`));
  await page.locator('.panel-filter').pressSequentially(`${BULK}00`);
  await filtered;
  await expect(count).toHaveText(`100 of ${total}`);
  await expect(dataRows(page)).toHaveCount(100);
  await expect(page.getByRole('button', { name: /^Load/ })).toHaveCount(0);

  await page.locator('.panel-filter').fill('no-such-logger-anywhere');
  await expect(page.locator('main')).toContainText('No loggers match');
  await page.getByRole('button', { name: 'Clear the filter' }).click();
  await expect(dataRows(page)).toHaveCount(200);
});

test('test_large_table_filter_responsive: with 1,000 loggers a keystroke updates the rows within 1 s', async ({ page }, info) => {
  await openPanel(page, 'loggers');
  const filter = page.locator('.panel-filter');
  const runs: number[] = [];
  for (const digit of ['1', '2', '3', '4', '5']) {
    await filter.fill(`${BULK}00`);
    await expect(dataRows(page)).toHaveCount(100);
    const t0 = await page.evaluate(() => performance.now());
    await filter.press(digit); // `fastapi_sample.bulk.00N` matches ten loggers
    const done = await page.waitForFunction(
      () => document.querySelectorAll('main table tbody tr').length === 10 && performance.now(),
      undefined,
      { polling: 'raf' },
    );
    runs.push((await done.jsonValue()) as number - t0);
  }
  const median = [...runs].sort((a, b) => a - b)[2]!;
  const summary = `runs ${runs.map((r) => r.toFixed(0)).join(', ')} ms; median ${median.toFixed(0)} ms`;
  info.annotations.push({ type: 'filter-latency', description: summary });
  console.log(`test_large_table_filter_responsive: ${summary}`);
  expect(median).toBeLessThan(1000);
});

test('§10.4 config is grouped by source with the winning source marked and masked values badged', async ({ page }) => {
  await openPanel(page, 'config');
  const groups = page.locator('main tbody tr.group');
  expect(await groups.count()).toBeGreaterThan(1);
  await expect(groups.first()).toContainText('highest precedence');
  await expect(page.locator('main .tag.ok', { hasText: 'won' }).first()).toBeVisible();

  await page.locator('.panel-filter').fill('api_token');
  const row = dataRows(page).filter({ hasText: /api_token/i }).first();
  await expect(row.locator('.tag', { hasText: 'masked' })).toBeVisible();
  await expect(page.locator('main')).not.toContainText('dev-api-token');
});

test('§10.5 the dependency graph is interactive and focuses a bean with its neighbours', async ({ page }) => {
  await openPanel(page, 'beans');
  await page.getByRole('button', { name: 'Graph', exact: true }).click();
  await settled(page);
  const graph = page.getByRole('group', { name: 'Bean dependency graph' });
  await expect(graph).toBeVisible();
  const nodes = graph.locator('g[role="button"]');
  expect(await nodes.count()).toBeGreaterThan(1);

  const bean = graph.locator('g[role="button"][aria-label$=":get_database"]');
  await bean.click();
  await expect(graph.locator('g[aria-pressed="true"]')).toHaveAttribute('aria-label', /:get_database, focused$/);
  await expect(page.locator('main .notice')).toContainText('its dependencies on the right, its dependents on the left');
  await expect(graph.locator('g.node.out')).not.toHaveCount(0); // get_settings
  await expect(graph.locator('g.node.in')).not.toHaveCount(0); // get_owner_repository

  await page.keyboard.press('Escape');
  await expect(graph.locator('g[aria-pressed="true"]')).toHaveCount(0);

  // the keyboard path: Tab to a node, Enter to focus it
  await nodes.first().focus();
  await page.keyboard.press('Enter');
  await expect(graph.locator('g[aria-pressed="true"]')).toHaveCount(1);
});

test('§10.7 an untrusted source gets the token prompt, which calls auth/session', async ({ browser }) => {
  // A forwarded header without SHARPIT_TRUSTED_PROXIES makes even a loopback peer untrusted (guard.is_trusted_source).
  const context = await browser.newContext({ extraHTTPHeaders: { 'X-Forwarded-For': '203.0.113.5' } });
  const page = await context.newPage();
  const panels = page.waitForResponse((r) => r.url().endsWith('/api/panels'));
  await page.goto('./#/overview');
  expect((await panels).status()).toBe(401);
  await expect(page.getByRole('heading', { name: 'Token required' })).toBeVisible();
  await expect(page.getByLabel('Token', { exact: true })).toBeFocused();

  await page.getByLabel('Token', { exact: true }).fill('wrong-token');
  const rejected = page.waitForResponse((r) => r.url().endsWith('/api/auth/session'));
  await page.getByRole('button', { name: 'Unlock' }).click();
  expect((await rejected).status()).toBe(401);
  await expect(page.getByRole('alert')).toContainText('That token was not accepted');

  await page.getByLabel('Token', { exact: true }).fill(TOKEN);
  const accepted = page.waitForResponse((r) => r.url().endsWith('/api/auth/session'));
  await page.getByRole('button', { name: 'Unlock' }).click();
  const session = await accepted;
  expect(session.status()).toBe(204);
  expect(session.request().headers()['authorization']).toBe(`Bearer ${TOKEN}`);

  // the session cookie now authorises the panel's own calls
  await settled(page);
  await expect(page.getByRole('heading', { name: 'Overview' })).toBeVisible();
  await expect(page.getByRole('navigation', { name: 'Panels' }).getByRole('link')).toHaveCount(PANELS.length);
  await context.close();
});

test('§10.9 the production build runs under sharpit CSP with no violation on any panel', async ({ page }) => {
  await page.addInitScript(() => {
    const w = window as unknown as { __csp: string[] };
    w.__csp = [];
    document.addEventListener('securitypolicyviolation', (e) => w.__csp.push(`${e.violatedDirective} ${e.blockedURI}`));
  });
  const errors: string[] = [];
  page.on('console', (m) => {
    if (m.type() === 'error' || /Content Security Policy/i.test(m.text())) errors.push(m.text());
  });
  page.on('pageerror', (e) => errors.push(e.message));

  const shell = await page.goto('./');
  const csp = shell!.headers()['content-security-policy'] ?? '';
  expect(csp).toContain("script-src 'self'");
  expect(csp).not.toContain('unsafe-eval');
  expect(csp.match(/script-src[^;]*/)![0]).not.toContain('unsafe-inline');
  // the built shell: module scripts from ./assets only, nothing inline
  const html = await shell!.text();
  expect(html).not.toMatch(/<script(?![^>]*\bsrc=)[^>]*>/);
  expect(html).toMatch(/<script type="module" crossorigin src="\.\/assets\/index-[\w-]+\.js"><\/script>/);

  for (const p of PANELS) await openPanel(page, p.id);
  await openPanel(page, 'beans');
  await page.getByRole('button', { name: 'Graph', exact: true }).click();
  await settled(page);
  await page.keyboard.press('Control+K');
  await page.keyboard.type('log');
  await expect(page.getByRole('dialog', { name: 'Go to' }).getByRole('option').first()).toBeVisible();
  await page.keyboard.press('Escape');

  expect(await page.evaluate(() => (window as unknown as { __csp: string[] }).__csp)).toEqual([]);
  expect(errors).toEqual([]);
});
