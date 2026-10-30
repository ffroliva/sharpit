<script lang="ts">
  import { ApiError, get, post } from '../lib/api';
  import { firstSentence } from '../lib/format';
  import { scrollable } from '../lib/scrollable';
  import type { Panel, ServerStatus } from '../lib/types';

  /** MCP server and CLI share one status shape; only MCP has an on/off toggle. */
  let { panel, kind }: { panel: Panel; kind: 'mcp-server' | 'cli' } = $props();

  let data = $state<ServerStatus | null>(null);
  let error = $state<string | null>(null);
  let toggling = $state(false);
  let toggleError = $state<string | null>(null);

  const describe = (e: unknown) => {
    const body = e instanceof ApiError ? e.body : null;
    if (typeof body === 'object' && body !== null && 'error' in body) return String(body.error);
    return e instanceof ApiError ? `HTTP ${e.status}` : 'The application is not responding.';
  };

  // svelte-ignore state_referenced_locally (one view instance per panel)
  get<ServerStatus>(kind).then(
    (d) => (data = d),
    (e: unknown) => (error = describe(e)),
  );

  async function toggle() {
    if (!data || toggling || panel.readOnly) return;
    toggling = true;
    toggleError = null;
    try {
      data = await post<ServerStatus>('mcp-server/toggle', { enabled: !data.enabled });
    } catch (e) {
      toggleError = describe(e);
    } finally {
      toggling = false;
    }
  }

  const title = $derived(kind === 'cli' ? 'CLI' : 'MCP server');
  // the endpoint is relative to this host; a client needs the whole URL
  const url = $derived(data ? new URL(data.endpoint, location.href).href : '');
  const connect = $derived(
    kind === 'cli'
      ? `curl -X POST ${url}/tools/get_overview -H "content-type: application/json" -d "{}"`
      : `claude mcp add --transport http sharpit ${url}`,
  );
  /** The tool text is written for an LLM; backticks mark code. Split so code renders as code. */
  const segments = (text: string) => text.split('`').map((t, i) => ({ t, code: i % 2 === 1 }));
  const average = (d: ServerStatus) => (d.callCount ? Math.round(d.totalLatencyMillis / d.callCount) : 0);
</script>

<div class="panel">
  <header class="panel-head">
    <h1>{title}</h1>
    {#if data}
      <span class={data.enabled ? 'ok' : 'muted'}>{data.enabled ? 'On' : 'Off'}</span>
    {/if}
    <span class="grow"></span>
    {#if toggleError}<span class="danger" role="alert">{toggleError}</span>{/if}
    {#if kind === 'mcp-server' && data}
      <button
        class={data.enabled ? '' : 'primary'}
        onclick={toggle}
        disabled={panel.readOnly}
        aria-disabled={toggling || undefined}
        title={panel.readOnly ? (panel.readOnlyReason ?? undefined) : undefined}
      >
        {toggling ? 'Switching…' : data.enabled ? 'Turn off' : 'Turn on'}
      </button>
    {/if}
  </header>
  <div class="panel-body" use:scrollable role="region" aria-label={title}>
    {#if panel.readOnly}<p class="notice warn">{panel.readOnlyReason}</p>{/if}
    {#if error}
      <div class="empty" role="alert"><p class="lead danger">Could not load the {title} status</p><p>{error}</p></div>
    {:else if !data}
      <table aria-hidden="true"><tbody>{#each { length: 6 } as _}<tr class="skeleton"><td></td><td></td></tr>{/each}</tbody></table>
    {:else}
      <section class="block">
        <dl class="facts">
          <dt>Endpoint</dt><dd class="mono">{url}</dd>
          <dt>{kind === 'cli' ? 'Try it' : 'Connect'}</dt>
          <dd>
            <code class="cmd">{connect}</code>
            <span class="muted sm">{kind === 'cli' ? 'Every tool below is POST …/tools/<name> with its arguments as JSON. Outside the browser, add the session cookie or -H "Authorization: Bearer $SHARPIT_AUTHENTICATION_TOKEN".' : 'Claude Code; other MCP clients take the same URL over streamable HTTP.'}</span>
          </dd>
          {#if data.configuredMode}
            <dt>Configured</dt>
            <dd>
              <span class="mono">{data.configuredMode}</span>
              {#if data.overridden}<span class="muted"> (switched here until restart)</span>{/if}
            </dd>
          {/if}
          {#if data.protocolVersion}<dt>Protocol</dt><dd class="mono">{data.protocolVersion}</dd>{/if}
          <dt>Server</dt><dd><span class="mono">{data.serverName} {data.serverVersion}</span></dd>
          <dt>Calls</dt>
          <dd>
            {data.callCount}{#if data.callCount} <span class="muted">· {average(data)} ms average</span>{/if}
            {#if data.timeouts || data.capacityRefusals || data.responseLimitRefusals}
              <span class="warn">
                · {data.timeouts} timed out, {data.capacityRefusals} refused at capacity{#if data.responseLimitRefusals !== undefined}, {data.responseLimitRefusals} over the size limit{/if}
              </span>
            {/if}
          </dd>
          <dt>Results cap</dt><dd>{data.maxResults} rows per call</dd>
        </dl>
      </section>
      {#if data.tools.length === 0}
        <div class="empty">
          <p>{kind === 'cli' ? 'The CLI endpoint is off, so no tools are listed.' : 'No tools are available.'}</p>
        </div>
      {:else}
        <table aria-label="{title} tools">
          <thead>
            <tr><th>{kind === 'cli' ? 'Command' : 'Tool'}</th><th>What it returns</th><th>Panel</th></tr>
          </thead>
          <tbody>
            {#each data.tools as t (t.name)}
              <tr>
                <td class="mono">{t.name}</td>
                <td class="desc">
                  <details>
                    <summary>{#each segments(firstSentence(t.description)) as seg}{#if seg.code}<code>{seg.t}</code>{:else}{seg.t}{/if}{/each}</summary>
                    <p>{#each segments(t.description) as seg}{#if seg.code}<code>{seg.t}</code>{:else}{seg.t}{/if}{/each}</p>
                  </details>
                </td>
                <td>
                  <span class="mono">{t.panel}</span>
                  {#if !t.panelEnabled}<span class="tag muted">disabled</span>
                  {:else if t.action && t.panelReadOnly}<span class="tag warn">read-only</span>{/if}
                  {#if t.action}<span class="tag muted">action</span>{/if}
                </td>
              </tr>
            {/each}
          </tbody>
        </table>
      {/if}
    {/if}
  </div>
</div>

<style>
  .desc { max-width: 72ch; padding-top: var(--s1); padding-bottom: var(--s1); }
  .desc summary { cursor: pointer; }
  .desc p { margin: var(--s1) 0 0; color: var(--muted); }
  .cmd { display: block; user-select: all; overflow-wrap: anywhere; } /* one click selects the whole command */
  dd .sm { display: block; }
  .tag { margin-left: var(--s1); }
</style>
