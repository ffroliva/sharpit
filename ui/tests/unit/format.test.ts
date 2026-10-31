import { describe, expect, it } from 'vitest';
import { firstSentence, scannedWhen, upgradeHint } from '../../src/lib/format';

describe('upgradeHint', () => {
  // the server sends only fixed versions above the installed one, sorted ascending by PEP 440
  it('names the first (lowest) fixed version the server sends', () => {
    expect(upgradeHint('jinja2', ['3.1.3', '3.1.4'])).toBe('pip install "jinja2>=3.1.3"');
  });
  it.each([
    ['django', '5.1rc1', ['5.1']],
    ['urllib3', '2.0.0a3', ['2.0.0']],
    ['pkg', '1.0', ['1.0.post1']],
  ])('gives a hint for pre-release and post-release fixes: %s %s %s', (pkg, installed, fixed) => {
    expect(upgradeHint(pkg, fixed)).toBe(`pip install "${pkg}>=${fixed[0]}"`);
  });
  it('has nothing to say without a fixed version', () => {
    expect(upgradeHint('pkg', [])).toBeNull();
  });
  // the hint is a shell command the user pastes: OSV strings must not be able to break out of it
  it.each([
    ['evil"; rm -rf ~; "', ['2.0']],
    ['pkg', ['2.0"; touch x; "']],
    ['pkg', ['2.0;id']],
    ['pkg$(id)', ['2.0']],
    ['pkg', ['$(id)']],
  ])('refuses unsafe text: %s %s', (pkg, fixed) => {
    expect(upgradeHint(pkg, fixed)).toBeNull();
  });
  it('accepts the version characters PEP 440 uses', () => {
    expect(upgradeHint('zope.interface', ['1!2.0.post1+local'])).toBe('pip install "zope.interface>=1!2.0.post1+local"');
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
    const at = new Date(2026, 9, 30, 22, 5);
    // the time follows the viewer's locale (12h on CI, 24h elsewhere)
    const time = at.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    expect(scannedWhen(at.getTime(), now)).toBe(`today ${time}`);
  });
  it('gives the date for an older scan', () => {
    expect(scannedWhen(new Date(2026, 9, 28, 9, 0).getTime(), now)).not.toMatch(/^today/);
  });
});
