import { describe, expect, it } from 'vitest';
import { ApiError } from '../../src/lib/api';
import {
  describeLoadError,
  formatLoadError,
  isAbortError,
  isServerUnreachableError,
  toErrorMessage,
} from '../../src/lib/loadError';

describe('loadError', () => {
  // ported: loadError.test.js::loadError includes the canonical policy reason, status and request context
  it('includes the canonical policy reason, status and request context', () => {
    const error = new ApiError(403, {
      error: 'sharpit panel access denied',
      panel: 'memory',
      reason: 'sharpit is read-only via SHARPIT_READ_ONLY=true',
    });

    expect(formatLoadError(error, 'Unable to run Memory')).toBe(
      'Unable to run Memory: sharpit is read-only via SHARPIT_READ_ONLY=true (HTTP 403)',
    );
    expect(describeLoadError(error).serverUnreachable).toBe(false);
  });

  // ported: loadError.test.js::loadError does not misclassify policy text containing a network-error phrase
  it('does not misclassify policy text containing a network-error phrase', () => {
    const error = new ApiError(403, {
      error: 'sharpit panel access denied',
      panel: 'memory',
      reason: 'Load failed because Memory is read-only.',
    });
    expect(formatLoadError(error)).toBe('Load failed because Memory is read-only. (HTTP 403)');
    expect(describeLoadError(error).serverUnreachable).toBe(false);
  });

  // ported: loadError.test.js::loadError detects browser fetch failures as server unreachable
  it('detects browser fetch failures as server unreachable', () => {
    expect(isServerUnreachableError(new TypeError('Load failed'))).toBe(true);
    expect(isServerUnreachableError('Could not load beans: Failed to fetch')).toBe(true);
    expect(isServerUnreachableError('HTTP 503')).toBe(false);
  });

  // ported: loadError.test.js::loadError describes network failures with a server-not-running tip
  it('describes network failures with a server-not-running tip', () => {
    const description = describeLoadError(new TypeError('Load failed'), 'Unable to load overview');

    expect(description).toEqual({
      title: 'Server unreachable',
      message:
        'sharpit could not reach the application. The server may have been stopped. Start it again, then retry or refresh this page.',
      serverUnreachable: true,
    });
  });

  // ported: loadError.test.js::loadError keeps HTTP failures specific to the failed request
  it('keeps HTTP failures specific to the failed request', () => {
    expect(formatLoadError(new Error('HTTP 500'), 'Unable to load overview')).toBe('Unable to load overview: HTTP 500');
  });

  // ported: loadError.test.js::loadError formats browser fetch failures with the same backend-down message
  it('formats browser fetch failures with the same backend-down message', () => {
    expect(formatLoadError(new TypeError('Failed to fetch'), 'Unable to load health')).toBe(
      'Server unreachable: sharpit could not reach the application. The server may have been stopped. Start it again, then retry or refresh this page.',
    );
  });

  // ported: loadError.test.js::loadError normalizes non-error values
  it('normalizes non-error values', () => {
    expect(toErrorMessage('Load failed')).toBe('Load failed');
    expect(toErrorMessage(null)).toBe('Request failed');
  });

  // ported: loadError.test.js::loadError recognizes abort errors without requiring DOMException support
  it('recognizes abort errors without requiring DOMException support', () => {
    expect(isAbortError({ name: 'AbortError' })).toBe(true);
    expect(isAbortError(new Error('request failed'))).toBe(false);
    expect(isAbortError(null)).toBe(false);
  });
});
