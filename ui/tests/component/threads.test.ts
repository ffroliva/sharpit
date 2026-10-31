// @vitest-environment jsdom
import { expect, it } from 'vitest';
import Threads from '../../src/views/Threads.svelte';
import { harness, json, page, until } from './support';

const thread = (id: number, name: string, state: string, stackTrace: string[] = []) => ({ id, name, state, daemon: false, stackTrace });
const report = (threads: unknown[], tasks: unknown[] = [], warnings: string[] = []) => ({
  available: true, unavailableReason: null, capturedAt: 1, totalThreads: threads.length, daemonThreads: 0,
  stateCounts: [{ state: 'RUNNABLE', count: 1 }, { state: 'WAITING', count: 1 }], threads, page: page(threads.length),
  tasks, taskCount: tasks.length, warnings,
});
const h = harness();
const tab = (name: string) => [...h.target.querySelectorAll<HTMLElement>('[role="tab"]')].find((t) => t.textContent?.startsWith(name))!;

it('shows loading, then the threads with state chips', async () => {
  h.route((url) => (url.startsWith('api/threads') ? json(200, report([thread(1, 'MainThread', 'RUNNABLE'), thread(2, 'worker', 'WAITING')])) : undefined));
  h.mount(Threads);
  expect(h.text()).toContain('Loading');
  await until(() => expect(h.text()).toContain('MainThread'));
  expect(h.text()).toContain('WAITING');
  expect(h.text()).toContain('C-level waits'); // the help says time.sleep reads as RUNNABLE
});

it('shows the error state', async () => {
  h.route(() => json(500, { error: 'x' }));
  h.mount(Threads);
  await until(() => expect(h.target.querySelector('[role="alert"]')?.textContent).toContain('Could not load'));
});

it('highlights application frames in an expanded stack', async () => {
  const stack = ['app.main.handler (/srv/app/main.py:12)', 'threading.wait (/usr/lib/python3.12/threading.py:320)'];
  h.route((url) => (url.startsWith('api/threads') ? json(200, report([thread(1, 'MainThread', 'RUNNABLE', stack)])) : undefined));
  h.mount(Threads);
  await until(() => expect(h.text()).toContain('MainThread'));
  [...h.target.querySelectorAll('button')].find((b) => b.textContent?.includes('MainThread'))!.click();
  await until(() => expect(h.target.querySelectorAll('li.app')).toHaveLength(1));
  expect(h.target.querySelector('li.app')?.textContent).toContain('main.py:12');
});

it('the Tasks tab lists asyncio tasks with their request, and has its own empty state', async () => {
  const task = { name: 'Task-7', coroutine: 'sleeper', state: 'PENDING', stackTrace: ['app.sleeper (/srv/app/s.py:3)'], request: { method: 'GET', path: '/sleeper', ageMs: 5 } };
  h.route((url) => (url.startsWith('api/threads') ? json(200, report([thread(1, 'MainThread', 'RUNNABLE')], [task])) : undefined));
  h.mount(Threads);
  await until(() => expect(h.text()).toContain('MainThread'));
  tab('Tasks').click();
  await until(() => expect(h.text()).toContain('Task-7'));
  expect(h.text()).toContain('GET /sleeper');
  h.route((url) => (url.startsWith('api/threads') ? json(200, report([thread(1, 'MainThread', 'RUNNABLE')], [], ['no loop'])) : undefined));
  [...h.target.querySelectorAll('button')].find((b) => b.textContent === 'Refresh')!.click();
  await until(() => expect(h.text()).toContain('No asyncio tasks'));
  expect(h.text()).toContain('no loop');
});

it('filtering by a state chip asks the server for that state', async () => {
  h.route((url) => (url.startsWith('api/threads') ? json(200, report([thread(2, 'worker', 'WAITING')])) : undefined));
  h.mount(Threads);
  await until(() => expect(h.text()).toContain('worker'));
  [...h.target.querySelectorAll('button')].find((b) => b.textContent?.startsWith('WAITING'))!.click();
  await until(() => expect(h.calls('GET').at(-1)).toContain('state=WAITING'));
});
