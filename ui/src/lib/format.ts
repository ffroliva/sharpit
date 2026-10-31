const SAFE_NAME = /^[A-Za-z0-9._-]+$/;
const SAFE_VERSION = /^[A-Za-z0-9._!+-]+$/;

/**
 * The pip command that reaches the lowest fixed version, or null when there is none. The server sends only versions
 * above the installed one, sorted by PEP 440, so the first is the target. The command is pasted into a shell and its
 * parts come from OSV, so anything outside package-name and version characters gives null.
 */
export function upgradeHint(pkg: string, fixed: readonly string[]): string | null {
  const target = fixed[0];
  return SAFE_NAME.test(pkg) && target && SAFE_VERSION.test(target) ? `pip install "${pkg}>=${target}"` : null;
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
