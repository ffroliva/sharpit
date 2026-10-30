import { describe, expect, it } from 'vitest';
import { buildGraph, neighbourhood } from '../../src/lib/graph';
import fixture from '../../../tests/fixtures/bootui/beans.json';

const beans = fixture.beans;
const entries = beans.reduce((n, b) => n + b.dependencies.length, 0);
const names = new Set(beans.map((b) => b.name));
const missing = new Set(beans.flatMap((b) => b.dependencies).filter((d) => !names.has(d)));

describe('buildGraph', () => {
  const g = buildGraph(beans);

  it('has one edge per dependencies entry', () => {
    expect(entries).toBe(722);
    expect(g.edges).toHaveLength(entries);
    for (const b of beans) {
      expect(g.edges.filter((e) => e.from === b.name).map((e) => e.to)).toEqual(b.dependencies);
    }
  });

  it('adds an external node for each dependency that is not a bean, so no edge dangles', () => {
    expect(missing.size).toBe(21);
    expect(g.nodes).toHaveLength(beans.length + missing.size);
    const ids = new Set(g.nodes.map((n) => n.id));
    expect(ids.size).toBe(g.nodes.length);
    for (const e of g.edges) expect(ids.has(e.from) && ids.has(e.to)).toBe(true);
    expect(g.nodes.find((n) => n.id === 'environment')).toEqual({ id: 'environment', type: null, classification: null, external: true });
    expect(g.nodes.find((n) => n.id === beans[0]!.name)).toMatchObject({ type: beans[0]!.type, external: false });
  });
});

describe('neighbourhood', () => {
  const g = buildGraph(beans);
  // a bean with both dependencies and dependents
  const focus = beans.find((b) => b.dependencies.length > 0 && g.edges.some((e) => e.to === b.name))!;

  it('depth 1 holds the focus, its dependencies and its dependents, and only edges between them', () => {
    const n = neighbourhood(g, focus.name);
    const ids = new Set(n.nodes.map((x) => x.id));
    const expected = new Set([focus.name, ...focus.dependencies, ...g.edges.filter((e) => e.to === focus.name).map((e) => e.from)]);
    expect(ids).toEqual(expected);
    for (const e of n.edges) expect(ids.has(e.from) && ids.has(e.to)).toBe(true);
    expect(n.edges.length).toBe(g.edges.filter((e) => ids.has(e.from) && ids.has(e.to)).length);
  });

  it('depth 2 is a strict superset of depth 1', () => {
    const one = new Set(neighbourhood(g, focus.name, 1).nodes.map((x) => x.id));
    const two = new Set(neighbourhood(g, focus.name, 2).nodes.map((x) => x.id));
    expect([...one].every((id) => two.has(id))).toBe(true);
    expect(two.size).toBeGreaterThan(one.size);
  });

  it('depth 0 is the focus alone; an unknown id is empty', () => {
    expect(neighbourhood(g, focus.name, 0).nodes.map((x) => x.id)).toEqual([focus.name]);
    expect(neighbourhood(g, 'no-such-bean')).toEqual({ nodes: [], edges: [] });
  });
});
