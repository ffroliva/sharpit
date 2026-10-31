export interface Point {
  x: number;
  y: number;
}

/**
 * Fruchterman–Reingold force layout, run to completion before the first paint: no animation loop, so
 * `prefers-reduced-motion` has nothing to stop. Deterministic (golden-angle spiral start), O(n²) per step,
 * which is fine for the capped node count the graph renders.
 */
export function forceLayout(count: number, edges: readonly (readonly [number, number])[], iterations = 220): Point[] {
  const k = 34; // ideal edge length
  const pos: Point[] = Array.from({ length: count }, (_, i) => {
    const a = i * 2.399963;
    const r = k * 0.6 * Math.sqrt(i + 1);
    return { x: r * Math.cos(a), y: r * Math.sin(a) };
  });
  let temperature = k * 2;
  for (let it = 0; it < iterations; it++) {
    const dx = new Float64Array(count);
    const dy = new Float64Array(count);
    for (let i = 0; i < count; i++) {
      const a = pos[i]!;
      for (let j = i + 1; j < count; j++) {
        const b = pos[j]!;
        const x = a.x - b.x;
        const y = a.y - b.y;
        const d2 = Math.max(x * x + y * y, 0.01);
        const f = (k * k) / d2; // repulsion k²/d, applied along the unit vector
        dx[i]! += x * f;
        dy[i]! += y * f;
        dx[j]! -= x * f;
        dy[j]! -= y * f;
      }
    }
    for (const [s, t] of edges) {
      const a = pos[s]!;
      const b = pos[t]!;
      const x = a.x - b.x;
      const y = a.y - b.y;
      const d = Math.max(Math.hypot(x, y), 0.01);
      const f = d / k; // attraction d²/k, along the unit vector
      dx[s]! -= x * f;
      dy[s]! -= y * f;
      dx[t]! += x * f;
      dy[t]! += y * f;
    }
    for (let i = 0; i < count; i++) {
      const p = pos[i]!;
      const gx = dx[i]! - p.x * 0.08; // gravity: lone nodes settle about k/sqrt(0.08) ≈ 120 units out, not off-screen
      const gy = dy[i]! - p.y * 0.08;
      const d = Math.max(Math.hypot(gx, gy), 0.01);
      const step = Math.min(d, temperature);
      p.x += (gx / d) * step;
      p.y += (gy / d) * step;
    }
    temperature = Math.max(temperature * 0.97, 0.5);
  }
  return pos;
}

/** `centre` in the middle, its dependencies on an arc to the right, its dependents on the left. */
export function radialLayout(outgoing: number, incoming: number, radius = 150): { centre: Point; out: Point[]; in: Point[] } {
  const arc = (n: number, from: number, to: number) =>
    Array.from({ length: n }, (_, i) => {
      const a = n === 1 ? (from + to) / 2 : from + ((to - from) * i) / (n - 1);
      return { x: radius * Math.cos(a), y: radius * Math.sin(a) };
    });
  const spread = (n: number) => Math.min(Math.PI * 0.9, 0.35 * Math.max(n - 1, 0));
  return {
    centre: { x: 0, y: 0 },
    out: arc(outgoing, -spread(outgoing) / 2, spread(outgoing) / 2),
    in: arc(incoming, Math.PI - spread(incoming) / 2, Math.PI + spread(incoming) / 2),
  };
}

/** Column pitch and row pitch of `layeredLayout`: room for a centred label above each node. */
export const LAYER_COL = 220;
export const LAYER_ROW = 44;

/**
 * Left-to-right layers for a small graph: a node's column is the length of its longest dependency chain, so
 * dependents sit left of what they depend on and edges run rightwards, clear of the nodes. Rows within a column follow
 * the average row of the dependents already placed, which keeps a chain on one line. Cycles count once.
 */
export function layeredLayout(count: number, edges: readonly (readonly [number, number])[]): Point[] {
  const deps = Array.from({ length: count }, () => [] as number[]);
  const users = Array.from({ length: count }, () => [] as number[]);
  for (const [s, t] of edges) {
    if (s === t) continue;
    deps[s]!.push(t);
    users[t]!.push(s);
  }
  const height = new Array<number>(count).fill(-1);
  const visiting = new Set<number>();
  const measure = (i: number): number => {
    if (height[i]! >= 0) return height[i]!;
    if (visiting.has(i)) return 0; // a back edge: the cycle is cut here
    visiting.add(i);
    height[i] = Math.max(0, ...deps[i]!.map((d) => measure(d) + 1));
    visiting.delete(i);
    return height[i]!;
  };
  for (let i = 0; i < count; i++) measure(i);
  const top = Math.max(0, ...height);
  const pos: Point[] = new Array(count);
  const row = new Map<number, number>();
  for (let h = top; h >= 0; h--) {
    const column = [...height.keys()].filter((i) => height[i] === h);
    const weight = (i: number) => {
      const placed = users[i]!.filter((u) => row.has(u)).map((u) => row.get(u)!);
      return placed.length ? placed.reduce((a, b) => a + b, 0) / placed.length : Infinity; // unlinked nodes go last
    };
    column.sort((a, b) => weight(a) - weight(b) || a - b);
    column.forEach((i, r) => {
      row.set(i, r);
      pos[i] = { x: (top - h) * LAYER_COL, y: (r - (column.length - 1) / 2) * LAYER_ROW };
    });
  }
  return pos;
}
