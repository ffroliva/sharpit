<script lang="ts">
  import { tick, untrack, type Snippet } from 'svelte';
  import { ApiError } from '../lib/api';
  import { buildGraph, neighbourhood, type Graph, type GraphNode } from '../lib/graph';
  import { forceLayout, layeredLayout, radialLayout, type Point } from '../lib/layout';
  import { scrollable } from '../lib/scrollable';
  import { ServerPage } from '../lib/paging';
  import type { BeanRow } from '../lib/types';

  let { focus = $bindable(null), controls }: { focus?: string | null; controls?: Snippet } = $props();

  /** Above this the force layout gets slow and the picture unreadable: focus a bean or filter instead. */
  const MAX_NODES = 120;
  const MAX_BEANS = 5000;
  /** Up to this many nodes get the layered layout (and labels): columns by dependency depth, nothing overlaps. */
  const LAYERED = 40;

  let full = $state<Graph | null>(null);
  let error = $state<string | null>(null);
  let classification = $state('APPLICATION');
  let showExternal = $state(false);
  let hover = $state<string | null>(null);

  (async () => {
    try {
      full = buildGraph(await ServerPage.loadAll<BeanRow>('beans', 'beans', MAX_BEANS));
    } catch (e) {
      error = e instanceof ApiError ? `HTTP ${e.status}` : 'The application is not responding.';
    }
  })();

  const classifications = $derived(
    full ? [...new Set(full.nodes.filter((n) => !n.external).map((n) => n.classification!))].sort() : [],
  );

  interface View {
    nodes: (GraphNode & Point & { role: 'centre' | 'out' | 'in' | 'node' })[];
    edges: { from: string; to: string }[];
    shown: number;
    eligible: number;
    layered: boolean;
  }

  const view: View | null = $derived.by(() => {
    if (!full) return null;
    const keep = (n: GraphNode) => showExternal || !n.external || n.id === focus;
    if (focus && full.nodes.some((n) => n.id === focus)) {
      const near = neighbourhood(full, focus, 1);
      const out = near.edges.filter((e) => e.from === focus && e.to !== focus).map((e) => e.to);
      const inn = near.edges.filter((e) => e.to === focus && e.from !== focus).map((e) => e.from);
      const byId = new Map(near.nodes.map((n) => [n.id, n]));
      const keptOut = [...new Set(out)].map((id) => byId.get(id)!).filter(keep);
      const keptIn = [...new Set(inn)].filter((id) => !out.includes(id)).map((id) => byId.get(id)!).filter(keep);
      // same node cap as the overview: the centre plus at most MAX_NODES - 1 neighbours, dependencies first
      const outs = keptOut.slice(0, MAX_NODES - 1);
      const ins = keptIn.slice(0, MAX_NODES - 1 - outs.length);
      const r = radialLayout(outs.length, ins.length, 110 + 6 * Math.max(outs.length, ins.length));
      const nodes: View['nodes'] = [
        { ...byId.get(focus)!, ...r.centre, role: 'centre' },
        ...outs.map((n, i) => ({ ...n, ...r.out[i]!, role: 'out' as const })),
        ...ins.map((n, i) => ({ ...n, ...r.in[i]!, role: 'in' as const })),
      ];
      const ids = new Set(nodes.map((n) => n.id));
      const edges = near.edges.filter((e) => ids.has(e.from) && ids.has(e.to) && (e.from === focus || e.to === focus));
      return { nodes, edges, shown: nodes.length, eligible: 1 + keptOut.length + keptIn.length, layered: false };
    }
    const inClass = full.nodes.filter((n) => !n.external && (!classification || n.classification === classification));
    const base = new Set(inClass.map((n) => n.id));
    const externals = showExternal
      ? full.nodes.filter((n) => n.external && full!.edges.some((e) => e.to === n.id && base.has(e.from)))
      : [];
    const candidates = [...inClass, ...externals];
    // keep the best-connected nodes when over the cap
    const degree = new Map<string, number>();
    for (const e of full.edges) {
      degree.set(e.from, (degree.get(e.from) ?? 0) + 1);
      degree.set(e.to, (degree.get(e.to) ?? 0) + 1);
    }
    const picked =
      candidates.length > MAX_NODES
        ? [...candidates].sort((a, b) => (degree.get(b.id) ?? 0) - (degree.get(a.id) ?? 0)).slice(0, MAX_NODES)
        : candidates;
    const index = new Map(picked.map((n, i) => [n.id, i]));
    const edges = full.edges.filter((e) => index.has(e.from) && index.has(e.to));
    const pairs = edges.map((e) => [index.get(e.from)!, index.get(e.to)!] as const);
    const layered = picked.length <= LAYERED;
    const pos = layered ? layeredLayout(picked.length, pairs) : forceLayout(picked.length, pairs);
    return {
      nodes: picked.map((n, i) => ({ ...n, ...pos[i]!, role: 'node' as const })),
      edges,
      shown: picked.length,
      eligible: candidates.length,
      layered,
    };
  });

  const at = $derived(new Map((view?.nodes ?? []).map((n) => [n.id, n])));
  // fit the content, but never zoom in past ~1:1 on a sparse graph (labels stay a readable size, unclipped)
  const box = $derived.by(() => {
    const ns = view?.nodes ?? [];
    const xs = ns.map((n) => n.x);
    const ys = ns.map((n) => n.y);
    const [minX, maxX] = ns.length ? [Math.min(...xs), Math.max(...xs)] : [0, 0];
    const [minY, maxY] = ns.length ? [Math.min(...ys), Math.max(...ys)] : [0, 0];
    const w = Math.max(maxX - minX + 2 * 170, 720); // 170: room for a label either side
    const h = Math.max(maxY - minY + 2 * 30, 420);
    return `${(minX + maxX) / 2 - w / 2} ${(minY + maxY) / 2 - h / 2} ${w} ${h}`;
  });
  const labelled = $derived((view?.nodes.length ?? 0) <= 40 || !!focus);

  // `module:function` and dotted names: the last segment is what a developer recognises
  const short = (id: string) => id.split(/[:.]/).filter(Boolean).pop() ?? id;
  /** `to` moved `by` units towards `from`: the arrow tip stops at the circle's edge instead of under it. */
  const towards = (to: Point, from: Point, by: number): Point => {
    const d = Math.hypot(to.x - from.x, to.y - from.y) || 1;
    return { x: to.x - ((to.x - from.x) / d) * by, y: to.y - ((to.y - from.y) / d) * by };
  };
  const touches = (e: { from: string; to: string }, id: string | null) => id !== null && (e.from === id || e.to === id);

  let svg = $state<SVGSVGElement>();
  let heading = $state<HTMLElement>();
  const nodeEl = (id: string) => svg?.querySelector<SVGGElement>(`g[data-id="${CSS.escape(id)}"]`) ?? null;

  // Arriving from the list's Graph button: once drawn, keyboard focus lands on the centre node
  let land = untrack(() => focus) !== null;
  $effect(() => {
    if (view && land) {
      land = false;
      tick().then(() => focus && nodeEl(focus)?.focus());
    }
  });

  /** Leave focus mode; keyboard focus goes to the node that was the centre (or the heading if it is filtered out). */
  async function back() {
    const was = focus;
    focus = null;
    hover = null;
    await tick();
    const el = was ? nodeEl(was) : null;
    if (el) el.focus();
    else if (heading) {
      heading.tabIndex = -1;
      heading.focus();
    }
  }

  // on the window: after a click the focused element may be anywhere in the panel; the palette's own Esc is left alone
  function onwindowkey(event: KeyboardEvent) {
    if (event.key !== 'Escape' || !focus || event.defaultPrevented) return;
    if (event.target instanceof Element && event.target.closest('dialog')) return;
    event.preventDefault();
    back();
  }

  function choose(id: string) {
    focus = id === focus ? null : id;
    hover = null;
  }
  function key(event: KeyboardEvent, id: string) {
    if (event.key === 'Enter' || event.key === ' ') {
      event.preventDefault();
      choose(id);
    }
  }
</script>

<svelte:window onkeydown={onwindowkey} />

<div class="panel">
  <header class="panel-head">
    <h1 bind:this={heading}>Providers</h1>
    {@render controls?.()}
    <span class="grow"></span>
    {#if !focus}
      <label class="visually-hidden" for="graph-class">Classification</label>
      <select id="graph-class" bind:value={classification}>
        {#each classifications as c}<option value={c}>{c.toLowerCase()}</option>{/each}
        <option value="">all classifications</option>
      </select>
    {/if}
    <label class="check"><input type="checkbox" bind:checked={showExternal} /> External</label>
    <span class="muted count" aria-live="polite">
      {#if view}{view.shown} of {view.eligible}{/if}
    </span>
  </header>
  <div class="panel-body graph-body" use:scrollable role="region" aria-label="Providers">
    {#if error}
      <div class="empty" role="alert"><p class="lead danger">Could not load providers</p><p>{error}</p></div>
    {:else if !view}
      <p class="empty muted">Loading the dependency graph…</p>
    {:else}
      <p class="notice muted sm">
        {#if focus && view.shown === 1}
          <strong class="mono">{short(focus)}</strong> has no dependencies, and nothing depends on it.
          <button class="link" onclick={back}>Back to all providers</button> (Esc)
        {:else if focus}
          <strong class="mono">{focus}</strong>: its dependencies on the right, its dependents on the left.
          <button class="link" onclick={back}>Back to all providers</button> (Esc)
        {:else if view.eligible > view.shown}
          Showing the {view.shown} best-connected of {view.eligible} providers. Select one to see its neighbours.
        {:else if view.shown === 0}
          No providers in this classification. Pick another one above.
        {:else}
          Arrows point from a provider to what it depends on. Select one (click, or Tab then Enter) to focus it.
        {/if}
      </p>
      <svg bind:this={svg} viewBox={box} role="group" aria-label="Provider dependency graph">
        <defs>
          <marker id="arrow" viewBox="0 0 10 10" refX="10" refY="5" markerUnits="userSpaceOnUse" markerWidth="7" markerHeight="7" orient="auto">
            <path d="M0 0 L10 5 L0 10 z" class="arrow" />
          </marker>
        </defs>
        {#each view.edges as e (e.from + '>' + e.to)}
          {@const a = at.get(e.from)!}
          {@const b = at.get(e.to)!}
          {@const tip = towards(b, a, (b.role === 'centre' ? 8 : 5) + 2)}
          <line x1={a.x} y1={a.y} x2={tip.x} y2={tip.y} class:hot={touches(e, hover)} marker-end="url(#arrow)" />
        {/each}
        {#each view.nodes as n (n.id)}
          <g
            class="node {n.role}"
            class:external={n.external}
            class:app={n.classification === 'APPLICATION'}
            transform="translate({n.x} {n.y})"
            data-id={n.id}
            role="button"
            tabindex="0"
            aria-label="{n.id}{n.external ? ' (external)' : ''}{n.id === focus ? ', focused' : ''}"
            aria-pressed={n.id === focus}
            onclick={() => choose(n.id)}
            onkeydown={(e) => key(e, n.id)}
            onpointerenter={() => (hover = n.id)}
            onpointerleave={() => (hover = null)}
            onfocus={() => (hover = n.id)}
            onblur={() => (hover = null)}
          >
            <title>{n.id}{n.type && n.type !== n.id ? `\n${n.type}` : ''}</title>
            <circle r={n.role === 'centre' ? 8 : 5} />
            {#if labelled || hover === n.id}
              {#if view.layered}
                <!-- above the node: edges leave sideways, so a label never sits on one -->
                <text y="-11" text-anchor="middle">{short(n.id)}</text>
              {:else}
                <text x={n.role === 'in' ? -10 : 10} y="4" text-anchor={n.role === 'in' ? 'end' : 'start'}>{short(n.id)}</text>
              {/if}
            {/if}
          </g>
        {/each}
      </svg>
    {/if}
  </div>
</div>

<style>
  .graph-body { display: flex; flex-direction: column; }
  svg { flex: 1; width: 100%; min-height: 360px; display: block; }
  .check { display: inline-flex; align-items: center; gap: var(--s1); white-space: nowrap; }
  .count { white-space: nowrap; }
  line { stroke: var(--muted); stroke-width: 1; opacity: 0.55; vector-effect: non-scaling-stroke; }
  line.hot { stroke: var(--accent); opacity: 1; stroke-width: 1.5; }
  .arrow { fill: var(--muted); }
  .node { cursor: pointer; outline: none; }
  .node circle { fill: var(--bg); stroke: var(--muted); stroke-width: 1.5; vector-effect: non-scaling-stroke; }
  .node.app circle { stroke: var(--ink); }
  .node.external circle { stroke-dasharray: 2 2; }
  .node.centre circle { fill: var(--accent); stroke: var(--accent); }
  .node:hover circle { fill: var(--sel); }
  .node.centre:hover circle { fill: var(--accent); }
  .node:focus-visible circle { stroke: var(--accent); stroke-width: 3; }
  text { font: 11px var(--mono); fill: var(--ink); paint-order: stroke; stroke: var(--bg); stroke-width: 3px; }
</style>
