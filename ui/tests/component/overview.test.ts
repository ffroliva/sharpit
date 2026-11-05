// @vitest-environment jsdom
import { expect, it } from 'vitest';
import Overview from '../../src/views/Overview.svelte';
import { harness, json, until } from './support';

const h = harness();

it('Retry reloads the overview and leaves focus in its panel region', async () => {
  let calls = 0;
  h.route(() => ++calls === 1 ? json(503, { error: 'offline' }) : json(200, {
    bootUiVersion: '0.5.0', applicationName: 'sample', frameworkName: 'FastAPI', frameworkVersion: null,
    javaVersion: null, javaVendor: null, activeProfiles: [], defaultProfiles: [], webApplicationType: null,
    serverPort: null, managementPort: null, contextPath: null, startupTimeMillis: null,
    activation: { enabled: true, localhostOnly: true, reason: 'active', warnings: [] }, openApiUrl: null,
  }));
  h.mount(Overview);
  await until(() => expect(h.target.querySelector('[role="alert"]')?.textContent).toContain('Could not load'));
  h.target.querySelector<HTMLButtonElement>('button')!.click();
  expect(document.activeElement).toBe(h.target.querySelector('.panel-body'));
  await until(() => expect(h.text()).toContain('sample'));
  expect(calls).toBe(2);
});
