/** Something the Ctrl/Cmd+K palette can jump to. */
export interface Entry {
  kind: 'panel' | 'logger' | 'config';
  id: string;
  label: string;
}

export interface Hit {
  entry: Entry;
  score: number;
}

// Match tiers, best first. Fuzzy (in-order subsequence) scores below every contiguous match.
const EXACT = 5;
const PREFIX = 4;
const WORD_PREFIX = 3;
const SUBSTRING = 2;
const FUZZY = 1;

/** Case-insensitive ranked search over `label`; a blank query lists the index in order. */
export function search(index: readonly Entry[], query: string, limit = 50): Hit[] {
  const q = query.trim().toLowerCase();
  if (!q) return index.slice(0, limit).map((entry) => ({ entry, score: 0 }));
  // a word starts after a separator common in logger names, config keys and titles
  const wordStart = new RegExp(`[\\s._\\-/:]${q.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}`);
  const hits: Hit[] = [];
  for (const entry of index) {
    const score = scoreOf(entry.label.toLowerCase(), q, wordStart);
    if (score > 0) hits.push({ entry, score });
  }
  hits.sort((a, b) => b.score - a.score || a.entry.label.length - b.entry.label.length || byCodeUnit(a.entry.label, b.entry.label));
  return hits.slice(0, limit);
}

// the same order in every browser locale
const byCodeUnit = (a: string, b: string) => (a < b ? -1 : a > b ? 1 : 0);

function scoreOf(label: string, q: string, wordStart: RegExp): number {
  if (label === q) return EXACT;
  if (label.startsWith(q)) return PREFIX;
  if (wordStart.test(label)) return WORD_PREFIX;
  if (label.includes(q)) return SUBSTRING;
  return isSubsequence(label, q) ? FUZZY : 0;
}

function isSubsequence(label: string, q: string): boolean {
  let i = 0;
  for (const ch of label) if (ch === q[i]) i++;
  return i === q.length;
}
