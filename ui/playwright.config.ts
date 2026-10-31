import os from 'node:os';
import path from 'node:path';
import { defineConfig, devices } from '@playwright/test';
import { TOKEN } from './tests/e2e/support';

// The port comes from the multi-agent lease (`agentctl.py lease app-port`), never a hard-coded default.
const port = process.env.SHARPIT_E2E_PORT;
if (!port) throw new Error('Set SHARPIT_E2E_PORT to the app port leased via agentctl');
const scratch = path.join(os.tmpdir(), `sharpit-e2e-${port}`);
const unreachable = 'http://127.0.0.1:9'; // an unstubbed scan fails fast instead of calling OSV.dev or FIRST

const SERVER_ENV: Record<string, string> = {
  // Loopback stays trusted; a request carrying X-Forwarded-For is an untrusted source that needs this token.
  SHARPIT_ALLOW_NON_LOCALHOST: 'true',
  SHARPIT_AUTHENTICATION_TOKEN: TOKEN,
  // A real read-only and a real disabled panel, so the rail shows the server's reasons (§10.1).
  SHARPIT_PANELS_MCP_SERVER_READ_ONLY: 'true',
  SHARPIT_PANELS_CLI_ENABLED: 'false',
  SHARPIT_STATE_DIR: path.join(scratch, 'state'),
  SHARPIT_VULNERABILITIES_OSV_BASE_URI: unreachable,
  SHARPIT_VULNERABILITIES_EPSS_BASE_URI: unreachable,
  SAMPLE_MANY_LOGGERS: '1000',
  DEBUG: 'false', // an environment value over a Settings default: Configuration marks the winning source (§10.4)
};

export default defineConfig({
  testDir: 'tests/e2e',
  outputDir: path.join(scratch, 'test-results'), // traces and failure artefacts stay out of the repo
  reporter: [['list']],
  workers: 1, // one shared server whose logger levels and scan state the tests observe
  timeout: 60_000,
  use: {
    ...devices['Desktop Chrome'],
    baseURL: `http://127.0.0.1:${port}/sharpit/`,
    viewport: { width: 1280, height: 800 },
  },
  // The real app and sharpit's real CSP, serving the committed build in src/sharpit/ui/static (not a Vite dev server).
  webServer: {
    command: `node ui/tests/e2e/serve.mjs ${port}`, // uvicorn on the example app, minimal environment
    cwd: '..',
    url: `http://127.0.0.1:${port}/sharpit/`,
    reuseExistingServer: false,
    timeout: 60_000,
    stdout: 'ignore',
    stderr: 'pipe',
    // serve.mjs forwards only these keys (plus what the OS and uv need): the run ignores the caller's SHARPIT_* settings.
    env: { ...SERVER_ENV, SHARPIT_E2E_KEYS: Object.keys(SERVER_ENV).join(',') },
  },
});
