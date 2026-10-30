<script lang="ts">
  import type { Snippet } from 'svelte';
  import { ApiError } from '../lib/api';
  import { buildGraph, neighbourhood, type Graph, type GraphNode } from '../lib/graph';
  import { forceLayout, radialLayout, type Point } from '../lib/layout';
  import { ServerPage } from '../lib/paging';
  import type { BeanRow } from '../lib/types';

  let { focus = $bindable(null), controls }: { focus?: string | null; controls?: Snippet } = $props();

  /** Above this the force layout gets slow and the picture unreadable: focus a bean or filter instead. */
  const MAX_NODES = 120;
  const MAX_BEANS = 5000;

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
      return { nodes, edges, shown: nodes.length, eligible: 1 + keptOut.length + keptIn.length };
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
    const pos = forceLayout(picked.length, edges.map((e) => [index.get(e.from)!, index.get(e.to)!] as const));
    return {
      nodes: picked.map((n, i) => ({ ...n, ...pos[i]!, role: 'node' as const })),
      edges,
      shown: picked.length,
      eligible: candidates.length,
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
  const touches = (e: { from: string; to: string }, id: string | null) => id !== null && (e.from === id || e.to === id);

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

<div class="panel">
  <header class="panel-head">
    <h1>Beans</h1>
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
  <div class="panel-body graph-body">
    {#if error}
      <div class="empty" role="alert"><p class="lead danger">Could not load beans</p><p>{error}</p></div>
    {:else if !view}
      <p class="empty muted">Loading the dependency graph…</p>
    {:else}
      <p class="notice muted sm">
        {#if focus}
          <strong class="mono">{focus}</strong>: its dependencies on the right, its dependents on the left.
          <button class="link" onclick={() => (focus = null)}>Back to all beans</button> (Esc)
        {:else if view.eligible > view.shown}
          Showing the {view.shown} best-connected of {view.eligible} beans. Select a bean to see its neighbours.
        {:else if view.shown === 0}
          No beans in this classification. Pick another one above.
        {:else}
          Select a bean (click, or Tab then Enter) to see its dependencies and dependents.
        {/if}
      </p>
      <!-- svelte-ignore a11y_no_noninteractive_element_interactions -->
      <svg
        viewBox={box}
        role="group"
        aria-label="Bean dependency graph"
        onkeydown={(e) => e.key === 'Escape' && focus && (focus = null)}
      >
        <defs>
          <marker id="arrow" viewBox="0 0 10 10" refX="16" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
            <path d="M0 0 L10 5 L0 10 z" class="arrow" />
          </marker>
        </defs>
        {#each view.edges as e (e.from + '>' + e.to)}
          {@const a = at.get(e.from)!}
          {@const b = at.get(e.to)!}
          <line x1={a.x} y1={a.y} x2={b.x} y2={b.y} class:hot={touches(e, hover)} marker-end="url(#arrow)" />
        {/each}
        {#each view.nodes as n (n.id)}
          <g
            class="node {n.role}"
            class:external={n.external}
            class:app={n.classification === 'APPLICATION'}
            transform="translate({n.x} {n.y})"
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
              <text x={n.role === 'in' ? -10 : 10} y="4" text-anchor={n.role === 'in' ? 'end' : 'start'}>{short(n.id)}</text>
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
