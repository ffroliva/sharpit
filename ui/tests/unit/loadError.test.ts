import { describe, expect, it } from 'vitest';
import { ApiError } from '../../src/lib/api';
import { describeLoadError } from '../../src/lib/loadError';

describe('loadError', () => {
  it('keeps policy failures specific and does not classify their text as network failure', () => {
    const error = new ApiError(403, {
      error: 'sharpit panel access denied',
      panel: 'memory',
      reason: 'Load failed because Memory is read-only.',
    });
    expect(describeLoadError(error)).toBe('Load failed because Memory is read-only. (HTTP 403)');
  });

  it('describes browser fetch failures with a server-not-running tip', () => {
    expect(describeLoadError(new TypeError('Load failed'))).toBe(
      'sharpit could not reach the application. The server may have been stopped. Start it again, then retry or refresh this page.',
    );
  });

  it('keeps HTTP failures specific to the failed request', () => {
    expect(describeLoadError(new Error('HTTP 500'))).toBe('HTTP 500');
  });

  it('normalizes string and empty error values', () => {
    expect(describeLoadError('A local error')).toBe('A local error');
    expect(describeLoadError(null)).toBe('Request failed');
  });
});
