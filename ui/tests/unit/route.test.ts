// @vitest-environment jsdom
import { describe, expect, it } from 'vitest';
import { href, parse } from '../../src/lib/route';

describe('parse', () => {
  it('reads the panel and the filter', () => {
    expect(parse('#/loggers?q=app.db')).toEqual({ panel: 'loggers', q: 'app.db' });
  });
  it('round-trips href', () => {
    expect(parse(href('a b', 'x&y'))).toEqual({ panel: 'a b', q: 'x&y' });
  });
  it('falls back to the raw text for a malformed escape instead of throwing', () => {
    expect(parse('#/%E0%A4%A?q=x')).toEqual({ panel: '%E0%A4%A', q: 'x' });
    expect(parse('#/%')).toEqual({ panel: '%', q: '' });
  });
});
