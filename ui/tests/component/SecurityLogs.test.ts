// @vitest-environment jsdom
import { expect, it } from 'vitest';
import SecurityLogs from '../../src/views/SecurityLogs.svelte';
import { FakeEventSource, harness, json, panel, until } from './support';

const report = {
  auditEventsPresent: true,
  unavailableReason: null,
  maxLogs: 500,
  typeSummaries: [
    { type: 'AUTHENTICATION_FAILURE', count: 2 },
    { type: 'AUTHENTICATION_SUCCESS', count: 1 },
  ],
  events: [
    {
      timestamp: '2026-11-01T10:15:30.120Z', principal: 'alice', type: 'AUTHENTICATION_FAILURE',
      data: [
        { name: 'details', value: '******', masked: true, truncated: false },
        { name: 'type', value: 'BadCredentialsException', masked: false, truncated: false },
      ],
      traceId: 'r-42', requestId: 'r-42',
    },
  ],
  page: { total: 3, matched: 3, offset: 0, limit: 200, returned: 1, hasMore: false },
};

const h = harness();

it('renders type summaries, the masked badge, and refetches on a stream update', async () => {
  h.route((url) => (url.startsWith('api/security-logs') ? json(200, report) : undefined));
  h.mount(SecurityLogs, { panel: panel('security-logs') });
  await until(() => expect(h.text()).toContain('BadCredentialsException'));
  expect(h.text()).toContain('AUTHENTICATION_FAILURE · 2');
  expect(h.text()).toContain('masked');
  expect(h.text()).toContain('r-42');
  const before = h.calls('GET').length;
  FakeEventSource.last.emit('update');
  await until(() => expect(h.calls('GET')).toHaveLength(before + 1));
});

it('filters by a type summary', async () => {
  h.route((url) => (url.startsWith('api/security-logs') ? json(200, report) : undefined));
  h.mount(SecurityLogs, { panel: panel('security-logs') });
  await until(() => expect(h.text()).toContain('AUTHENTICATION_SUCCESS · 1'));
  const chip = [...h.target.querySelectorAll('button')].find((b) => b.textContent?.startsWith('AUTHENTICATION_SUCCESS'));
  chip?.click();
  await until(() => expect(h.calls('GET').some((u) => u.includes('type=AUTHENTICATION_SUCCESS'))).toBe(true));
});

it('shows the unavailable reason', async () => {
  const unavailable = { ...report, auditEventsPresent: false, unavailableReason: 'Request capture is unavailable', events: [], typeSummaries: [] };
  h.route((url) => (url.startsWith('api/security-logs') ? json(200, unavailable) : undefined));
  h.mount(SecurityLogs, { panel: panel('security-logs') });
  await until(() => expect(h.text()).toContain('Request capture is unavailable'));
});
