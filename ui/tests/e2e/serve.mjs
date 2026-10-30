// Starts the example app for the e2e run with a minimal environment. Playwright's webServer always merges the whole
// process.env, and the Configuration panel (and so the committed screenshots) would show every variable on this machine.
import { spawn } from 'node:child_process';

const KEEP = /^(path|pathext|systemroot|systemdrive|comspec|windir|temp|tmp|home|userprofile|appdata|localappdata|homedrive|homepath|uv_.*|sharpit_.*|sample_.*)$/i;
const env = Object.fromEntries(Object.entries(process.env).filter(([name]) => KEEP.test(name) && name !== 'SHARPIT_E2E_PORT'));
const port = process.argv[2];
const args = ['run', 'uvicorn', 'examples.fastapi_sample.app:create_app', '--factory', '--host', '127.0.0.1', '--port', port];
const server = spawn('uv', args, { env, stdio: 'inherit', shell: process.platform === 'win32' });
server.on('exit', (code) => process.exit(code ?? 1));
