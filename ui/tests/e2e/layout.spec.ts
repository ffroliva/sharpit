import { expect, test, type Page } from '@playwright/test';
import { openPanel, settled } from './support';

async function theme(page: Page, scheme: 'light' | 'dark'): Promise<void> {
  await page.emulateMedia({ colorScheme: scheme });
  await page.goto('./');
  await page.evaluate((value) => document.documentElement.setAttribute('data-theme', value), scheme);
}

for (const scheme of ['light', 'dark'] as const) {
  test.describe(`${scheme} layout`, () => {
    test.beforeEach(async ({ page }) => theme(page, scheme));

    for (const width of [390, 720]) {
      test(`rail links do not overlap at ${width}px`, async ({ page }) => {
        await page.setViewportSize({ width, height: 800 });
        const links = page.locator('nav.rail a[href^="#/"]');
        await expect(links.first()).toBeVisible();
        const boxes = await links.evaluateAll((items) => items.map((item) => {
          const { left, right } = item.getBoundingClientRect();
          return { left, right };
        }));
        for (let i = 1; i < boxes.length; i++) expect(boxes[i].left).toBeGreaterThanOrEqual(boxes[i - 1].right);
      });
    }

    for (const size of [{ width: 390, height: 800 }, { width: 720, height: 800 }, { width: 1280, height: 500 }]) {
      test(`current panel is in view at ${size.width}x${size.height}`, async ({ page }) => {
        await page.setViewportSize(size);
        await openPanel(page, 'vulnerabilities');
        const item = page.locator('nav.rail a[aria-current="page"]');
        const rail = page.locator('nav.rail');
        const [itemBox, railBox] = await Promise.all([item.boundingBox(), rail.boundingBox()]);
        expect(itemBox).not.toBeNull();
        expect(railBox).not.toBeNull();
        expect(itemBox!.right).toBeGreaterThan(railBox!.left);
        expect(itemBox!.left).toBeLessThan(railBox!.right);
        expect(itemBox!.bottom).toBeGreaterThan(railBox!.top);
        expect(itemBox!.top).toBeLessThan(railBox!.bottom);
      });
    }

    test('fluid columns have width at 390px', async ({ page }) => {
      await page.setViewportSize({ width: 390, height: 800 });
      for (const id of ['loggers', 'beans', 'http-exchanges']) {
        await openPanel(page, id);
        const widths = await page.locator('main table thead th').evaluateAll((items) => items.map((item) => item.getBoundingClientRect().width));
        expect(widths.length).toBeGreaterThan(0);
        expect(widths.every((width) => width > 48), `${id}: ${widths.join(', ')}`).toBeTruthy();
      }
    });

    for (const id of ['log-tail', 'security-logs']) {
      test(`${id} panel header is one line`, async ({ page }) => {
        await page.setViewportSize({ width: 1280, height: 800 });
        await openPanel(page, id);
        await expect(page.locator('.panel-head')).toHaveCSS('height', /./);
        expect(await page.locator('.panel-head').evaluate((el) => el.getBoundingClientRect().height)).toBeLessThanOrEqual(36);
      });
    }

    for (const id of ['sqlalchemy-statistics', 'fastapi-security']) {
      test(`${id} headings are styled`, async ({ page }) => {
        await page.setViewportSize({ width: 1280, height: 800 });
        await openPanel(page, id);
        const heading = page.locator('main h2').first();
        await expect(heading).toBeVisible();
        await expect(heading).toHaveCSS('font-size', '13px');
        await expect(heading).toHaveCSS('font-weight', '600');
        expect(await heading.evaluate((el) => el.getBoundingClientRect().left)).toBe(16);
      });
    }

    for (const id of ['health', 'exceptions', 'sql-trace', 'transactions', 'security-logs', 'alembic']) {
      test(`${id} header actions sit right`, async ({ page }) => {
        await page.setViewportSize({ width: 1280, height: 800 });
        await openPanel(page, id);
        const header = page.locator('.panel-head');
        const control = header.locator('button, input, select').last();
        await expect(control).toBeVisible();
        const [headerBox, controlBox, padding] = await Promise.all([
          header.boundingBox(),
          control.boundingBox(),
          header.evaluate((el) => parseFloat(getComputedStyle(el).paddingRight)),
        ]);
        expect(controlBox).not.toBeNull();
        expect(headerBox).not.toBeNull();
        expect(headerBox!.right - padding - (controlBox!.x + controlBox!.width)).toBeLessThanOrEqual(1);
      });
    }

    test('details and link buttons meet the 24px target at 390px', async ({ page }) => {
      await page.setViewportSize({ width: 390, height: 800 });
      await openPanel(page, 'http-exchanges');
      const buttons = page.locator('main button.link');
      await expect(buttons.first()).toBeVisible();
      const heights = await buttons.evaluateAll((items) => items.map((item) => item.getBoundingClientRect().height));
      expect(heights.every((height) => height >= 24), heights.join(', ')).toBeTruthy();
    });
  });
}
