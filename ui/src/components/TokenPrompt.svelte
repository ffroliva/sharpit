<script lang="ts">
  import { ApiError, session } from '../lib/api';

  let { onauthenticated }: { onauthenticated: () => void } = $props();

  let token = $state('');
  let pending = $state(false);
  let error = $state<string | null>(null);

  async function submit(event: SubmitEvent) {
    event.preventDefault();
    if (!token.trim() || pending) return;
    pending = true;
    error = null;
    try {
      await session(token.trim());
      token = '';
      onauthenticated();
    } catch (e) {
      error =
        e instanceof ApiError
          ? e.status === 401
            ? 'That token was not accepted. Copy it from the application log, where sharpit prints it at startup.'
            : `sharpit answered HTTP ${e.status}. Check the application log.`
          : 'The application is not responding. Restart it and retry.';
    } finally {
      pending = false;
    }
  }
</script>

<form class="prompt" onsubmit={submit} aria-labelledby="token-title">
  <h1 id="token-title">Token required</h1>
  <p class="muted">
    This browser is not on the application's machine, so sharpit asks for its token once. The token is printed in the
    application log when sharpit starts, or set with <code>SHARPIT_AUTHENTICATION_TOKEN</code>.
  </p>
  <label for="token">Token</label>
  <div class="row">
    <!-- svelte-ignore a11y_autofocus -->
    <input
      id="token"
      type="password"
      autocomplete="off"
      spellcheck="false"
      autofocus
      bind:value={token}
      aria-invalid={error ? 'true' : undefined}
      aria-describedby={error ? 'token-error' : undefined}
    />
    <button class="primary" type="submit" disabled={pending || !token.trim()}>
      {pending ? 'Checking…' : 'Unlock'}
    </button>
  </div>
  {#if error}<p id="token-error" class="danger" role="alert">{error}</p>{/if}
</form>

<style>
  .prompt { max-width: 440px; padding: var(--s6) var(--s4); }
  h1 { margin: 0 0 var(--s2); font-size: 16.5px; line-height: 24px; font-weight: 600; }
  p { margin: 0 0 var(--s3); }
  label { display: block; margin-bottom: var(--s1); }
  .row { display: flex; gap: var(--s2); }
  .row input { flex: 1; font-family: var(--mono); }
</style>
