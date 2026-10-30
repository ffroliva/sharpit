import { get as read } from 'svelte/store';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ApiError, authRequired, busyMessage, del, get, post, session } from '../../src/lib/api';
import apiSource from '../../src/lib/api.ts?raw';
import overview from '../../../tests/fixtures/bootui/overview.json';

const fetchMock = vi.fn<typeof fetch>();

function json(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), { status, headers: { 'content-type': 'application/json' } });
}

beforeEach(() => {
  fetchMock.mockReset();
  vi.stubGlobal('fetch', fetchMock);
  authRequired.set(false);
  busyMessage.set(null);
});
afterEach(() => vi.unstubAllGlobals());

describe('urls', () => {
  it('uses a relative api/ url so the UI works under any mount path', async () => {
    fetchMock.mockResolvedValue(json(200, overview));
    expect(await get('overview')).toEqual(overview);
    const [url, init] = fetchMock.mock.calls[0]!;
    expect(url).toBe('api/overview');
    expect(init?.method).toBe('GET');
  });

  it('encodes params and drops empty ones', async () => {
    fetchMock.mockResolvedValue(json(200, {}));
    await get('config', { q: 'db url', source: '', overridesOnly: false, offset: 0, limit: 200, x: null, y: undefined });
    expect(fetchMock.mock.calls[0]![0]).toBe('api/config?q=db+url&overridesOnly=false&offset=0&limit=200');
  });

  it('post sends a JSON body, del sends DELETE', async () => {
    fetchMock.mockResolvedValueOnce(json(200, { name: 'ROOT' })).mockResolvedValueOnce(new Response(null, { status: 204 }));
    await post('loggers/ROOT', { level: 'DEBUG' });
    expect(fetchMock.mock.calls[0]![0]).toBe('api/loggers/ROOT');
    const init = fetchMock.mock.calls[0]![1]!;
    expect(init.method).toBe('POST');
    expect(init.body).toBe('{"level":"DEBUG"}');
    expect(new Headers(init.headers).get('content-type')).toBe('application/json');
    expect(await del('dismissed-rules/1')).toBeUndefined();
    expect(fetchMock.mock.calls[1]![1]!.method).toBe('DELETE');
  });
});

describe('errors', () => {
  it('401 sets authRequired and throws ApiError with the body', async () => {
    const body = { error: 'sharpit authentication required' };
    fetchMock.mockResolvedValue(json(401, body));
    const err = await post('vulnerabilities').catch((e: unknown) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect(err).toMatchObject({ status: 401, body });
    expect(read(authRequired)).toBe(true);
    expect(read(busyMessage)).toBeNull();
  });

  it('409 busy sets busyMessage from the server body', async () => {
    const body = {
      error: 'sharpit action already in progress',
      operation: 'vulnerability-scan',
      activeOperation: 'vulnerability-scan',
      message: "Operation 'vulnerability-scan' cannot start while 'vulnerability-scan' is in progress.",
    };
    fetchMock.mockResolvedValue(json(409, body));
    await expect(post('vulnerabilities')).rejects.toMatchObject({ status: 409, body });
    expect(read(busyMessage)).toBe(body.message);
    expect(read(authRequired)).toBe(false);
  });

  it('409 without a message falls back to the error text', async () => {
    fetchMock.mockResolvedValue(json(409, { error: 'sharpit action already in progress' }));
    await expect(post('vulnerabilities')).rejects.toBeInstanceOf(ApiError);
    expect(read(busyMessage)).toBe('sharpit action already in progress');
  });

  it('the busy text is never hard-coded in api.ts', () => {
    expect(apiSource).not.toContain('already in progress');
  });

  it('a non-JSON error body becomes ApiError with body null', async () => {
    fetchMock.mockResolvedValue(new Response('<html>oops</html>', { status: 500, headers: { 'content-type': 'text/html' } }));
    await expect(get('overview')).rejects.toMatchObject({ status: 500, body: null });
  });
});

describe('success', () => {
  it('a 200 with a non-JSON body is a clear ApiError, not undefined', async () => {
    fetchMock.mockResolvedValue(new Response('<html>proxy page</html>', { status: 200, headers: { 'content-type': 'text/html' } }));
    const err = await get('overview').catch((e: unknown) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect(err).toMatchObject({ status: 200, body: null });
    expect((err as Error).message).toMatch(/not JSON/);
  });

  it('a 200 with malformed JSON is an ApiError too', async () => {
    fetchMock.mockResolvedValue(new Response('{oops', { status: 200, headers: { 'content-type': 'application/json' } }));
    await expect(get('overview')).rejects.toBeInstanceOf(ApiError);
  });

  it('a successful request clears busyMessage and authRequired', async () => {
    authRequired.set(true);
    busyMessage.set('busy');
    fetchMock.mockResolvedValue(json(200, overview));
    await get('overview');
    expect(read(authRequired)).toBe(false);
    expect(read(busyMessage)).toBeNull();
  });
});

describe('session', () => {
  it('posts api/auth/session with the bearer token and clears the prompt state', async () => {
    authRequired.set(true);
    busyMessage.set('busy');
    fetchMock.mockResolvedValue(new Response(null, { status: 204 }));
    await session('s3cret');
    const [url, init] = fetchMock.mock.calls[0]!;
    expect(url).toBe('api/auth/session');
    expect(init?.method).toBe('POST');
    expect(new Headers(init?.headers).get('authorization')).toBe('Bearer s3cret');
    expect(read(authRequired)).toBe(false);
    expect(read(busyMessage)).toBeNull();
  });

  it('a rejected token throws ApiError 401 and keeps the prompt up', async () => {
    authRequired.set(true);
    fetchMock.mockResolvedValue(json(401, { error: 'sharpit authentication required' }));
    await expect(session('wrong')).rejects.toMatchObject({ status: 401 });
    expect(read(authRequired)).toBe(true);
  });
});
