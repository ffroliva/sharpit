/** The CSS class for an HTTP status: its word always shows beside it, colour is only a hint (DESIGN.md). */
export function statusFamilyClass(status: number | null): 'ok' | 'muted' | 'warn' | 'danger' {
  if (status === null) return 'muted';
  if (status >= 500) return 'danger';
  if (status >= 400) return 'warn';
  return status >= 200 && status < 300 ? 'ok' : 'muted';
}

/**
 * Is this stack frame the application's own code? An exception frame carries the server's verdict; a thread or task
 * line is `module.function (file:line)`, judged by its file the way the server does: installed packages, the standard
 * library and synthetic files (`<frozen ...>`) are not the app.
 */
export function isApplicationFrame(frame: string | { applicationFrame: boolean }): boolean {
  if (typeof frame !== 'string') return frame.applicationFrame;
  const file = /\((.*):\d+\)$/.exec(frame)?.[1];
  if (!file || file.startsWith('<')) return false;
  // shortcut: the standard library is recognised by its usual install layouts, so an unusual prefix reads as app code
  return !/site-packages|dist-packages|[\\/]lib[\\/]python\d|python\d+[\\/]lib[\\/]/i.test(file);
}

/** 24-hour clock time of an epoch-ms or ISO timestamp. */
export const clock = (at: number | string) => new Date(at).toLocaleTimeString([], { hour12: false });
