import { expect, it } from 'vitest';
import { NAV, groupPanels } from '../../src/lib/nav';
import { panel } from '../component/support';

const ALL = [
  'overview', 'activity', 'health', 'threads', 'log-tail', 'exceptions', 'http-exchanges', 'http-probe', 'sql-trace',
  'database-connection-pools', 'alembic', 'config', 'loggers', 'mappings', 'beans', 'mcp-server', 'cli', 'rest-api',
  'vulnerabilities',
];

it('every panel id sits in exactly one group', () => {
  const placed = NAV.flatMap((g) => g.ids);
  expect(new Set(placed).size).toBe(placed.length);
  for (const id of ALL) expect(placed.filter((p) => p === id), id).toHaveLength(1);
});

it('keeps the spec groups in order', () => {
  expect(NAV.map((g) => g.title)).toEqual(['Overview', 'Runtime', 'Database', 'Configuration', 'Advisors']);
  expect(NAV[1]!.ids).toEqual(['health', 'threads', 'log-tail', 'exceptions', 'http-exchanges', 'http-probe']);
});

it('hides a panel that is not built yet, drops empty groups and keeps an unknown id visible', () => {
  const groups = groupPanels([
    panel('overview'),
    panel('threads'),
    panel('health', { available: false, unavailableReason: 'Not built yet' }),
    panel('sql-trace', { available: false, unavailableReason: 'SQLAlchemy is not imported by this application' }),
    panel('mystery'),
  ]);
  expect(groups.map((g) => [g.title, g.panels.map((p) => p.id)])).toEqual([
    ['Overview', ['overview']],
    ['Runtime', ['threads']],
    ['Database', ['sql-trace']],
    ['Other', ['mystery']],
  ]);
});
