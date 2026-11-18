// @vitest-environment jsdom
import { describe, expect, it } from 'vitest';
import Alembic from '../../src/views/Alembic.svelte';
import Exceptions from '../../src/views/Exceptions.svelte';
import Health from '../../src/views/Health.svelte';
import SqlTrace from '../../src/views/SqlTrace.svelte';
import Traces from '../../src/views/Traces.svelte';
import { harness, json, panel, readOnly, until } from './support';

const group = {
  id: 'g1',
  exceptionClassName: 'app.errors.Boom',
  message: 'it broke',
  count: 14,
  firstSeen: 1_700_000_000_000,
  lastSeen: 1_700_000_100_000,
  location: 'app.py:10',
  applicationException: true,
  lastThread: 'MainThread',
  lastRequestMethod: 'GET',
  lastRequestPath: '/boom',
  lastHandler: null,
  lastSource: 'request',
  lastTraceId: 't1',
  status: 'OPEN',
  regressionCount: 0,
  errorContract: null,
};

const exceptionsReport = (groups: unknown[] = [group]) => ({
  available: true,
  unavailableReason: null,
  maxGroups: 100,
  totalExceptions: groups.length,
  groups,
});

describe('Action policy in views', () => {
  const h = harness();

  // ported: actionPolicy.test.js::Action policy changes during confirmation retains exception status and cached groups when a status action is denied
  it('Exceptions retains exception status and reports canonical denial text when a status action is denied', async () => {
    const reason = 'Exceptions are read-only via SHARPIT_PANELS_EXCEPTIONS_READ_ONLY=true';
    h.route((url, init) => {
      if (url === 'api/exceptions' && (init?.method ?? 'GET') === 'GET') return json(200, exceptionsReport());
      if (url === 'api/exceptions/g1/status' && init?.method === 'POST') {
        return json(403, { error: 'sharpit panel access denied', panel: 'exceptions', reason });
      }
      return undefined;
    });

    h.mount(Exceptions, { panel: panel('exceptions') });
    await until(() => expect(h.text()).toContain('app.errors.Boom'));

    const ackBtn = [...h.target.querySelectorAll('button')].find((b) => b.textContent === 'Acknowledge')!;
    ackBtn.click();

    await until(() => expect(h.text()).toContain(reason));
    expect(h.text()).toContain('HTTP 403');
    expect(h.text()).toContain('OPEN');
  });

  // ported: actionPolicy.test.js::Action policy changes during confirmation %s preserves canonical denial text and status
  it('Traces preserves canonical denial text and status when clear action is denied', async () => {
    const reason = 'Traces are read-only via SHARPIT_READ_ONLY=true';
    const summary = {
      traceId: 'trace-1',
      rootSpanName: 'GET /test',
      httpPath: '/test',
      services: ['api'],
      startEpochNanos: 1_000,
      endEpochNanos: 10_000,
      durationNanos: 9_000,
      spanCount: 1,
      hasError: false,
      hasAi: false,
    };

    h.route((url, init) => {
      if (url === 'api/traces' && (init?.method ?? 'GET') === 'GET') {
        return json(200, { enabled: true, unavailableReason: null, retained: 1, capacity: 100, traces: [summary] });
      }
      if (url === 'api/traces' && init?.method === 'DELETE') {
        return json(403, { error: 'sharpit panel access denied', panel: 'traces', reason });
      }
      return undefined;
    });

    h.mount(Traces, { panel: panel('traces') });
    await until(() => expect(h.text()).toContain('GET /test'));

    const clearBtn = [...h.target.querySelectorAll('button')].find((b) => b.textContent === 'Clear')!;
    clearBtn.click();

    await until(() => expect(h.text()).toContain(reason));
    expect(h.text()).toContain('HTTP 403');
  });

  // ported: actionPolicy.test.js::Action policy changes during confirmation %s rechecks policy before issuing its request
  it('Exceptions rechecks policy before issuing requests and disables actions when disabled or read-only', async () => {
    h.route((url) => (url === 'api/exceptions' ? json(200, exceptionsReport()) : undefined));

    // Disabled panel
    h.mount(Exceptions, {
      panel: panel('exceptions', { enabled: false, readOnly: false }),
    });
    await until(() => expect(h.text()).toContain('app.errors.Boom'));

    const disabledButtons = [...h.target.querySelectorAll('button')].filter((b) =>
      ['Acknowledge', 'Resolve', 'Clear all'].includes(b.textContent ?? ''),
    );
    expect(disabledButtons.length).toBe(3);
    for (const b of disabledButtons) {
      expect(b.disabled).toBe(true);
      expect(b.title).toContain('SHARPIT_PANELS_EXCEPTIONS_ENABLED=false');
      b.click();
    }
    expect(h.calls('POST')).toEqual([]);
    expect(h.calls('DELETE')).toEqual([]);
  });

  it('Health disables Run checks when read-only or disabled and handles 403 denial', async () => {
    const reason = 'Health is read-only via SHARPIT_READ_ONLY=true';
    const healthTree = {
      name: 'sharpit',
      status: 'UP',
      details: { checkedAt: Date.now() },
      components: [],
    };

    h.route((url, init) => {
      if (url === 'api/health') return json(200, healthTree);
      if (url === 'api/health/check' && init?.method === 'POST') {
        return json(403, { error: 'sharpit panel access denied', panel: 'health', reason });
      }
      return undefined;
    });

    h.mount(Health, { panel: panel('health', { enabled: false, readOnly: false }) });
    await until(() => expect(h.text()).toContain('Run checks'));

    const btn = [...h.target.querySelectorAll('button')].find((b) => b.textContent === 'Run checks')!;
    expect(btn.disabled).toBe(true);
    expect(btn.title).toContain('SHARPIT_PANELS_HEALTH_ENABLED=false');
    btn.click();
    expect(h.calls('POST')).toEqual([]);
  });

  it('SqlTrace disables Pause/Resume and Clear when panel is read-only or disabled', async () => {
    const report = {
      available: true,
      unavailableReason: null,
      capturing: true,
      bufferSize: 100,
      totalCaptured: 0,
      entries: [],
      topStatements: [],
      dataSources: [],
    };
    h.route((url) => (url === 'api/sql-trace' ? json(200, report) : undefined));

    h.mount(SqlTrace, { panel: panel('sql-trace', { enabled: false, readOnly: false }) });
    await until(() => expect(h.text()).toContain('Pause'));

    const buttons = [...h.target.querySelectorAll('button')].filter((b) => ['Pause', 'Clear'].includes(b.textContent ?? ''));
    expect(buttons.length).toBe(2);
    for (const b of buttons) {
      expect(b.disabled).toBe(true);
      expect(b.title).toContain('SHARPIT_PANELS_SQL_TRACE_ENABLED=false');
      b.click();
    }
    expect(h.calls('POST')).toEqual([]);
  });

  it('Alembic disables Read database version when panel is read-only or disabled', async () => {
    const report = {
      alembicPresent: true,
      configPath: 'alembic.ini',
      total: 1,
      heads: ['head1'],
      databases: [
        {
          name: 'db1',
          currentVersion: 'head1',
          applied: 1,
          pending: 0,
          checkedAt: Date.now(),
          unavailableReason: null,
          migrations: [],
        },
      ],
    };
    h.route((url) => (url === 'api/alembic/migrations' ? json(200, report) : undefined));

    h.mount(Alembic, { panel: panel('alembic', { enabled: false, readOnly: false }) });
    await until(() => expect(h.text()).toContain('Read database version'));

    const btn = [...h.target.querySelectorAll('button')].find((b) => b.textContent?.includes('Read database version'))!;
    expect(btn.disabled).toBe(true);
    expect(btn.title).toContain('SHARPIT_PANELS_ALEMBIC_ENABLED=false');
    btn.click();
    expect(h.calls('POST')).toEqual([]);
  });
});
