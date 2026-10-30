import { expect, type Page } from '@playwright/test';

/** The server's token (playwright.config.ts sets SHARPIT_AUTHENTICATION_TOKEN to it). */
export const TOKEN = 'e2e-token';

/** The example app's registry, in rail order. */
export const PANELS = [
  { id: 'overview', title: 'Overview' },
  { id: 'config', title: 'Configuration' },
  { id: 'mappings', title: 'Mappings' },
  { id: 'loggers', title: 'Loggers' },
  { id: 'beans', title: 'Beans' },
  { id: 'vulnerabilities', title: 'Vulnerabilities' },
  { id: 'mcp-server', title: 'MCP Server' },
  { id: 'cli', title: 'CLI' },
] as const;

/** Open a panel by its hash route and wait until its data has rendered. */
export async function openPanel(page: Page, id: string, q = ''): Promise<void> {
  await page.goto(`./#/${id}${q ? `?q=${encodeURIComponent(q)}` : ''}`);
  await settled(page);
}

/** No skeleton rows, no busy region, no loading phase. */
export async function settled(page: Page): Promise<void> {
  await expect(page.locator('main h1').first()).toBeVisible();
  await expect(page.locator('main .skeleton')).toHaveCount(0);
  await expect(page.locator('main [aria-busy="true"]')).toHaveCount(0);
  await expect(page.locator('main [data-phase="loading"]')).toHaveCount(0);
  await expect(page.locator('main', { hasText: 'Loading the dependency graph' })).toHaveCount(0);
}

/** Rows of the main data table (group header rows excluded). */
export const dataRows = (page: Page) => page.locator('main table tbody tr:not(.group):not(.skeleton)');
