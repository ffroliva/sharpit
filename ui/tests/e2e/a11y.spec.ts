// Spec §10 check 8: light and dark themes pass axe (no serious or critical violation, WCAG 2.x A/AA) on every panel,
// and reduced motion is honoured. With SHOTS=1 each view is also saved to screenshots/ in both themes.
import AxeBuilder from '@axe-core/playwright';
import { expect, test, type Page } from '@playwright/test';
import path from 'node:path';
import { openPanel, PANELS, settled } from './support';

// The committed images change only on purpose: `SHOTS=1 npm run e2e`.
const SHOTS = process.env.SHOTS === '1' ? path.join(import.meta.dirname, 'screenshots') : null;

/** The app's own settings rather than this machine's environment variables, which are not for a committed image. */
async function appSettingsOnly(page: Page): Promise<void> {
  const select = page.locator('#config-source');
  const values = await select.locator('option').evaluateAll((os) => os.map((o) => (o as HTMLOptionElement).value));
  await select.selectOption(values.find((v) => v && v !== 'systemEnvironment')!);
  await settled(page);
}

/** Every panel, plus the beans graph, which is its own view. Axe runs on the whole view, before `shot` narrows it. */
const VIEWS: { name: string; open: (page: Page) => Promise<void>; shot?: (page: Page) => Promise<void> }[] = [
  ...PANELS.map((p) => ({
    name: p.id,
    open: (page: Page) => openPanel(page, p.id),
    shot: p.id === 'config' ? appSettingsOnly : undefined,
  })),
  {
    name: 'beans-graph',
    open: async (page: Page) => {
      await openPanel(page, 'beans');
      await page.getByRole('button', { name: 'Graph', exact: true }).click();
      await settled(page);
    },
  },
];

for (const scheme of ['light', 'dark'] as const) {
  test(`§10.8 axe finds no serious or critical violation in the ${scheme} theme`, async ({ page }) => {
    await page.emulateMedia({ colorScheme: scheme, reducedMotion: 'reduce' });
    const found: string[] = [];
    for (const view of VIEWS) {
      await view.open(page);
      const { violations } = await new AxeBuilder({ page })
        .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'])
        .analyze();
      const others = violations.filter((x) => x.impact !== 'serious' && x.impact !== 'critical');
      console.log(`axe ${scheme} ${view.name}: ${violations.length} rule(s) violated${others.length ? `; below serious: ${others.map((x) => `${x.id} (${x.impact})`).join(', ')}` : ''}`);
      for (const v of violations.filter((x) => x.impact === 'serious' || x.impact === 'critical')) {
        found.push(`${view.name}: ${v.id} (${v.impact}) x${v.nodes.length}: ${v.nodes.slice(0, 3).map((n) => n.target.join(' ')).join(' | ')}`);
      }
      if (SHOTS) {
        await view.shot?.(page);
        await page.screenshot({ path: path.join(SHOTS, `${view.name}-${scheme}.png`) });
      }
    }
    expect(found).toEqual([]);
  });
}

test('§10.8 the theme toggle pins light and dark; reduced motion zeroes every transition', async ({ page }) => {
  await page.emulateMedia({ colorScheme: 'light' });
  await openPanel(page, 'overview');
  const background = () => page.evaluate(() => getComputedStyle(document.body).backgroundColor);
  const light = await background();
  const toggle = page.getByRole('button', { name: /^Theme: / });
  await toggle.click(); // system -> light
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'light');
  await toggle.click(); // light -> dark
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark');
  expect(await background()).not.toBe(light);
  await page.reload();
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark'); // the choice is remembered

  // --dur in milliseconds, whatever unit the minifier wrote it in
  const duration = () =>
    page.evaluate(() => {
      const raw = getComputedStyle(document.documentElement).getPropertyValue('--dur').trim();
      return parseFloat(raw) * (raw.endsWith('ms') ? 1 : 1000);
    });
  await page.emulateMedia({ reducedMotion: 'no-preference' });
  expect(await duration()).toBe(150);
  await page.emulateMedia({ reducedMotion: 'reduce' });
  expect(await duration()).toBe(0);
});
