import { readable } from 'svelte/store';

/** `#/<panel>?q=<filter>`: hash routing keeps every URL relative to the shell, whatever the mount path. */
export interface Route {
  panel: string;
  q: string;
}

export function parse(hash: string): Route {
  const [path = '', query = ''] = hash.replace(/^#\/?/, '').split('?', 2);
  return { panel: decode(path) || 'overview', q: new URLSearchParams(query).get('q') ?? '' };
}

/** A malformed escape (a lone `%`) is kept as typed instead of throwing out of routing. */
function decode(text: string): string {
  try {
    return decodeURIComponent(text);
  } catch {
    return text;
  }
}

export function href(panel: string, q = ''): string {
  return `#/${encodeURIComponent(panel)}${q ? `?${new URLSearchParams({ q })}` : ''}`;
}

export const route = readable(parse(location.hash), (set) => {
  const update = () => set(parse(location.hash));
  addEventListener('hashchange', update);
  return () => removeEventListener('hashchange', update);
});
