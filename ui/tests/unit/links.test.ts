import { describe, expect, it } from 'vitest';
import { linkable } from '../../src/lib/links';

describe('linkable', () => {
  it('accepts app-relative and http(s) URLs', () => {
    for (const url of ['/docs', '/', 'https://example.com/openapi.json', 'HTTP://example.com']) {
      expect(linkable(url), url).toBe(true);
    }
  });
  it('refuses protocol-relative and script URLs', () => {
    for (const url of ['//evil.example/x', '/\\evil.example/x', 'javascript:alert(1)', 'data:text/html,x', 'docs']) {
      expect(linkable(url), url).toBe(false);
    }
  });
  it('refuses URLs that tab, CR or LF turn protocol-relative (browsers drop them while parsing)', () => {
    for (const url of ['/\t/evil.example', '/\n/evil.example', '/\r\\evil.example', '/\r\n/evil.example']) {
      expect(linkable(url), JSON.stringify(url)).toBe(false);
    }
  });
});
