/** The fields of the contract's `BeanSummary` that the graph needs. */
export interface Bean {
  name: string;
  type: string | null;
  classification: string;
  dependencies: string[];
}

export interface GraphNode {
  id: string;
  type: string | null;
  classification: string | null;
  /** A dependency name that is not itself a listed bean (e.g. a container-provided object). */
  external: boolean;
}

/** `from` depends on `to`. */
export interface GraphEdge {
  from: string;
  to: string;
}

export interface Graph {
  nodes: GraphNode[];
  edges: GraphEdge[];
}

/** One node per bean, one edge per `dependencies` entry; unknown dependency names become external nodes. */
export function buildGraph(beans: readonly Bean[]): Graph {
  const nodes = new Map<string, GraphNode>();
  for (const b of beans) nodes.set(b.name, { id: b.name, type: b.type, classification: b.classification, external: false });
  const edges: GraphEdge[] = [];
  for (const b of beans) {
    for (const to of b.dependencies) {
      if (!nodes.has(to)) nodes.set(to, { id: to, type: null, classification: null, external: true });
      edges.push({ from: b.name, to });
    }
  }
  return { nodes: [...nodes.values()], edges };
}

/** The subgraph within `depth` hops of `id`, following edges in both directions (dependencies and dependents). */
export function neighbourhood(graph: Graph, id: string, depth = 1): Graph {
  if (!graph.nodes.some((n) => n.id === id)) return { nodes: [], edges: [] };
  const adjacent = new Map<string, string[]>();
  const link = (a: string, b: string) => {
    const list = adjacent.get(a);
    if (list) list.push(b);
    else adjacent.set(a, [b]);
  };
  for (const e of graph.edges) {
    link(e.from, e.to);
    link(e.to, e.from);
  }
  const seen = new Set([id]);
  let frontier = [id];
  for (let d = 0; d < depth && frontier.length > 0; d++) {
    const next: string[] = [];
    for (const n of frontier) {
      for (const m of adjacent.get(n) ?? []) {
        if (!seen.has(m)) {
          seen.add(m);
          next.push(m);
        }
      }
    }
    frontier = next;
  }
  return {
    nodes: graph.nodes.filter((n) => seen.has(n.id)),
    edges: graph.edges.filter((e) => seen.has(e.from) && seen.has(e.to)),
  };
}
