// @vitest-environment jsdom
import { expect, it, vi } from 'vitest';
import LogTail from '../../src/views/LogTail.svelte';
import { FakeEventSource, harness, until } from './support';

const line = (message: string, level = 'INFO', logger = 'app') => JSON.stringify({ timestamp: 1_700_000_000_000, level, logger, message, thread: 'MainThread' });
const h = harness();

function feed(lines: [string, string, string?, string?][]) {
  const es = FakeEventSource.last;
  es.open();
  lines.forEach(([id, message, level, logger]) => es.emit('log', line(message, level, logger), id));
}

it('is loading until the stream opens, then shows the empty hint', async () => {
  h.mount(LogTail);
  expect(h.text()).toContain('Connecting');
  FakeEventSource.last.open();
  await until(() => expect(h.text()).toContain('No log lines yet'));
  expect(h.text()).toContain('root logger');
  expect(FakeEventSource.last.url).toBe('api/log-tail/stream');
});

it('shows the error state while the stream is refused, and recovers on its own', async () => {
  vi.useFakeTimers();
  h.mount(LogTail);
  FakeEventSource.last.fail(true);
  await vi.advanceTimersByTimeAsync(0);
  expect(h.target.querySelector('[role="alert"]')?.textContent).toContain('Log stream');
  await vi.advanceTimersByTimeAsync(1000);
  FakeEventSource.last.open();
  await vi.advanceTimersByTimeAsync(0);
  expect(h.target.querySelector('[role="alert"]')).toBeNull();
  vi.useRealTimers();
});

it('renders lines as text with level classes, drops a repeated id, filters by level, logger and text', async () => {
  h.mount(LogTail);
  feed([['n-1', '<b>bold</b> hello'], ['n-1', '<b>bold</b> hello'], ['n-2', 'disk full', 'ERROR', 'app.db'], ['n-3', 'tick', 'DEBUG', 'app']]);
  await until(() => expect(h.target.querySelectorAll('li.line')).toHaveLength(3));
  expect(h.target.querySelector('b')).toBeNull();
  expect(h.target.querySelector('li.line.danger')?.textContent).toContain('disk full');
  const set = (sel: string, value: string, ev = 'change') => {
    const el = h.target.querySelector<HTMLInputElement | HTMLSelectElement>(sel)!;
    el.value = value;
    el.dispatchEvent(new Event(ev, { bubbles: true }));
  };
  set('select[aria-label="Level"]', 'ERROR');
  await until(() => expect(h.target.querySelectorAll('li.line')).toHaveLength(1));
  set('select[aria-label="Level"]', '');
  set('input[aria-label="Logger"]', 'app.db', 'input');
  await until(() => expect(h.target.querySelectorAll('li.line')).toHaveLength(1));
  set('input[aria-label="Logger"]', '', 'input');
  set('input[aria-label="Search"]', 'hello', 'input');
  await until(() => expect(h.target.querySelectorAll('li.line')).toHaveLength(1));
});

it('pause closes the stream, resume reopens it from the last id', async () => {
  h.mount(LogTail);
  feed([['n-1', 'one'], ['n-2', 'two']]);
  await until(() => expect(h.target.querySelectorAll('li.line')).toHaveLength(2));
  const btn = (name: string) => [...h.target.querySelectorAll('button')].find((b) => b.textContent === name)!;
  btn('Pause').click();
  await until(() => expect(FakeEventSource.last.readyState).toBe(2));
  btn('Resume').click();
  await until(() => expect(FakeEventSource.last.url).toBe('api/log-tail/stream?after=n-2'));
});

it('copies the visible lines', async () => {
  const writeText = vi.fn(() => Promise.resolve());
  Object.defineProperty(navigator, 'clipboard', { value: { writeText }, configurable: true });
  h.mount(LogTail);
  feed([['n-1', 'one'], ['n-2', 'two', 'ERROR']]);
  await until(() => expect(h.target.querySelectorAll('li.line')).toHaveLength(2));
  [...h.target.querySelectorAll('button')].find((b) => b.textContent === 'Copy visible')!.click();
  expect(writeText).toHaveBeenCalledTimes(1);
  const text = (writeText.mock.calls[0] as unknown as [string])[0];
  expect(text).toContain('one');
  expect(text).toContain('ERROR');
});
