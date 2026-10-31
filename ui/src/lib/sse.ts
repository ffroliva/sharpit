export type StreamState = 'connecting' | 'connected' | 'error' | 'closed';

export interface StreamHandlers {
  /** A change tick, or the panel's cue to reload after a reopen (a tick in the gap would otherwise be lost). */
  onUpdate?: () => void;
  /** A log line; a repeated id is dropped before this is called. */
  onLine?: (data: string, id: string) => void;
  onState?: (state: StreamState) => void;
  /** Resume a log stream after this event id. */
  after?: string;
}

const CLOSED = 2; // EventSource.CLOSED, spelled out so tests can stand in for the class
const MAX_SEEN = 5000;

const withAfter = (url: string, id: string) => `${url}${url.includes('?') ? '&' : '?'}after=${encodeURIComponent(id)}`;

/**
 * An SSE stream with the behaviour sharpit's server needs (spec 10):
 * - the server closes every few seconds on purpose: an error while the browser is CONNECTING is a rotation, so the
 *   state stays "connected" and the panel reloads once the stream is back;
 * - a non-200 answer (503 at the stream cap, 403) leaves the source CLOSED with no browser retry, so it reopens
 *   itself after 1 s doubling to 30 s, reset once the stream opens, and reports "error" meanwhile;
 * - a tab that is hidden closes the stream; it reopens (and reloads) when visible again.
 */
export function openStream(url: string, h: StreamHandlers): { close(): void } {
  let source: EventSource | null = null;
  let timer: ReturnType<typeof setTimeout> | undefined;
  let last = h.after ?? '';
  let delay = 1000;
  let rotated = false;
  let stopped = false;
  const seen = new Set<string>();

  const connect = () => {
    const es = new EventSource(last ? withAfter(url, last) : url);
    source = es;
    h.onState?.('connecting');
    es.onopen = () => {
      delay = 1000; // a 200 answer is the server accepting the stream, even if it stays quiet
      h.onState?.('connected');
      if (rotated) {
        rotated = false;
        h.onUpdate?.();
      }
    };
    es.addEventListener('update', () => {
      delay = 1000;
      h.onUpdate?.();
    });
    es.addEventListener('log', (e) => {
      delay = 1000;
      const { data, lastEventId: id } = e as MessageEvent<string>;
      if (id) {
        if (seen.has(id)) return;
        if (seen.size >= MAX_SEEN) seen.clear(); // shortcut: a clear can let one replayed line through, which is harmless
        seen.add(id);
        last = id;
      }
      h.onLine?.(data, id);
    });
    es.onerror = () => {
      if (es.readyState !== CLOSED) {
        rotated = true; // the browser reconnects by itself: keep showing "connected"
        return;
      }
      es.close();
      rotated = true; // a tick during the backoff goes nowhere: reload once the stream is back
      h.onState?.('error');
      timer = setTimeout(connect, delay);
      delay = Math.min(delay * 2, 30_000);
    };
  };

  const halt = () => {
    clearTimeout(timer);
    timer = undefined;
    source?.close();
    source = null;
  };

  const visibility = () => {
    if (stopped) return;
    if (document.visibilityState === 'hidden') {
      halt();
      h.onState?.('closed');
    } else if (!source) {
      connect();
      h.onUpdate?.();
    }
  };

  document.addEventListener('visibilitychange', visibility);
  if (document.visibilityState !== 'hidden') connect();
  return {
    close() {
      stopped = true;
      document.removeEventListener('visibilitychange', visibility);
      halt();
      h.onState?.('closed');
    },
  };
}
