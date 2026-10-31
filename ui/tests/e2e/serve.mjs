// Starts the example app for the e2e run with a hermetic environment. Playwright's webServer always merges the whole
// process.env; this keeps only what the OS and uv need plus the keys playwright.config.ts sets (SHARPIT_E2E_KEYS), so
// neither the caller's SHARPIT_* settings nor this machine's variables reach the app (or the committed screenshots).
import { spawn } from 'node:child_process';
import { existsSync } from 'node:fs';
import { delimiter, join } from 'node:path';

const OS = /^(path|pathext|systemroot|systemdrive|comspec|windir|temp|tmp|home|userprofile|appdata|localappdata|homedrive|homepath)$/i;
const keys = new Set((process.env.SHARPIT_E2E_KEYS ?? '').split(',').filter(Boolean));
const env = Object.fromEntries(Object.entries(process.env).filter(([name]) => OS.test(name) || keys.has(name)));
const port = Number(process.argv[2]);
if (!Number.isInteger(port) || port < 1 || port > 65535) throw new Error('port must be an integer from 1 to 65535');
const uvName = process.platform === 'win32' ? 'uv.exe' : 'uv';
const uv = (process.env.PATH ?? '').split(delimiter).map((dir) => join(dir, uvName)).find(existsSync);
if (!uv) throw new Error('uv executable not found on PATH');
// playwright.sqla.config.ts serves the SQLAlchemy dogfood sample instead of the default example app
const app = process.env.SHARPIT_E2E_APP || 'examples.fastapi_sample.app:create_app';
const args = ['run', 'uvicorn', app, '--factory', '--host', '127.0.0.1', '--port', String(port)];
const server = spawn(uv, args, { env, stdio: 'inherit', shell: false });
server.on('exit', (code) => process.exit(code ?? 1));
