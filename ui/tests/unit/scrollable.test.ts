// @vitest-environment jsdom
import { afterEach, expect, it, vi } from 'vitest';
import { scrollable } from '../../src/lib/scrollable';

let observed: (() => void) | null = null;
class FakeResizeObserver {
  constructor(cb: () => void) { observed = cb; }
  observe() {}
  disconnect() {}
}

function region(scrollHeight: number, clientHeight: number) {
  const node = document.createElement('div');
  Object.defineProperty(node, 'scrollHeight', { configurable: true, get: () => scrollHeight });
  Object.defineProperty(node, 'clientHeight', { configurable: true, get: () => clientHeight });
  document.body.append(node);
  return {
    node,
    resize(s: number, c: number) {
      scrollHeight = s;
      clientHeight = c;
      observed?.();
    },
  };
}

afterEach(() => {
  vi.unstubAllGlobals();
  document.body.replaceChildren();
  observed = null;
});

it('is a tab stop only while it overflows', () => {
  vi.stubGlobal('ResizeObserver', FakeResizeObserver);
  const r = region(500, 100);
  const action = scrollable(r.node);
  expect(r.node.getAttribute('tabindex')).toBe('0');
  r.resize(100, 100);
  expect(r.node.hasAttribute('tabindex')).toBe(false);
  r.resize(300, 100);
  expect(r.node.getAttribute('tabindex')).toBe('0');
  action.destroy?.();
});

it('a short region adds no tab stop', () => {
  vi.stubGlobal('ResizeObserver', FakeResizeObserver);
  const r = region(50, 100);
  scrollable(r.node);
  expect(r.node.hasAttribute('tabindex')).toBe(false);
});

it('never pulls focus out from under the user when the content shrinks', () => {
  vi.stubGlobal('ResizeObserver', FakeResizeObserver);
  const r = region(500, 100);
  scrollable(r.node);
  r.node.focus();
  r.resize(100, 100);
  expect(document.activeElement).toBe(r.node);
  expect(r.node.getAttribute('tabindex')).toBe('0');
});
