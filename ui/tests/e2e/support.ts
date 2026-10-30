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

/** No skeleton rows, no busy region, no loading phase (a disabled panel shows its unavailable page instead). */
export async function settled(page: Page): Promise<void> {
  await expect(page.locator('main h1, main .empty .lead').first()).toBeVisible();
  await expect(page.locator('main .skeleton')).toHaveCount(0);
  await expect(page.locator('main [aria-busy="true"]')).toHaveCount(0);
  await expect(page.locator('main [data-phase="loading"]')).toHaveCount(0);
  await expect(page.locator('main', { hasText: 'Loading the dependency graph' })).toHaveCount(0);
}

/** Rows of the main data table (group header rows excluded); also used inside the page, hence the plain CSS. */
export const DATA_ROWS = 'main table tbody tr:not(.group):not(.skeleton)';
export const dataRows = (page: Page) => page.locator(DATA_ROWS);

/** The reasons the e2e server's registry gives (playwright.config.ts flags; strings from engine/panels.py). */
export const REASONS = {
  readOnly: 'Panel is read-only via SHARPIT_PANELS_MCP_SERVER_READ_ONLY=true', // read_only_reason('mcp-server', False)
  disabled: 'Panel is disabled via SHARPIT_PANELS_CLI_ENABLED=false', // disabled_reason('cli'), mirrored by App.svelte
};
