// @vitest-environment jsdom
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { openStream, type StreamState } from '../../src/lib/sse';
import { FakeEventSource } from '../component/support';

const states: StreamState[] = [];
const opened: { close(): void }[] = [];
beforeEach(() => {
  vi.useFakeTimers();
  FakeEventSource.instances = [];
  states.length = 0;
  vi.stubGlobal('EventSource', FakeEventSource);
});
afterEach(() => {
  opened.splice(0).forEach((s) => s.close());
  vi.useRealTimers();
  vi.unstubAllGlobals();
  Object.defineProperty(document, 'visibilityState', { value: 'visible', configurable: true });
});
const track = <T extends { close(): void }>(s: T) => (opened.push(s), s);
const open = (extra = {}) => track(openStream('api/log-tail/stream', { onState: (s) => states.push(s), ...extra }));

it('a server close is a planned rotation: it stays connected and reloads after the reopen', () => {
  const onUpdate = vi.fn();
  open({ onUpdate });
  FakeEventSource.last.open();
  FakeEventSource.last.fail(false); // readyState CONNECTING: the browser reconnects by itself
  expect(states).toEqual(['connecting', 'connected']);
  FakeEventSource.last.open();
  expect(onUpdate).toHaveBeenCalledTimes(1);
  expect(FakeEventSource.instances).toHaveLength(1);
});

it('an update event calls onUpdate', () => {
  const onUpdate = vi.fn();
  open({ onUpdate });
  FakeEventSource.last.emit('update');
  expect(onUpdate).toHaveBeenCalledTimes(1);
});

it('drops a line whose id it already has, and resumes with ?after=<lastId> on a reopen', () => {
  const onLine = vi.fn();
  open({ onLine });
  const first = FakeEventSource.last;
  first.emit('log', '{"n":1}', 'a-1');
  first.emit('log', '{"n":1}', 'a-1');
  first.emit('log', '{"n":2}', 'a-2');
  expect(onLine).toHaveBeenCalledTimes(2);
  first.fail(true);
  vi.advanceTimersByTime(1000);
  expect(FakeEventSource.last.url).toBe('api/log-tail/stream?after=a-2');
});

it('a stream with no ids reopens on the plain URL', () => {
  track(openStream('api/activity/stream', {}));
  FakeEventSource.last.fail(true);
  vi.advanceTimersByTime(1000);
  expect(FakeEventSource.last.url).toBe('api/activity/stream');
});

it('closes when the tab is hidden and reopens, reloading, when it is visible again', () => {
  const onUpdate = vi.fn();
  open({ onUpdate });
  const first = FakeEventSource.last;
  Object.defineProperty(document, 'visibilityState', { value: 'hidden', configurable: true });
  document.dispatchEvent(new Event('visibilitychange'));
  expect(first.readyState).toBe(2);
  Object.defineProperty(document, 'visibilityState', { value: 'visible', configurable: true });
  document.dispatchEvent(new Event('visibilitychange'));
  expect(FakeEventSource.instances).toHaveLength(2);
  expect(onUpdate).toHaveBeenCalledTimes(1);
});

it('a CLOSED error (503, 403) reopens by itself: 1 s, 2 s, 4 s ... capped at 30 s, reset by a message', () => {
  open();
  const waits: number[] = [];
  for (let i = 0; i < 7; i++) {
    const before = FakeEventSource.instances.length;
    FakeEventSource.last.fail(true);
    let waited = 0;
    while (FakeEventSource.instances.length === before) {
      vi.advanceTimersByTime(500);
      waited += 500;
    }
    waits.push(waited);
  }
  expect(waits).toEqual([1000, 2000, 4000, 8000, 16000, 30000, 30000]);
  expect(states).toContain('error');
  FakeEventSource.last.emit('update');
  FakeEventSource.last.fail(true);
  const before = FakeEventSource.instances.length;
  vi.advanceTimersByTime(1000);
  expect(FakeEventSource.instances.length).toBe(before + 1);
});

it('close() stops everything, including a pending reopen', () => {
  const s = open();
  FakeEventSource.last.fail(true);
  s.close();
  vi.advanceTimersByTime(60_000);
  expect(FakeEventSource.instances).toHaveLength(1);
});

it('a stream reopened after a refused (CLOSED) connect reloads the panel, so a tick in the gap is not lost', () => {
  const onUpdate = vi.fn();
  open({ onUpdate });
  FakeEventSource.last.fail(true);
  vi.advanceTimersByTime(1000);
  FakeEventSource.last.open();
  expect(onUpdate).toHaveBeenCalledTimes(1);
});

it('an accepted stream resets the backoff even when it stays quiet', () => {
  open();
  for (const wait of [1000, 2000, 4000]) {
    FakeEventSource.last.fail(true);
    vi.advanceTimersByTime(wait);
  }
  FakeEventSource.last.open(); // healthy for a long time, no ticks
  FakeEventSource.last.fail(true);
  const before = FakeEventSource.instances.length;
  vi.advanceTimersByTime(1000);
  expect(FakeEventSource.instances.length).toBe(before + 1);
});
