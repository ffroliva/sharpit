import { describe, expect, it } from 'vitest';
import { forceLayout, LAYER_ROW, layeredLayout, radialLayout } from '../../src/lib/layout';

describe('forceLayout', () => {
  it('places every node at a finite point, deterministically', () => {
    const edges: [number, number][] = [[0, 1], [1, 2], [3, 4]];
    const a = forceLayout(6, edges);
    expect(a).toHaveLength(6);
    for (const p of a) expect(Number.isFinite(p.x) && Number.isFinite(p.y)).toBe(true);
    expect(forceLayout(6, edges)).toEqual(a);
  });

  it('pulls linked nodes closer than unlinked ones', () => {
    const p = forceLayout(4, [[0, 1], [2, 3]]);
    const d = (i: number, j: number) => Math.hypot(p[i]!.x - p[j]!.x, p[i]!.y - p[j]!.y);
    expect(d(0, 1)).toBeLessThan(d(0, 2));
    expect(d(2, 3)).toBeLessThan(d(1, 3));
  });
});

describe('radialLayout', () => {
  it('puts dependencies right of the centre and dependents left', () => {
    const r = radialLayout(3, 2);
    expect(r.out).toHaveLength(3);
    expect(r.in).toHaveLength(2);
    for (const p of r.out) expect(p.x).toBeGreaterThan(0);
    for (const p of r.in) expect(p.x).toBeLessThan(0);
  });
});

describe('layeredLayout', () => {
  // owner_repository(0) -> database(1) -> settings(2); 3, 4 and 5 stand alone
  const edges: [number, number][] = [[0, 1], [1, 2]];

  it('puts dependents left of their dependencies, one column per depth', () => {
    const p = layeredLayout(6, edges);
    expect(p[0]!.x).toBeLessThan(p[1]!.x);
    expect(p[1]!.x).toBeLessThan(p[2]!.x);
  });

  it('never overlaps two nodes: every pair is at least a label row apart', () => {
    const p = layeredLayout(6, edges);
    for (let i = 0; i < p.length; i++) {
      for (let j = i + 1; j < p.length; j++) {
        expect(Math.hypot(p[i]!.x - p[j]!.x, p[i]!.y - p[j]!.y)).toBeGreaterThanOrEqual(LAYER_ROW);
      }
    }
  });

  it('survives a cycle and is deterministic', () => {
    const cyclic: [number, number][] = [[0, 1], [1, 0], [1, 2]];
    const a = layeredLayout(3, cyclic);
    for (const q of a) expect(Number.isFinite(q.x) && Number.isFinite(q.y)).toBe(true);
    expect(layeredLayout(3, cyclic)).toEqual(a);
  });
});
