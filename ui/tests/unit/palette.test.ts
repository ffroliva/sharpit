import { describe, expect, it } from 'vitest';
import { search, type Entry } from '../../src/lib/palette';
import panels from '../../../tests/fixtures/bootui/panels.json';
import loggers from '../../../tests/fixtures/bootui/loggers.json';

const index: Entry[] = [
  ...panels.panels.map((p): Entry => ({ kind: 'panel', id: p.id, label: p.title })),
  ...loggers.loggers.map((l): Entry => ({ kind: 'logger', id: l.name, label: l.name })),
];

describe('search', () => {
  it('ranks an exact prefix above a fuzzy match, even when the fuzzy label sorts first', () => {
    const small: Entry[] = [
      { kind: 'config', id: 'a', label: 'a_long_offset_group' }, // fuzzy "log": l..o..g
      { kind: 'logger', id: 'b', label: 'logging' }, // prefix
    ];
    expect(search(small, 'log').map((h) => h.entry.id)).toEqual(['b', 'a']);
  });

  it('orders exact > prefix > word prefix > substring > fuzzy', () => {
    const tiers: Entry[] = [
      { kind: 'config', id: 'fuzzy', label: 'xdxbx' },
      { kind: 'config', id: 'substring', label: 'xxdbx' },
      { kind: 'config', id: 'word', label: 'app.db_url' },
      { kind: 'config', id: 'prefix', label: 'dbpool' },
      { kind: 'config', id: 'exact', label: 'DB' },
    ];
    expect(search(tiers, 'db').map((h) => h.entry.id)).toEqual(['exact', 'prefix', 'word', 'substring', 'fuzzy']);
  });

  it('is case-insensitive, skips non-matches, and finds panels and loggers in the golden index', () => {
    const hits = search(index, 'LOGG');
    expect(hits[0]!.entry).toEqual({ kind: 'panel', id: 'loggers', label: 'Loggers' });
    expect(hits.every((h) => h.score > 0)).toBe(true);
    expect(search(index, 'zzzz-not-there')).toEqual([]);
  });

  it('caps the result count; an empty query lists the index in order', () => {
    expect(search(index, 'o', 10)).toHaveLength(10);
    expect(search(index, '  ', 3).map((h) => h.entry)).toEqual(index.slice(0, 3));
  });
});
