// @vitest-environment jsdom
import { flushSync } from 'svelte';
import { describe, expect, it } from 'vitest';
import Alembic from '../../src/views/Alembic.svelte';
import Config from '../../src/views/Config.svelte';
import Exceptions from '../../src/views/Exceptions.svelte';
import Health from '../../src/views/Health.svelte';
import HttpProbe from '../../src/views/HttpProbe.svelte';
import MySql from '../../src/views/MySql.svelte';
import PostgreSql from '../../src/views/PostgreSql.svelte';
import SqlTrace from '../../src/views/SqlTrace.svelte';
import Traces from '../../src/views/Traces.svelte';
import Transactions from '../../src/views/Transactions.svelte';
import PolicyPropWrapper from './PolicyPropWrapper.svelte';
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

  it('Exceptions handler guard halts execution when panel is read-only and buttons are disabled', async () => {
    h.route((url) => (url === 'api/exceptions' ? json(200, exceptionsReport()) : undefined));

    const view = h.mount<{ act: (fn: () => Promise<unknown>) => Promise<void> }>(Exceptions, {
      panel: readOnly('exceptions'),
    });
    await until(() => expect(h.text()).toContain('app.errors.Boom'));

    const disabledButtons = [...h.target.querySelectorAll('button')].filter((b) =>
      ['Acknowledge', 'Resolve', 'Clear all'].includes(b.textContent ?? ''),
    );
    expect(disabledButtons).toHaveLength(3);
    for (const b of disabledButtons) {
      expect(b.disabled).toBe(true);
      expect(b.title).toContain('SHARPIT_READ_ONLY=true');
    }

    // Call the handler directly to test the guard
    await view.act(async () => fetch('api/exceptions', { method: 'DELETE' }));
    expect(h.calls('DELETE')).toEqual([]);
  });

  it('Traces handler guard halts execution when panel is read-only', async () => {
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
    h.route((url) =>
      url === 'api/traces'
        ? json(200, { enabled: true, unavailableReason: null, retained: 1, capacity: 100, traces: [summary] })
        : undefined,
    );

    const view = h.mount<{ clear: () => Promise<void> }>(Traces, { panel: readOnly('traces') });
    await until(() => expect(h.text()).toContain('GET /test'));

    const clearBtn = [...h.target.querySelectorAll('button')].find((b) => b.textContent === 'Clear')!;
    expect(clearBtn.disabled).toBe(true);
    expect(clearBtn.title).toContain('SHARPIT_READ_ONLY=true');

    await view.clear();
    expect(h.calls('DELETE')).toEqual([]);
  });

  it('HttpProbe handler guard halts execution when panel is read-only', async () => {
    h.route((url) => (url.startsWith('api/mappings') ? json(200, { items: [], total: 0 }) : undefined));

    const view = h.mount<{ send: () => Promise<void> }>(HttpProbe, {
      panel: readOnly('http-probe'),
      q: 'GET /test',
    });

    const sendBtn = [...h.target.querySelectorAll('button')].find((b) => b.textContent === 'Send')!;
    expect(sendBtn.disabled).toBe(true);
    expect(sendBtn.title).toContain('SHARPIT_READ_ONLY=true');

    await view.send();
    expect(h.calls('POST')).toEqual([]);
  });

  it('re-evaluates action policy when the panel prop changes', async () => {
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
    h.route((url) =>
      url === 'api/traces'
        ? json(200, { enabled: true, unavailableReason: null, retained: 1, capacity: 100, traces: [summary] })
        : undefined,
    );

    const wrapper = h.mount<{ updatePanel: (p: unknown) => void }>(PolicyPropWrapper);
    await until(() => expect(h.text()).toContain('GET /test'));

    const clearBtn = [...h.target.querySelectorAll('button')].find((b) => b.textContent === 'Clear')!;
    expect(clearBtn.disabled).toBe(false);

    wrapper.updatePanel(readOnly('traces'));
    flushSync();

    expect(clearBtn.disabled).toBe(true);
    expect(clearBtn.title).toContain('SHARPIT_READ_ONLY=true');
  });

  it('Health disables Run checks when read-only', async () => {
    const healthTree = {
      name: 'sharpit',
      status: 'UP',
      details: { checkedAt: Date.now() },
      components: [],
    };

    h.route((url) => (url === 'api/health' ? json(200, healthTree) : undefined));

    h.mount(Health, { panel: readOnly('health') });
    await until(() => expect(h.text()).toContain('Run checks'));

    const btn = [...h.target.querySelectorAll('button')].find((b) => b.textContent === 'Run checks')!;
    expect(btn.disabled).toBe(true);
    expect(btn.title).toContain('SHARPIT_READ_ONLY=true');
  });

  it('SqlTrace disables Pause/Resume and Clear when panel is read-only', async () => {
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

    h.mount(SqlTrace, { panel: readOnly('sql-trace') });
    await until(() => expect(h.text()).toContain('Pause'));

    const buttons = [...h.target.querySelectorAll('button')].filter((b) => ['Pause', 'Clear'].includes(b.textContent ?? ''));
    expect(buttons).toHaveLength(2);
    for (const b of buttons) {
      expect(b.disabled).toBe(true);
      expect(b.title).toContain('SHARPIT_READ_ONLY=true');
    }
  });

  it('Alembic disables Read database version when panel is read-only', async () => {
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

    h.mount(Alembic, { panel: readOnly('alembic') });
    await until(() => expect(h.text()).toContain('Read database version'));

    const btn = [...h.target.querySelectorAll('button')].find((b) => b.textContent?.includes('Read database version'))!;
    expect(btn.disabled).toBe(true);
    expect(btn.title).toContain('SHARPIT_READ_ONLY=true');
  });

  it('Transactions disables Pause/Resume and Clear when panel is read-only', async () => {
    const report = {
      available: true,
      unavailableReason: null,
      capturing: true,
      bufferSize: 100,
      totalCaptured: 0,
      entries: [],
    };
    h.route((url) => (url === 'api/transactions' ? json(200, report) : undefined));

    h.mount(Transactions, { panel: readOnly('transactions') });
    await until(() => expect(h.text()).toContain('Pause'));

    const buttons = [...h.target.querySelectorAll('button')].filter((b) => ['Pause', 'Clear'].includes(b.textContent ?? ''));
    expect(buttons).toHaveLength(2);
    for (const b of buttons) {
      expect(b.disabled).toBe(true);
      expect(b.title).toContain('SHARPIT_READ_ONLY=true');
    }
  });

  it('MySql disables Read MySQL when panel is read-only', async () => {
    const report = {
      status: 'AVAILABLE',
      dataSources: [],
      readAt: Date.now(),
      disclaimer: 'test',
      message: null,
      limitations: [],
      diagnostics: [],
    };
    h.route((url) => (url === 'api/mysql' ? json(200, report) : undefined));

    h.mount(MySql, { panel: readOnly('mysql') });
    await until(() => expect(h.text()).toContain('Read MySQL'));

    const btn = [...h.target.querySelectorAll('button')].find((b) => b.textContent?.includes('Read MySQL'))!;
    expect(btn.disabled).toBe(true);
    expect(btn.title).toContain('SHARPIT_READ_ONLY=true');
  });

  it('PostgreSql disables Read PostgreSQL when panel is read-only', async () => {
    const report = {
      status: 'AVAILABLE',
      dataSources: [],
      readAt: Date.now(),
      disclaimer: 'test',
      message: null,
      limitations: [],
      diagnostics: [],
    };
    h.route((url) => (url === 'api/postgresql' ? json(200, report) : undefined));

    h.mount(PostgreSql, { panel: readOnly('postgresql') });
    await until(() => expect(h.text()).toContain('Read PostgreSQL'));

    const btn = [...h.target.querySelectorAll('button')].find((b) => b.textContent?.includes('Read PostgreSQL'))!;
    expect(btn.disabled).toBe(true);
    expect(btn.title).toContain('SHARPIT_READ_ONLY=true');
  });

  it('ServerTable displays canonical panel-access reason on 403 load error', async () => {
    const reason = 'Config is read-only via SHARPIT_PANELS_CONFIG_READ_ONLY=true';
    h.route((url) => {
      if (url.startsWith('api/config')) {
        return json(403, { error: 'sharpit panel access denied', panel: 'config', reason });
      }
      return undefined;
    });

    h.mount(Config);

    await until(() => expect(h.text()).toContain(reason));
    expect(h.text()).toContain('HTTP 403');
  });
});
