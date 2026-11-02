import { expect, it } from 'vitest';
import { NAV, groupPanels } from '../../src/lib/nav';
import { PANEL_04_IDS as ALL_PANEL_04_IDS, PANEL_04_IMPLEMENTED as ALL_PANEL_04_IMPLEMENTED } from '../../src/lib/panels04';
import { panel } from '../component/support';

const PANEL_04_IDS = ALL_PANEL_04_IDS.filter((id) => !ALL_PANEL_04_IMPLEMENTED[id as keyof typeof ALL_PANEL_04_IMPLEMENTED]);
const PANEL_04_IMPLEMENTED = Object.fromEntries(PANEL_04_IDS.map((id) => [id, false]));

const ALL = [
  'overview', 'activity', 'health', 'threads', 'log-tail', 'exceptions', 'http-exchanges', 'http-probe', 'sql-trace',
  'database-connection-pools', 'alembic', 'config', 'loggers', 'mappings', 'beans', 'mcp-server', 'cli', 'rest-api',
  'vulnerabilities',
  'data', 'transactions', 'postgresql', 'mysql', 'traces', 'security', 'security-logs', 'database-advisor',
  'architecture', 'sqlalchemy-statistics', 'fastapi-security', 'fastapi',
];

it('every panel id sits in exactly one group', () => {
  const placed = NAV.flatMap((g) => g.ids);
  expect(new Set(placed).size).toBe(placed.length);
  for (const id of ALL) expect(placed.filter((p) => p === id), id).toHaveLength(1);
});

it('keeps the spec groups in order', () => {
  expect(NAV.map((g) => g.title)).toEqual(['Overview', 'Runtime', 'Database', 'Configuration', 'Advisors']);
  expect(NAV[1]!.ids).toEqual([
    'health', 'threads', 'log-tail', 'exceptions', 'http-exchanges', 'http-probe', 'traces', 'security-logs',
  ]);
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

it('keeps every 0.4 panel unimplemented and out of navigation', () => {
  expect(Object.values(PANEL_04_IMPLEMENTED)).toEqual(PANEL_04_IDS.map(() => false));
  const groups = groupPanels(PANEL_04_IDS.map((id) => panel(id)));
  const shown = groups.flatMap((group) => group.panels.map((item) => item.id));
  expect(shown.every((id) => !PANEL_04_IDS.includes(id))).toBe(true);
});

it('keeps all 12 O4 panel implementation flags registered', () => {
  expect(ALL_PANEL_04_IDS).toEqual([
    'data',
    'transactions',
    'postgresql',
    'mysql',
    'traces',
    'security',
    'security-logs',
    'database-advisor',
    'architecture',
    'sqlalchemy-statistics',
    'fastapi-security',
    'fastapi',
  ]);
  expect(Object.keys(ALL_PANEL_04_IMPLEMENTED)).toEqual(ALL_PANEL_04_IDS);
});
