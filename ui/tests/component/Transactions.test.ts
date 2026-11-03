// @vitest-environment jsdom
import { expect, it } from 'vitest';
import Transactions from '../../src/views/Transactions.svelte';
import { FakeEventSource, harness, json, panel, readOnly, until } from './support';

const report = {
  available: true,
  unavailableReason: null,
  capturing: true,
  bufferSize: 2,
  totalCaptured: 2,
  slowTransactionThresholdMillis: 200,
  connectionHoldThresholdMillis: 500,
  stats: {
    totalTransactions: 2,
    totalDurationMillis: 4,
    maxDurationMillis: 3,
    avgDurationMillis: 2,
    slowTransactions: 0,
    connectionHeldTransactions: 0,
    committedCount: 2,
    rolledBackCount: 0,
    unknownCount: 0,
    nestedCount: 1,
    evicted: 0,
  },
  entries: [
    {
      id: 2, methodName: 'orders:save', propagation: 'PARTICIPATING', isolation: null, status: 'COMMITTED',
      startTimestamp: 1_700_000_000_001, endTimestamp: 1_700_000_000_003, durationMillis: 2, parentId: 1,
      thread: 'MainThread', traceId: null, sqlStatementCount: 0, connectionCount: 1, readOnly: null,
      slow: false, connectionHeld: false, errorMessage: null,
    },
    {
      id: 1, methodName: 'orders:create', propagation: 'NEW', isolation: null, status: 'COMMITTED',
      startTimestamp: 1_700_000_000_000, endTimestamp: 1_700_000_000_003, durationMillis: 3, parentId: null,
      thread: 'MainThread', traceId: null, sqlStatementCount: 1, connectionCount: 1, readOnly: null,
      slow: false, connectionHeld: false, errorMessage: null,
    },
  ],
  warnings: [],
};

const h = harness();

it('renders transactions, indents savepoints, and refreshes on a stream update', async () => {
  h.route((url) => (url === 'api/transactions' ? json(200, report) : undefined));
  h.mount(Transactions, { panel: panel('transactions') });
  await until(() => expect(h.text()).toContain('orders:create'));
  expect(h.text()).toContain('orders:save');
  expect(h.text()).toContain('—');
  expect(h.target.querySelector('tr.child')?.getAttribute('data-parent')).toBe('1');
  const before = h.calls('GET').length;
  FakeEventSource.last.emit('update');
  await until(() => expect(h.calls('GET').length).toBe(before + 1));
});

it('hides transaction controls for a read-only panel', async () => {
  h.route((url) => (url === 'api/transactions' ? json(200, report) : undefined));
  h.mount(Transactions, { panel: readOnly('transactions') });
  await until(() => expect(h.text()).toContain('orders:create'));
  expect([...h.target.querySelectorAll('button')].some((button) => /Pause|Resume|Clear/.test(button.textContent ?? ''))).toBe(false);
});

