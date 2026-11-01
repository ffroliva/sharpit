import { implemented as architecture } from './architecture';
import { implemented as data } from './data';
import { implemented as database_advisor } from './database_advisor';
import { implemented as fastapi } from './fastapi';
import { implemented as fastapi_security } from './fastapi_security';
import { implemented as mysql } from './mysql';
import { implemented as postgresql } from './postgresql';
import { implemented as security } from './security';
import { implemented as security_logs } from './security_logs';
import { implemented as sqlalchemy_statistics } from './sqlalchemy_statistics';
import { implemented as traces } from './traces';
import { implemented as transactions } from './transactions';

export const PANEL_04_IMPLEMENTED = {
  data,
  transactions,
  postgresql,
  mysql,
  traces,
  security,
  'security-logs': security_logs,
  'database-advisor': database_advisor,
  architecture,
  'sqlalchemy-statistics': sqlalchemy_statistics,
  'fastapi-security': fastapi_security,
  fastapi,
} as const;

export const PANEL_04_IDS = Object.keys(PANEL_04_IMPLEMENTED);

export function panelImplemented(id: string): boolean {
  return PANEL_04_IMPLEMENTED[id as keyof typeof PANEL_04_IMPLEMENTED] ?? true;
}
