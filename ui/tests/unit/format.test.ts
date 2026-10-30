import { describe, expect, it } from 'vitest';
import { firstSentence, scannedWhen, upgradeHint } from '../../src/lib/format';

describe('upgradeHint', () => {
  it('names the lowest fixed version above the installed one', () => {
    expect(upgradeHint('jinja2', '3.1.2', ['2.11.3', '3.1.3', '3.1.4'])).toBe('pip install "jinja2>=3.1.3"');
  });
  it('compares numerically, not as text', () => {
    expect(upgradeHint('pkg', '1.9.0', ['1.10.0'])).toBe('pip install "pkg>=1.10.0"');
  });
  it('has nothing to say without a fixed version', () => {
    expect(upgradeHint('pkg', '1.0', [])).toBeNull();
  });
});

describe('firstSentence', () => {
  it('keeps the text up to the first full stop', () => {
    expect(firstSentence('Return stable identity. Use this first.')).toBe('Return stable identity.');
  });
  it('keeps a text that has a single sentence', () => {
    expect(firstSentence('List loggers')).toBe('List loggers');
  });
  it('does not stop at a dot inside a name', () => {
    expect(firstSentence('Reads `sharpit.mcp.enabled` values. More.')).toBe('Reads `sharpit.mcp.enabled` values.');
  });
});

describe('scannedWhen', () => {
  const now = new Date(2026, 9, 30, 23, 0).getTime();
  it('says today for a scan from today', () => {
    expect(scannedWhen(new Date(2026, 9, 30, 22, 5).getTime(), now)).toMatch(/^today 22.05/);
  });
  it('gives the date for an older scan', () => {
    expect(scannedWhen(new Date(2026, 9, 28, 9, 0).getTime(), now)).not.toMatch(/^today/);
  });
});
