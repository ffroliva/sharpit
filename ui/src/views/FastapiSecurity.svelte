<script lang="ts">
  import PanelShell from '../components/PanelShell.svelte';
  import { errorText, get } from '../lib/api';
  import { loader } from '../lib/load.svelte';
  import type { Panel } from '../lib/types';

  let { panel }: { panel: Panel } = $props();

  type Chain = {
    order: number; requestMatcher: string; requestMatcherType: string; filters: string[];
    csrfEnabled: boolean; corsEnabled: boolean; sessionManagementPresent: boolean;
  };
  type Report = {
    springSecurityPresent: boolean; chains: Chain[]; limitations: string[];
    auth: { authenticationProviderTypes: string[]; userDetailsServiceTypes: string[]; configuredUsername: string | null } | null;
  };
  type Endpoint = {
    method: string; pattern: string; handler: string; secured: boolean; rule: string; roles: string[];
    chainIndex: number | null; matcherDescription: string | null; description: string | null; bestEffort: boolean;
  };
  type Endpoints = { springSecurityPresent: boolean; total: number; endpoints: Endpoint[] };
  type Explain = {
    matched: boolean; bestEffort: boolean; chainIndex: number | null; matcherDescription: string | null;
    filters: string[]; rule: string | null; roles: string[]; pattern: string | null;
  };

  const report = loader(() => get<Report>('fastapi-security'));
  const endpoints = loader(() => get<Endpoints>('fastapi-security/endpoints'));
  const reload = () => void Promise.all([report.reload(), endpoints.reload()]);
  $effect(reload);

  let rule = $state('');
  const rules = $derived([...new Set((endpoints.data?.endpoints ?? []).map((e) => e.rule))].sort());
  const shown = $derived((endpoints.data?.endpoints ?? []).filter((e) => !rule || e.rule === rule));

  let method = $state('GET');
  let path = $state('/');
  let result = $state<Explain | null>(null);
  let explainError = $state('');
  async function runExplain() {
    explainError = '';
    try {
      result = await get<Explain>('fastapi-security/explain', { method, path });
    } catch (e) {
      result = null;
      explainError = errorText(e);
    }
  }
</script>

<PanelShell title={panel.title} loading={report.loading} error={report.error ?? endpoints.error} onretry={reload}>
  {#if report.data}
    {#if !report.data.springSecurityPresent}
      <div class="empty">
        <p class="lead">FastAPI security unavailable</p>
        {#each report.data.limitations as why (why)}<p>{why}</p>{/each}
      </div>
    {:else}
      {#each report.data.limitations as why (why)}<p class="warn">{why}</p>{/each}
      <h2>Middleware stacks</h2>
      {#each report.data.chains as chain (chain.order)}
        <section class="chain">
          <p><strong>{chain.order}</strong> <span class="mono">{chain.requestMatcher}</span> <span class="muted">{chain.requestMatcherType}</span>
            {#if chain.corsEnabled}<span class="tag">CORS</span>{/if}
            {#if chain.csrfEnabled}<span class="tag">CSRF</span>{/if}
            {#if chain.sessionManagementPresent}<span class="tag">session</span>{/if}
          </p>
          {#if chain.filters.length === 0}
            <p class="muted">No middleware.</p>
          {:else}
            <ol class="mono">{#each chain.filters as f, i (i)}<li>{f}</li>{/each}</ol>
          {/if}
        </section>
      {/each}
      {#if report.data.auth}
        <h2>Authentication</h2>
        <dl>
          <dt>Security schemes</dt>
          <dd class="mono">{report.data.auth.authenticationProviderTypes.join(', ') || 'none'}</dd>
          <dt>Authentication backends</dt>
          <dd class="mono">{report.data.auth.userDetailsServiceTypes.join(', ') || 'none'}</dd>
        </dl>
      {/if}

      <h2>Explain a request</h2>
      <form class="form" onsubmit={(e) => (e.preventDefault(), void runExplain())}>
        <input type="text" aria-label="Method" bind:value={method} size="7" autocomplete="off" spellcheck="false" />
        <input type="text" aria-label="Path" bind:value={path} autocomplete="off" spellcheck="false" />
        <button type="submit" class="primary">Explain</button>
      </form>
      {#if explainError}<p class="warn">{explainError}</p>{/if}
      {#if result}
        <p class="explain">
          {#if result.matched}
            Matched <span class="mono">{result.pattern}</span>: <strong>{result.rule}</strong>
            {#if result.roles.length}<span class="mono">{result.roles.join(', ')}</span>{/if}
            via stack {result.chainIndex} ({result.matcherDescription})
          {:else}
            Not matched{#if result.matcherDescription}: {result.matcherDescription}{/if}
          {/if}
          {#if result.bestEffort}<span class="tag warn" title="Read statically; part of the route could not be inspected">best effort</span>{/if}
        </p>
      {/if}

      <h2>Endpoints</h2>
      {#if endpoints.data}
        <label class="sm">Rule
          <select aria-label="Rule" bind:value={rule}>
            <option value="">all ({endpoints.data.total})</option>
            {#each rules as r (r)}<option value={r}>{r}</option>{/each}
          </select>
        </label>
        <table>
          <thead><tr><th>Method</th><th>Path</th><th>Rule</th><th>Roles</th><th>Handler</th><th>Notes</th></tr></thead>
          <tbody>
            {#each shown as e (e.method + ' ' + e.pattern)}
              <tr>
                <td>{e.method}</td>
                <td class="mono">{e.pattern}</td>
                <td class:muted={!e.secured}>{e.rule}</td>
                <td class="mono">{e.roles.join(', ')}</td>
                <td class="mono">{e.handler}</td>
                <td>
                  {#if e.bestEffort}<span class="tag warn">best effort</span>{/if}
                  {#if e.description}<span class="muted">{e.description}</span>{/if}
                </td>
              </tr>
            {/each}
          </tbody>
        </table>
      {/if}
    {/if}
  {/if}
</PanelShell>
