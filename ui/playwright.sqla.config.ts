import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { defineConfig, devices } from '@playwright/test';

// The 0.2.0 panels against the SQLAlchemy dogfood sample (spec 14.3, 15). Same shape as playwright.config.ts.
// The port comes from the multi-agent lease (`agentctl.py lease app-port`), never a hard-coded default.
const port = process.env.SHARPIT_E2E_PORT;
if (!port) throw new Error('Set SHARPIT_E2E_PORT to the app port leased via agentctl');
const scratch = path.join(os.tmpdir(), `sharpit-e2e-sqla-${port}`);
const db = path.join(scratch, 'db');
// A fresh database (two revisions applied, one pending) and no dismissals left by a previous run. Workers load this file
// again while the server holds the database open, so only the main process resets it.
if (!process.env.TEST_WORKER_INDEX) {
  for (const dir of [db, path.join(scratch, 'state')]) fs.rmSync(dir, { recursive: true, force: true });
  fs.mkdirSync(db, { recursive: true });
}
const unreachable = 'http://127.0.0.1:9';

const SERVER_ENV: Record<string, string> = {
  SHARPIT_SQLA_DB_DIR: db, // read by the sample's create_app and by its Alembic env.py
  SHARPIT_STATE_DIR: path.join(scratch, 'state'),
  SHARPIT_VULNERABILITIES_OSV_BASE_URI: unreachable,
  SHARPIT_VULNERABILITIES_EPSS_BASE_URI: unreachable,
};

export default defineConfig({
  testDir: 'tests/e2e',
  testMatch: 'panels-0.2.0.spec.ts',
  outputDir: path.join(scratch, 'test-results'),
  reporter: [['list']],
  workers: 1, // one shared server whose captured requests the tests observe
  timeout: 60_000,
  use: {
    ...devices['Desktop Chrome'],
    baseURL: `http://127.0.0.1:${port}/sharpit/`,
    viewport: { width: 1280, height: 800 },
  },
  webServer: {
    // the sample's own Alembic applies revisions 0001 and 0002, then the real app starts under sharpit's CSP
    command: `uv run --no-sync alembic -c examples/fastapi_sqla/alembic.ini upgrade 0002 && node ui/tests/e2e/serve.mjs ${port}`,
    cwd: '..',
    url: `http://127.0.0.1:${port}/sharpit/`,
    reuseExistingServer: false,
    timeout: 90_000,
    stdout: 'ignore',
    stderr: 'pipe',
    env: {
      ...SERVER_ENV,
      SHARPIT_E2E_APP: 'examples.fastapi_sqla.app:create_app',
      SHARPIT_E2E_KEYS: Object.keys(SERVER_ENV).join(','),
    },
  },
});
