import { writable } from 'svelte/store';

/** Set when the server answers 401: the UI shows the token prompt, which calls `auth/session`. */
export const authRequired = writable(false);
/** The server's own busy text from a 409, shown next to the action that hit it. */
export const busyMessage = writable<string | null>(null);

export type Params = Record<string, string | number | boolean | null | undefined>;

export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly body: unknown,
    message = `HTTP ${status}`,
  ) {
    super(message);
    this.name = 'ApiError';
  }
}

export const get = <T>(path: string, params?: Params) => request<T>('GET', path, params);
export const post = <T>(path: string, body?: unknown) => request<T>('POST', path, undefined, body);
export const del = <T>(path: string, params?: Params) => request<T>('DELETE', path, params);

/** The token prompt: `auth/session` checks the bearer token and, for an untrusted source, sets the session cookie. */
export const session = (token: string) =>
  request<void>('POST', 'auth/session', undefined, undefined, { authorization: `Bearer ${token}` });

// Relative `api/...` so the UI works under whatever path the host mounts sharpit at.
// `path` segments are the caller's to encode (e.g. `loggers/${encodeURIComponent(name)}`).
function url(path: string, params: Params = {}): string {
  const query = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== null && value !== undefined && value !== '') query.set(key, String(value));
  }
  const qs = query.toString();
  return `api/${path}${qs ? `?${qs}` : ''}`;
}

async function request<T>(
  method: string,
  path: string,
  params?: Params,
  body?: unknown,
  headers: Record<string, string> = {},
): Promise<T> {
  const init: RequestInit = { method, cache: 'no-store', headers };
  if (body !== undefined) {
    init.headers = { ...headers, 'content-type': 'application/json' };
    init.body = JSON.stringify(body);
  }
  const res = await fetch(url(path, params), init);
  const data = await readJson(res);
  if (!res.ok) {
    if (res.status === 401) authRequired.set(true);
    if (res.status === 409) busyMessage.set(field(data, 'message') ?? field(data, 'error') ?? `HTTP ${res.status}`);
    throw new ApiError(res.status, data === NOT_JSON ? null : data);
  }
  authRequired.set(false);
  busyMessage.set(null);
  if (res.status === 204) return undefined as T;
  // e.g. a proxy's HTML page with 200: fail loudly rather than hand the view `undefined`
  if (data === NOT_JSON) throw new ApiError(res.status, null, `HTTP ${res.status}: the response is not JSON`);
  return data as T;
}

const NOT_JSON = Symbol('not JSON');

async function readJson(res: Response): Promise<unknown> {
  if (!res.headers.get('content-type')?.toLowerCase().includes('json')) return NOT_JSON;
  try {
    return await res.json();
  } catch {
    return NOT_JSON;
  }
}

function field(data: unknown, key: string): string | undefined {
  const value = typeof data === 'object' && data !== null ? (data as Record<string, unknown>)[key] : undefined;
  return typeof value === 'string' ? value : undefined;
}
