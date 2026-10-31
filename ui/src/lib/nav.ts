import type { Panel } from './types';

/** The rail's groups (spec 13.1); every panel id is in exactly one. `layout.ts` is the graph layout, not this. */
export const NAV: readonly { title: string; ids: readonly string[] }[] = [
  { title: 'Overview', ids: ['overview', 'activity'] },
  { title: 'Runtime', ids: ['health', 'threads', 'log-tail', 'exceptions', 'http-exchanges', 'http-probe'] },
  { title: 'Database', ids: ['sql-trace', 'database-connection-pools', 'alembic'] },
  { title: 'Configuration', ids: ['config', 'mappings', 'loggers', 'beans', 'mcp-server', 'cli'] },
  { title: 'Advisors', ids: ['rest-api', 'vulnerabilities'] },
];

/** A panel the server lists but has not built yet is not shown at all. */
export const notBuilt = (p: Panel) => !p.available && p.unavailableReason === 'Not built yet';

/** Panels by group, in the spec's order; empty groups drop out, and an id no group knows lands in "Other". */
export function groupPanels(panels: readonly Panel[]): { title: string; panels: Panel[] }[] {
  const shown = panels.filter((p) => !notBuilt(p));
  const known = new Set(NAV.flatMap((g) => g.ids));
  const groups = [
    ...NAV.map((g) => ({ title: g.title, panels: g.ids.flatMap((id) => shown.filter((p) => p.id === id)) })),
    { title: 'Other', panels: shown.filter((p) => !known.has(p.id)) },
  ];
  return groups.filter((g) => g.panels.length > 0);
}
