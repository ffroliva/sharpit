import { errorText } from './api';

/**
 * A view's data with loading and error state; a slow answer to an old `reload` never overwrites a newer one.
 * Nothing loads until `reload` is called: a view calls it inside an `$effect`, which then re-runs it when the
 * filters the fetcher reads change.
 */
export function loader<T>(fetcher: () => Promise<T>) {
  let data = $state<T | null>(null);
  let error = $state<string | null>(null);
  let loading = $state(true);
  let seq = 0;
  async function reload() {
    const mine = ++seq;
    try {
      const next = await fetcher();
      if (mine === seq) {
        data = next;
        error = null;
      }
    } catch (e) {
      if (mine === seq) error = errorText(e);
    } finally {
      if (mine === seq) loading = false;
    }
  }
  return {
    get data() { return data; },
    get error() { return error; },
    get loading() { return loading; },
    reload,
  };
}
