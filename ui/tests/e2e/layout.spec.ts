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
        expect(itemBox!.x + itemBox!.width).toBeGreaterThan(railBox!.x);
        expect(itemBox!.x).toBeLessThan(railBox!.x + railBox!.width);
        expect(itemBox!.y + itemBox!.height).toBeGreaterThan(railBox!.y);
        expect(itemBox!.y).toBeLessThan(railBox!.y + railBox!.height);
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
        expect(await page.locator('.panel-head').evaluate((el) => el.getBoundingClientRect().height)).toBeLessThanOrEqual(36);
      });
    }

    test('Log Tail controls fit at 390px and filters grow on desktop', async ({ page }) => {
      await page.setViewportSize({ width: 390, height: 800 });
      await openPanel(page, 'log-tail');
      for (const control of await page.locator('.panel-head select, .panel-head input, .panel-head button').all()) {
        const box = await control.boundingBox();
        expect(box).not.toBeNull();
        expect(box!.x).toBeGreaterThanOrEqual(0);
        expect(box!.x + box!.width).toBeLessThanOrEqual(390);
      }
      await page.setViewportSize({ width: 1280, height: 800 });
      const filterWidth = await page.locator('.panel-head .grow').first().evaluate((el) => el.getBoundingClientRect().width);
      expect(filterWidth).toBeGreaterThan(160);
    });

    for (const id of ['sqlalchemy-statistics', 'fastapi-security']) {
      test(`${id} headings are styled`, async ({ page }) => {
        await page.setViewportSize({ width: 1280, height: 800 });
        await openPanel(page, id);
        const heading = page.locator('main h2').first();
        await expect(heading).toBeVisible();
        await expect(heading).toHaveCSS('font-size', '13px');
        await expect(heading).toHaveCSS('font-weight', '600');
        expect(await heading.evaluate((el) => el.getBoundingClientRect().left - el.closest('.panel-body')!.getBoundingClientRect().left)).toBe(16);
      });
    }

    test('SQLAlchemy slowest statement output and warnings share the 16px inset', async ({ page }) => {
      await page.setViewportSize({ width: 1280, height: 800 });
      await openPanel(page, 'sqlalchemy-statistics');
      const body = page.locator('main .panel-body');
      for (const selector of ['h2', 'p.sm', 'pre', 'p.warn']) {
        const element = body.locator(selector).first();
        await expect(element).toBeVisible();
        expect(await element.evaluate((el) => el.getBoundingClientRect().left - el.closest('.panel-body')!.getBoundingClientRect().left)).toBe(16);
      }
    });

    test('panel content starts level with its heading', async ({ page }) => {
      await page.setViewportSize({ width: 1280, height: 800 });
      for (const [id, selector] of [['fastapi-security', '.chain'], ['sqlalchemy-statistics', 'dl.facts dt']] as const) {
        await openPanel(page, id);
        const heading = page.locator('main h2').first();
        const content = page.locator(`main ${selector}`).first();
        await expect(content).toBeVisible();
        const headingLeft = (await heading.boundingBox())!.x;
        const contentLeft = (await content.boundingBox())!.x;
        expect(contentLeft).toBe(headingLeft);
      }
    });

    for (const id of ['alembic', 'mysql', 'postgresql', 'database-connection-pools']) {
      test(`${id} monospace headings retain panel-title size`, async ({ page }) => {
        await page.setViewportSize({ width: 1280, height: 800 });
        await openPanel(page, id);
        if (id === 'alembic') await page.getByRole('button', { name: 'Read database version' }).click();
        let heading = page.locator('main h2.mono').first();
        if (!(await heading.count())) {
          await page.locator('main .panel-body').evaluate((body) => {
            const heading = document.createElement('h2');
            heading.className = 'mono';
            heading.textContent = 'panel value';
            body.append(heading);
          });
          heading = page.locator('main h2.mono').last();
        }
        await expect(heading).toBeVisible();
        await expect(heading).toHaveCSS('font-size', '13px');
      });
    }

    test('SQLAlchemy statistics numbers are right aligned and tabular', async ({ page }) => {
      await page.setViewportSize({ width: 1280, height: 800 });
      await page.request.get(new URL('/owners/n-plus-one', page.url()).href);
      await openPanel(page, 'sqlalchemy-statistics');
      const value = page.locator('dl.facts dd.num').first();
      await expect(value).toHaveCSS('text-align', 'right');
      await expect(value).toHaveCSS('font-variant-numeric', 'tabular-nums');
      await expect(page.locator('td.num').first()).toHaveCSS('text-align', 'right');
      const [label, number] = await Promise.all([
        page.locator('dl.facts.statistics dt').first().boundingBox(),
        page.locator('dl.facts.statistics dd.num').first().boundingBox(),
      ]);
      expect(label).not.toBeNull();
      expect(number).not.toBeNull();
      expect(number!.x - (label!.x + label!.width)).toBeLessThanOrEqual(24);
      await expect(page.locator('dl.facts dd.status').first()).toHaveCSS('text-align', 'left');
    });

    test('probe response heading does not add padding to the result inset', async ({ page }) => {
      await page.setViewportSize({ width: 1280, height: 800 });
      await openPanel(page, 'http-probe');
      await page.getByRole('combobox', { name: 'Path' }).fill('/owners');
      await page.getByRole('button', { name: 'Send' }).click();
      const heading = page.getByRole('region', { name: 'Response' }).locator('h2');
      await expect(heading).toHaveCSS('margin-top', '0px');
      await expect(heading).toHaveCSS('margin-left', '0px');
    });

    test('SQLAlchemy section paragraphs are inset', async ({ page }) => {
      await page.setViewportSize({ width: 1280, height: 800 });
      await openPanel(page, 'sqlalchemy-statistics');
      await expect(page.locator('section.block > p').first()).toHaveCSS('padding-left', '16px');
    });

    test('headingless server status facts have space above and below', async ({ page }) => {
      await page.setViewportSize({ width: 1280, height: 800 });
      await openPanel(page, 'mcp-server');
      const block = page.locator('.panel-body section.block');
      await expect(block.locator('dl.facts')).toHaveCSS('padding-top', '16px');
      await expect(block.locator('dl.facts')).toHaveCSS('padding-bottom', '16px');
    });

    test('the vulnerability summary uses its own 12px inset without section padding', async ({ page }) => {
      await page.setViewportSize({ width: 1280, height: 800 });
      await openPanel(page, 'vulnerabilities');
      await page.locator('main .panel-body').evaluate((body) => {
        const section = document.createElement('section');
        section.className = 'block summary';
        body.append(section);
      });
      await expect(page.locator('section.block.summary')).toHaveCSS('padding-top', '0px');
    });

    for (const id of ['health', 'exceptions', 'traces', 'sql-trace', 'transactions', 'security-logs', 'alembic', 'mysql', 'postgresql']) {
      test(`${id} header actions sit right`, async ({ page }) => {
        await page.setViewportSize({ width: 1280, height: 800 });
        await openPanel(page, id);
        const header = page.locator('.panel-head');
        if (id === 'mysql' || id === 'postgresql') await expect(header.locator('.count')).toHaveCount(0);
        const control = header.locator('button, input, select').last();
        await expect(control).toBeVisible();
        const count = header.locator('.count');
        const rightmost = await count.count() ? count : control;
        const [headerBox, controlBox, rightmostBox, padding] = await Promise.all([
          header.boundingBox(),
          control.boundingBox(),
          rightmost.boundingBox(),
          header.evaluate((el) => parseFloat(getComputedStyle(el).paddingRight)),
        ]);
        expect(controlBox).not.toBeNull();
        expect(headerBox).not.toBeNull();
        expect(rightmostBox).not.toBeNull();
        expect(headerBox!.x + headerBox!.width - padding - (rightmostBox!.x + rightmostBox!.width)).toBeLessThanOrEqual(1);
        if (await count.count()) expect(controlBox!.x + controlBox!.width).toBeLessThanOrEqual(rightmostBox!.x);
      });
    }

    test('details and link buttons meet the 24px target at 390px', async ({ page }) => {
      await page.setViewportSize({ width: 390, height: 800 });
      await page.request.get(new URL('/owners', page.url()).href);
      await openPanel(page, 'http-exchanges');
      const buttons = page.locator('main button.link');
      await expect(buttons.first()).toBeVisible();
      const heights = await buttons.evaluateAll((items) => items.map((item) => item.getBoundingClientRect().height));
      expect(heights.every((height) => height >= 24), heights.join(', ')).toBeTruthy();
    });
  });
}
