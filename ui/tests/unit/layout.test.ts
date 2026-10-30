import { describe, expect, it } from 'vitest';
import { forceLayout, radialLayout } from '../../src/lib/layout';

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
