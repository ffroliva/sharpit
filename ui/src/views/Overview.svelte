<script lang="ts">
  import { ApiError, get } from '../lib/api';
  import { linkable } from '../lib/links';
  import { scrollable } from '../lib/scrollable';
  import type { Overview } from '../lib/types';

  let data = $state<Overview | null>(null);
  let error = $state<string | null>(null);

  async function load() {
    error = null;
    try {
      data = await get<Overview>('overview');
    } catch (e) {
      error = e instanceof ApiError ? `HTTP ${e.status}` : 'The application is not responding.';
    }
  }
  load();

  const list = (xs: string[]) => (xs.length ? xs.join(', ') : 'none');
</script>

<div class="panel">
  <header class="panel-head">
    <h1>Scorecard</h1>
    {#if data}<span class="muted">{data.applicationName ?? 'Unnamed application'}</span>{/if}
  </header>
  <div class="panel-body" use:scrollable role="region" aria-label="Scorecard" tabindex="-1">
    {#if error}
      <div class="empty" role="alert"><p class="lead danger">Could not load the overview</p><p>{error}</p><button onclick={(event) => { const region = (event.currentTarget as HTMLElement).closest<HTMLElement>('.panel-body'); if (region) { region.tabIndex = -1; region.focus(); } void load(); }}>Retry</button></div>
    {:else if !data}
      <table aria-hidden="true"><tbody>{#each { length: 8 } as _}<tr class="skeleton"><td></td><td></td></tr>{/each}</tbody></table>
    {:else}
      <section class="block">
        <h2>Application</h2>
        <dl class="facts">
          <dt>Name</dt><dd class="mono">{data.applicationName ?? '—'}</dd>
          <dt>Framework</dt><dd>{data.frameworkName} <span class="mono">{data.frameworkVersion ?? ''}</span></dd>
          <dt>Python</dt><dd><span class="mono">{data.javaVersion ?? '—'}</span> <span class="muted">{data.javaVendor ?? ''}</span></dd>
          <dt>Server</dt>
          <dd>
            {data.webApplicationType ?? '—'}{#if data.serverPort}{' '}on port <span class="mono">{data.serverPort}</span>{/if}
            {#if data.contextPath}<span class="muted"> at </span><span class="mono">{data.contextPath}</span>{/if}
          </dd>
          <dt>Profiles</dt><dd class="mono">{list(data.activeProfiles)}</dd>
          {#if data.startupTimeMillis !== null}<dt>Startup</dt><dd>{data.startupTimeMillis} ms</dd>{/if}
          {#if data.openApiUrl}<dt>OpenAPI</dt><dd>{#if linkable(data.openApiUrl)}<a href={data.openApiUrl}>{data.openApiUrl}</a>{:else}<span class="mono">{data.openApiUrl}</span>{/if}</dd>{/if}
        </dl>
      </section>
      <section class="block">
        <h2>sharpit</h2>
        <dl class="facts">
          <dt>Status</dt>
          <dd><span class={data.activation.enabled ? 'ok' : 'danger'}>{data.activation.enabled ? 'Active' : 'Inactive'}</span> — {data.activation.reason}</dd>
          <dt>Access</dt>
          <dd>{data.activation.localhostOnly ? 'This machine only' : 'Remote access allowed (token required)'}</dd>
          <dt>Version</dt><dd class="mono">{data.bootUiVersion}</dd>
          {#each data.activation.warnings as warning}<dt class="warn">Warning</dt><dd class="warn">{warning}</dd>{/each}
        </dl>
      </section>
    {/if}
  </div>
</div>
