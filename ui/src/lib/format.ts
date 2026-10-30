/** Numeric parts of a version, for ordering: `1.10.0` > `1.9.0`; a pre-release tail such as `rc1` is ignored. */
const parts = (v: string) => v.split(/[.+-]/).map((p) => parseInt(p, 10) || 0);

function compare(a: string, b: string): number {
  const [x, y] = [parts(a), parts(b)];
  for (let i = 0; i < Math.max(x.length, y.length); i++) {
    const d = (x[i] ?? 0) - (y[i] ?? 0);
    if (d) return d;
  }
  return 0;
}

const SAFE_NAME = /^[A-Za-z0-9._-]+$/;
const SAFE_VERSION = /^[A-Za-z0-9._!+-]+$/;

/**
 * The pip command that reaches the lowest fixed version above `installed`, or null when there is none. The command is
 * pasted into a shell and its parts come from OSV, so anything outside package-name and version characters gives null.
 */
export function upgradeHint(pkg: string, installed: string, fixed: readonly string[]): string | null {
  if (!SAFE_NAME.test(pkg)) return null;
  const target = [...fixed].sort(compare).find((v) => compare(v, installed) > 0);
  return target && SAFE_VERSION.test(target) ? `pip install "${pkg}>=${target}"` : null;
}

/** Up to the first full stop that ends a sentence (followed by a space or the end), not one inside a dotted name. */
export function firstSentence(text: string): string {
  const end = text.search(/\.(\s|$)/);
  return end < 0 ? text : text.slice(0, end + 1);
}

/** "today 22:05" for a scan from today, otherwise the date and time. */
export function scannedWhen(ms: number, now = Date.now()): string {
  const at = new Date(ms);
  const time = at.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  return at.toDateString() === new Date(now).toDateString()
    ? `today ${time}`
    : at.toLocaleString([], { dateStyle: 'medium', timeStyle: 'short' });
}
