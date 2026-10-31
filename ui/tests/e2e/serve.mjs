// Starts the example app for the e2e run with a hermetic environment. Playwright's webServer always merges the whole
// process.env; this keeps only what the OS and uv need plus the keys playwright.config.ts sets (SHARPIT_E2E_KEYS), so
// neither the caller's SHARPIT_* settings nor this machine's variables reach the app (or the committed screenshots).
import { spawn } from 'node:child_process';

const OS = /^(path|pathext|systemroot|systemdrive|comspec|windir|temp|tmp|home|userprofile|appdata|localappdata|homedrive|homepath)$/i;
const keys = new Set((process.env.SHARPIT_E2E_KEYS ?? '').split(',').filter(Boolean));
const env = Object.fromEntries(Object.entries(process.env).filter(([name]) => OS.test(name) || keys.has(name)));
const port = process.argv[2];
const args = ['run', 'uvicorn', 'examples.fastapi_sample.app:create_app', '--factory', '--host', '127.0.0.1', '--port', port];
const server = spawn('uv', args, { env, stdio: 'inherit', shell: process.platform === 'win32' });
server.on('exit', (code) => process.exit(code ?? 1));
