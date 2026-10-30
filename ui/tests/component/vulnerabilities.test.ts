// @vitest-environment jsdom
import { flushSync, mount, unmount } from 'svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import Vulnerabilities from '../../src/views/Vulnerabilities.svelte';
import type { Panel, VulnReport } from '../../src/lib/types';
import golden from '../../../tests/fixtures/bootui/vulnerabilities.json';

const fetchMock = vi.fn<typeof fetch>();
const panel: Panel = {
  id: 'vulnerabilities', title: 'Vulnerabilities', available: true, unavailableReason: null,
  enabled: true, readOnly: false, readOnlyReason: null,
};

function json(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), { status, headers: { 'content-type': 'application/json' } });
}

const inventory = (): VulnReport => {
  const r = structuredClone(golden) as unknown as VulnReport;
  r.scan = { ...r.scan, status: 'NOT_SCANNED', scannedAt: null };
  return r;
};

function scanned(dismissed = false): VulnReport {
  const r = inventory();
  r.scan = { ...r.scan, status: 'SCANNED', message: 'Scan completed against OSV.dev.', scannedAt: 1761811200000 };
  r.vulnerable = dismissed ? 0 : 1;
  r.dependencies = [
    {
      packageName: 'jinja2', version: '3.1.2', vulnerabilityCount: dismissed ? 0 : 1, highestSeverity: dismissed ? 'NONE' : 'HIGH',
      vulnerabilities: [
        { id: 'GHSA-h5c8-rqwp-cp95', summary: 'Jinja sandbox breakout', severity: 'HIGH', score: 8.8, aliases: [],
          references: [], fixedVersions: ['3.1.3'], fixAvailable: true, dismissed },
      ],
    },
  ];
  return r;
}

let target: HTMLElement;
let component: ReturnType<typeof mount> | null = null;

function render(p: Panel = panel) {
  component = mount(Vulnerabilities, { target, props: { panel: p } });
  flushSync();
}
const phase = () => target.querySelector('[data-phase]')?.getAttribute('data-phase');
const button = (name: RegExp) => [...target.querySelectorAll('button')].find((b) => name.test(b.textContent ?? ''))!;
const until = (fn: () => void) => vi.waitFor(fn, { timeout: 1000, interval: 5 });

beforeEach(() => {
  fetchMock.mockReset();
  vi.stubGlobal('fetch', fetchMock);
  target = document.createElement('div');
  document.body.append(target);
});
afterEach(() => {
  if (component) unmount(component);
  component = null;
  target.remove();
  vi.unstubAllGlobals();
});

describe('Vulnerabilities state machine', () => {
  it('loading, then never-scanned when scannedAt is null; nothing is scanned on render', async () => {
    fetchMock.mockResolvedValue(json(200, inventory()));
    render();
    expect(phase()).toBe('loading');
    await until(() => expect(phase()).toBe('never-scanned'));
    expect(target.textContent).toContain('Not scanned yet');
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(fetchMock.mock.calls[0]![0]).toBe('api/vulnerabilities');
    expect(button(/Scan with OSV.dev/).disabled).toBe(false);
  });

  it('scanning while the POST is in flight, then results', async () => {
    let finish!: (r: Response) => void;
    fetchMock
      .mockResolvedValueOnce(json(200, inventory()))
      .mockReturnValueOnce(new Promise<Response>((resolve) => (finish = resolve)));
    render();
    await until(() => expect(phase()).toBe('never-scanned'));
    button(/Scan/).click();
    await until(() => expect(phase()).toBe('scanning'));
    const [url, init] = fetchMock.mock.calls[1]!;
    expect(url).toBe('api/vulnerabilities/scan');
    expect(init?.method).toBe('POST');
    expect(button(/Scanning/).disabled).toBe(true);
    finish(json(200, scanned()));
    await until(() => expect(phase()).toBe('results'));
    expect(target.textContent).toContain('GHSA-h5c8-rqwp-cp95');
    expect(target.textContent).toContain('HIGH');
    expect(button(/Dismiss/)).toBeTruthy();
  });

  it('busy (409) shows the server text next to the button and keeps the previous state', async () => {
    fetchMock
      .mockResolvedValueOnce(json(200, inventory()))
      .mockResolvedValueOnce(json(409, {
        error: 'sharpit action already in progress', operation: 'vulnerability-scan',
        activeOperation: 'vulnerability-scan', message: "Operation 'vulnerability-scan' cannot start while 'vulnerability-scan' is in progress.",
      }));
    render();
    await until(() => expect(phase()).toBe('never-scanned'));
    button(/Scan/).click();
    await until(() =>
      expect(target.querySelector('[role="status"]')?.textContent).toBe(
        "Operation 'vulnerability-scan' cannot start while 'vulnerability-scan' is in progress.",
      ),
    );
    expect(phase()).toBe('never-scanned');
    expect(button(/Scan/).disabled).toBe(false);
  });

  it('failed when the POST errors', async () => {
    fetchMock.mockResolvedValueOnce(json(200, inventory())).mockResolvedValueOnce(json(500, { error: 'Internal Server Error' }));
    render();
    await until(() => expect(phase()).toBe('never-scanned'));
    button(/Scan/).click();
    await until(() => expect(phase()).toBe('failed'));
    expect(target.querySelector('[role="alert"]')?.textContent).toContain('Internal Server Error');
    expect(button(/Scan again/).disabled).toBe(false);
  });

  it('failed when the scan reports ERROR (OSV unreachable)', async () => {
    const error = scanned();
    error.scan = { ...error.scan, status: 'ERROR', message: 'OSV.dev could not be reached.' };
    fetchMock.mockResolvedValue(json(200, error));
    render();
    await until(() => expect(phase()).toBe('failed'));
    expect(target.textContent).toContain('OSV.dev could not be reached.');
  });

  it('dismissed: Dismiss posts the rule id, reloads, and the row shows dismissed with Restore', async () => {
    fetchMock
      .mockResolvedValueOnce(json(200, scanned()))
      .mockResolvedValueOnce(json(200, { dismissed: ['GHSA-h5c8-rqwp-cp95::pypi:jinja2'] }))
      .mockResolvedValueOnce(json(200, scanned(true)))
      .mockResolvedValueOnce(json(200, { dismissed: [] }))
      .mockResolvedValueOnce(json(200, scanned()));
    render();
    await until(() => expect(phase()).toBe('results'));
    button(/Dismiss/).click();
    await until(() => expect(target.textContent).toContain('dismissed'));
    expect(fetchMock.mock.calls[1]![0]).toBe('api/dismissed-rules/GHSA-h5c8-rqwp-cp95%3A%3Apypi%3Ajinja2');
    expect(fetchMock.mock.calls[1]![1]?.method).toBe('POST');
    expect(fetchMock.mock.calls[2]![0]).toBe('api/vulnerabilities');
    expect(target.textContent).toContain('No known vulnerabilities');
    button(/Restore/).click();
    await until(() => expect(button(/Dismiss/)).toBeTruthy());
    expect(fetchMock.mock.calls[3]![1]?.method).toBe('DELETE');
  });

  it('read-only: Scan and Dismiss are disabled and the reason is shown', async () => {
    fetchMock.mockResolvedValue(json(200, scanned()));
    const reason = 'Panel is read-only via SHARPIT_PANELS_VULNERABILITIES_READ_ONLY=true';
    render({ ...panel, readOnly: true, readOnlyReason: reason });
    await until(() => expect(phase()).toBe('results'));
    expect(target.textContent).toContain(reason);
    expect(button(/Scan/).disabled).toBe(true);
    expect(button(/Dismiss/).disabled).toBe(true);
  });

  it('scanning disabled by configuration shows the server message', async () => {
    const off = inventory();
    off.scanningEnabled = false;
    off.scan = { ...off.scan, status: 'DISABLED', message: 'OSV scanning is disabled.' };
    fetchMock.mockResolvedValue(json(200, off));
    render();
    await until(() => expect(target.textContent).toContain('OSV scanning is disabled.'));
    expect(phase()).toBe('never-scanned'); // scannedAt null decides it, whatever the status says
    expect(button(/Scan/).disabled).toBe(true);
  });

  it('results whenever scannedAt is set, even if the status still says NOT_SCANNED', async () => {
    const r = scanned();
    r.scan = { ...r.scan, status: 'NOT_SCANNED' };
    fetchMock.mockResolvedValue(json(200, r));
    render();
    await until(() => expect(phase()).toBe('results'));
  });

  it('a failed reload after Dismiss keeps the report and reports the action error', async () => {
    fetchMock
      .mockResolvedValueOnce(json(200, scanned()))
      .mockResolvedValueOnce(json(200, { dismissed: ['GHSA-h5c8-rqwp-cp95::pypi:jinja2'] }))
      .mockResolvedValueOnce(json(500, { error: 'Internal Server Error' }));
    render();
    await until(() => expect(phase()).toBe('results'));
    button(/Dismiss/).click();
    await until(() => expect(target.querySelector('[role="alert"]')?.textContent).toContain('Internal Server Error'));
    expect(phase()).toBe('results');
    expect(target.textContent).toContain('GHSA-h5c8-rqwp-cp95');
  });
});
