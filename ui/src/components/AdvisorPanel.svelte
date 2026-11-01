<script lang="ts" module>
  export type Phase = 'loading' | 'load-failed' | 'never-scanned' | 'scanning' | 'failed' | 'results';
</script>

<script lang="ts">
  import type { Snippet } from 'svelte';
  import { ApiError, errorText, field } from '../lib/api';
  import { advisorAssessment, scoreBandTone } from '../lib/score';
  import { scrollable } from '../lib/scrollable';
  import type { AdvisorReport, AdvisorRule, ViolationsPage } from '../lib/types';

  /**
   * The shared advisor layout (spec 8): scan button with busy and failed states, score ring, severity counts, and a rule
   * list with samples, paged violations and dismiss/restore. A view whose findings are not rules (Vulnerabilities)
   * renders its own body through `children` and reuses the rest.
   */
  let {
    title, report, loadError = null, onScan, onDismiss, onRestore, onDismissFinding, loadViolations, readOnlyReason = null,
    scanDisabledReason = null, vulnerabilities = false, scanLabel, status, children,
  }: {
    title: string;
    report: AdvisorReport | null;
    loadError?: string | null;
    /** Runs the scan and stores the new report; a thrown 409 shows as busy, anything else as a failed scan. */
    onScan: () => Promise<void>;
    /** Dismiss or restore and reload the report; a throw keeps the old report and shows the action error. */
    onDismiss: (ruleId: string) => Promise<void>;
    onRestore: (ruleId: string) => Promise<void>;
    /** Dismiss one finding by its fingerprint and reload the report; offered on a violation row that has one. */
    onDismissFinding?: (fingerprint: string) => Promise<void>;
    loadViolations?: (ruleId: string, offset: number) => Promise<ViolationsPage>;
    /** Disables Scan and Dismiss/Restore. */
    readOnlyReason?: string | null;
    /** Disables Scan only (e.g. scanning switched off by configuration). */
    scanDisabledReason?: string | null;
    vulnerabilities?: boolean;
    scanLabel?: (phase: Phase) => string;
    status?: Snippet<[Phase]>;
    children?: Snippet<[{ phase: Phase; pending: string | null; toggle: (ruleId: string, dismissed: boolean) => void }]>;
  } = $props();

  let scanning = $state(false);
  /** The 409 body's own text, shown next to the Scan button. */
  let busy = $state<string | null>(null);
  let scanError = $state<string | null>(null);
  let actionError = $state<string | null>(null);
  let pending = $state<string | null>(null);
  let showDismissed = $state(false);

  const phase: Phase = $derived(
    scanning
      ? 'scanning'
      : scanError || report?.scan.status === 'ERROR'
        ? 'failed'
        : loadError
          ? 'load-failed'
          : !report
            ? 'loading'
            : report.scan.scannedAt === null
              ? 'never-scanned'
              : 'results',
  );
  const scanBlocked = $derived(readOnlyReason ?? scanDisabledReason);
  const assessment = $derived(report ? advisorAssessment(report, { vulnerabilities }) : null);
  const rules = $derived((report?.results ?? []).filter((r) => showDismissed || !r.dismissed));
  const dismissedCount = $derived((report?.results ?? []).filter((r) => r.dismissed).length);
  const label = $derived(
    scanLabel?.(phase) ?? (phase === 'scanning' ? 'Scanning…' : phase === 'results' || phase === 'failed' ? 'Scan again' : 'Scan'),
  );

  async function scan() {
    if (scanning || scanBlocked) return;
    scanning = true;
    closeViolations(); // the open rule's rows belong to the old scan
    busy = null;
    scanError = null;
    try {
      await onScan();
    } catch (e) {
      if (e instanceof ApiError && e.status === 409) busy = field(e.body, 'message') ?? field(e.body, 'error') ?? 'Another scan is running.';
      else scanError = errorText(e);
    } finally {
      scanning = false;
    }
  }

  async function toggle(ruleId: string, dismissed: boolean) {
    if (pending || readOnlyReason) return;
    pending = ruleId;
    actionError = null;
    try {
      await (dismissed ? onRestore(ruleId) : onDismiss(ruleId));
    } catch (e) {
      actionError = `${dismissed ? 'Restore' : 'Dismiss'} failed: ${errorText(e)}`;
    } finally {
      pending = null;
    }
  }

  // "View violations": one rule open at a time, pages appended
  let openRule = $state<string | null>(null);
  let violations = $state<string[]>([]);
  let fingerprints = $state<(string | null)[]>([]); // parallel to `violations`
  let dismissedFindings = $state<string[]>([]);
  let hasMore = $state(false);
  let violationError = $state<string | null>(null);
  let paging = $state(false);
  let seq = 0; // a page whose request is no longer the latest (closed, reopened, rescanned) is dropped
  async function more(ruleId: string, offset: number) {
    if (!loadViolations || paging) return;
    const mine = seq;
    violationError = null;
    paging = true;
    try {
      const page = await loadViolations(ruleId, offset);
      if (mine !== seq) return;
      violations = [...violations, ...page.violations];
      fingerprints = [...fingerprints, ...page.violations.map((_, i) => page.fingerprints?.[i] ?? null)];
      hasMore = page.page.hasMore;
    } catch (e) {
      if (mine === seq) violationError = errorText(e);
    } finally {
      if (mine === seq) paging = false;
    }
  }
  function closeViolations() {
    seq++;
    openRule = null;
    violations = [];
    fingerprints = [];
    dismissedFindings = [];
    hasMore = false;
    paging = false;
    violationError = null;
  }
  function view(ruleId: string) {
    const opening = openRule !== ruleId;
    closeViolations();
    if (opening) {
      openRule = ruleId;
      void more(ruleId, 0);
    }
  }

  async function dismissFinding(fingerprint: string) {
    if (!onDismissFinding || pending || readOnlyReason) return;
    pending = fingerprint;
    actionError = null;
    try {
      await onDismissFinding(fingerprint);
      dismissedFindings = [...dismissedFindings, fingerprint];
    } catch (e) {
      actionError = `Dismiss failed: ${errorText(e)}`;
    } finally {
      pending = null;
    }
  }

  const tone = (severity: string) =>
    severity === 'CRITICAL' || severity === 'HIGH' ? 'danger' : severity === 'MEDIUM' ? 'warn' : 'muted';
</script>

<div class="panel" data-phase={phase}>
  <header class="panel-head">
    <h1>{title}</h1>
    <span class="grow muted" aria-live="polite">{@render status?.(phase)}</span>
    {#if busy}<span class="warn" role="status">{busy}</span>{/if}
    <button class="primary" onclick={scan} disabled={scanning || !!scanBlocked} aria-busy={scanning}>{label}</button>
  </header>

  <div class="panel-body" use:scrollable role="region" aria-label={title}>
    {#if scanBlocked}<p class="notice warn">{scanBlocked}</p>{/if}
    {#if actionError}<p class="notice danger" role="alert">{actionError}</p>{/if}

    {#if phase === 'loading'}
      <table aria-hidden="true"><tbody>{#each { length: 6 } as _}<tr class="skeleton"><td></td><td></td></tr>{/each}</tbody></table>
    {:else if phase === 'load-failed'}
      <div class="empty" role="alert"><p class="lead danger">Could not load {title}</p><p>{loadError}</p></div>
    {:else}
      {#if phase === 'failed'}
        <div class="empty" role="alert">
          <p class="lead danger">Scan failed</p>
          <p>{scanError ?? report?.scan.message}</p>
        </div>
      {:else if phase === 'results' && report && assessment}
        <section class="block score" aria-label="Score">
          <svg viewBox="0 0 36 36" aria-hidden="true" class={scoreBandTone(assessment.score)}>
            <circle cx="18" cy="18" r="15.5" pathLength="100" class="track" />
            {#if assessment.score !== null}
              <circle cx="18" cy="18" r="15.5" pathLength="100" class="arc" stroke-dasharray="{assessment.score} 100" />
            {/if}
          </svg>
          <div>
            <p>
              <strong class="value" data-score={assessment.score ?? ''}>{assessment.score ?? '—'}</strong>
              <span class="muted">{assessment.score === null ? assessment.label : 'of 100'}</span>
            </p>
            {#if assessment.reason}<p class="sm muted">{assessment.reason}</p>{/if}
            <p class="counts">
              {#each report.severityCounts as c (c.severity)}
                <span class="tag {c.count ? tone(c.severity) : 'muted'}">{c.severity} {c.count}</span>
              {/each}
            </p>
          </div>
        </section>
      {/if}

      {#if children}
        {@render children({ phase, pending, toggle })}
      {:else if phase === 'never-scanned' || phase === 'scanning'}
        <div class="empty">
          <p class="lead">{phase === 'scanning' ? 'Scanning…' : 'Not scanned yet'}</p>
          <p class="muted">{report?.scan.message}</p>
        </div>
      {:else if phase === 'results' && report}
        {#if dismissedCount > 0}
          <label class="show sm"><input type="checkbox" bind:checked={showDismissed} /> Show dismissed ({dismissedCount})</label>
        {/if}
        {#if rules.length === 0}
          <div class="empty"><p class="lead ok">No active findings</p><p class="muted">{report.scan.message}</p></div>
        {/if}
        {#each rules as r (r.id)}
          {@render rule(r)}
        {/each}
      {/if}
    {/if}
  </div>
</div>

{#snippet rule(r: AdvisorRule)}
  <article class="rule" class:dismissed={r.dismissed}>
    <header>
      <span class="tag {r.dismissed ? 'muted' : tone(r.severity)}">{r.severity}</span>
      <span class="mono">{r.id}</span>
      <strong>{r.name}</strong>
      <span class="muted sm">{r.violationCount} {r.violationCount === 1 ? 'violation' : 'violations'}</span>
      {#if r.dismissed}<span class="tag muted">dismissed</span>{/if}
      <span class="actions">
        {#if loadViolations}
          <button class="link" aria-expanded={openRule === r.id} aria-label="View violations for {r.id}" onclick={() => view(r.id)}>View violations</button>
        {/if}
        <button
          onclick={() => toggle(r.id, r.dismissed)}
          disabled={!!pending || !!readOnlyReason}
          title={readOnlyReason ?? undefined}
          aria-label="{r.dismissed ? 'Restore' : 'Dismiss'} {r.id}"
        >{r.dismissed ? 'Restore' : 'Dismiss'}</button>
      </span>
    </header>
    <p>{r.description}</p>
    {#if r.sampleViolations.length}
      <ul class="mono sm samples">{#each r.sampleViolations as s}<li>{s}</li>{/each}</ul>
    {/if}
    {#if r.recommendation}<p class="sm"><span class="muted">Fix:</span> {r.recommendation}</p>{/if}
    {#if r.learnMoreUrl}<p class="sm"><a href={r.learnMoreUrl} target="_blank" rel="noreferrer">Learn more</a></p>{/if}
    {#if openRule === r.id}
      <div class="violations">
        {#if violationError}<p class="danger sm" role="alert">{violationError}</p>{/if}
        <ol class="mono sm">
          {#each violations as v, i}
            {@const fingerprint = fingerprints[i]}
            <li>
              {v}
              {#if onDismissFinding && fingerprint}
                {#if dismissedFindings.includes(fingerprint)}
                  <span class="tag muted">dismissed</span>
                {:else}
                  <button
                    class="link"
                    onclick={() => dismissFinding(fingerprint)}
                    disabled={!!pending || !!readOnlyReason}
                    title={readOnlyReason ?? undefined}
                    aria-label="Dismiss finding {fingerprint}"
                  >Dismiss this finding</button>
                {/if}
              {/if}
            </li>
          {/each}
        </ol>
        {#if hasMore}<button disabled={paging} onclick={() => more(r.id, violations.length)}>Load more</button>{/if}
      </div>
    {/if}
  </article>
{/snippet}

<style>
  .score { display: flex; gap: var(--s4); align-items: center; padding: var(--s3) var(--s4); border-bottom: 1px solid var(--line); }
  .score svg { width: 56px; height: 56px; flex: none; transform: rotate(-90deg); }
  .score circle { fill: none; stroke-width: 3.5; }
  .score .track { stroke: var(--line); }
  .score .arc { stroke: currentColor; stroke-linecap: round; }
  .score p { margin: 0 0 var(--s1); }
  .score .value { font-size: 20px; line-height: 24px; color: var(--ink); }
  .counts { display: flex; flex-wrap: wrap; gap: var(--s2); }
  .show { display: block; padding: var(--s2) var(--s4); }
  .rule { padding: var(--s2) var(--s4); border-bottom: 1px solid var(--line); }
  .rule header { display: flex; flex-wrap: wrap; gap: var(--s2); align-items: baseline; }
  .rule p { margin: var(--s1) 0; }
  .rule.dismissed { color: var(--muted); }
  .actions { margin-left: auto; display: flex; gap: var(--s2); }
  .samples, .violations ol { margin: var(--s1) 0; padding-left: var(--s6); overflow-wrap: anywhere; }
  .violations { padding: var(--s1) 0 var(--s2); }
</style>
