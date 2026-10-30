// @vitest-environment jsdom
import { flushSync, mount, unmount } from 'svelte';
import { get as read } from 'svelte/store';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import TokenPrompt from '../../src/components/TokenPrompt.svelte';
import { authRequired } from '../../src/lib/api';

const fetchMock = vi.fn<typeof fetch>();
let target: HTMLElement;
let component: ReturnType<typeof mount> | null = null;
let onauthenticated: ReturnType<typeof vi.fn>;

const input = () => target.querySelector<HTMLInputElement>('#token')!;
const submitButton = () => target.querySelector<HTMLButtonElement>('button[type="submit"]')!;
const until = (fn: () => void) => vi.waitFor(fn, { timeout: 1000, interval: 5 });

function type(value: string) {
  input().value = value;
  input().dispatchEvent(new Event('input', { bubbles: true }));
  flushSync();
}

beforeEach(() => {
  fetchMock.mockReset();
  vi.stubGlobal('fetch', fetchMock);
  authRequired.set(true);
  onauthenticated = vi.fn();
  target = document.createElement('div');
  document.body.append(target);
  component = mount(TokenPrompt, { target, props: { onauthenticated: onauthenticated as unknown as () => void } });
  flushSync();
});
afterEach(() => {
  if (component) unmount(component);
  component = null;
  target.remove();
  vi.unstubAllGlobals();
});

describe('TokenPrompt', () => {
  it('is a password field, and Unlock stays disabled until a token is typed', () => {
    expect(input().type).toBe('password');
    expect(submitButton().disabled).toBe(true);
    type('   ');
    expect(submitButton().disabled).toBe(true);
    type('abc');
    expect(submitButton().disabled).toBe(false);
  });

  it('posts api/auth/session with the bearer token, then reports success', async () => {
    fetchMock.mockResolvedValue(new Response(null, { status: 204 }));
    type(' s3cret ');
    submitButton().click();
    await until(() => expect(onauthenticated).toHaveBeenCalledTimes(1));
    const [url, init] = fetchMock.mock.calls[0]!;
    expect(url).toBe('api/auth/session');
    expect(init?.method).toBe('POST');
    expect(new Headers(init?.headers).get('authorization')).toBe('Bearer s3cret');
    expect(read(authRequired)).toBe(false);
    expect(input().value).toBe('');
  });

  it('a rejected token says so and does not call back', async () => {
    fetchMock.mockResolvedValue(
      new Response(JSON.stringify({ error: 'sharpit authentication required' }), {
        status: 401, headers: { 'content-type': 'application/json' },
      }),
    );
    type('wrong');
    submitButton().click();
    await until(() => expect(target.querySelector('[role="alert"]')?.textContent).toContain('not accepted'));
    expect(onauthenticated).not.toHaveBeenCalled();
    expect(input().getAttribute('aria-invalid')).toBe('true');
    expect(submitButton().disabled).toBe(false);
  });

  it('an unreachable server gets its own message', async () => {
    fetchMock.mockRejectedValue(new TypeError('Failed to fetch'));
    type('abc');
    submitButton().click();
    await until(() => expect(target.querySelector('[role="alert"]')?.textContent).toContain('not responding'));
  });

  it('shows Checking… and blocks a second submit while the call is in flight', async () => {
    let finish!: (r: Response) => void;
    fetchMock.mockReturnValue(new Promise<Response>((resolve) => (finish = resolve)));
    type('abc');
    submitButton().click();
    await until(() => expect(submitButton().textContent).toContain('Checking'));
    expect(submitButton().disabled).toBe(true);
    submitButton().click();
    expect(fetchMock).toHaveBeenCalledTimes(1);
    finish(new Response(null, { status: 204 }));
    await until(() => expect(onauthenticated).toHaveBeenCalled());
  });
});
