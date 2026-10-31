import { expect, it } from 'vitest';
import { isApplicationFrame, statusFamilyClass } from '../../src/lib/status';

it('colours a status by its family', () => {
  expect([200, 204, 302, 404, 499, 500, 503, 100].map(statusFamilyClass)).toEqual([
    'ok', 'ok', 'muted', 'warn', 'warn', 'danger', 'danger', 'muted',
  ]);
  expect(statusFamilyClass(null)).toBe('muted');
});

it('an exception frame carries its own flag', () => {
  expect(isApplicationFrame({ applicationFrame: true })).toBe(true);
  expect(isApplicationFrame({ applicationFrame: false })).toBe(false);
});

it('a thread stack line is judged by its file: installed packages, the standard library and synthetic files are not the app', () => {
  expect(isApplicationFrame('app.main.handler (C:\\work\\app\\main.py:12)')).toBe(true);
  expect(isApplicationFrame('app.main.handler (/srv/app/main.py:12)')).toBe(true);
  expect(isApplicationFrame('starlette.routing.run (/venv/lib/python3.12/site-packages/starlette/routing.py:9)')).toBe(false);
  expect(isApplicationFrame('threading.wait (C:\\Python312\\Lib\\threading.py:320)')).toBe(false);
  expect(isApplicationFrame('threading.wait (/usr/lib/python3.12/threading.py:320)')).toBe(false);
  expect(isApplicationFrame('importlib._bootstrap (<frozen importlib._bootstrap>:1)')).toBe(false);
  expect(isApplicationFrame('no location at all')).toBe(false);
  expect(isApplicationFrame('app.handler (C:\\work\\app\\main.py:12x)')).toBe(false);
});
