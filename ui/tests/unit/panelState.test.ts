import { describe, expect, it } from 'vitest';
import { panelActionReason, routePanelState } from '../../src/lib/panelState';
import type { Panel } from '../../src/lib/types';

describe('panelState', () => {
  // ported: panelState.test.js::panelState fails closed for unresolved action policy %j
  it.each([null, {}, { id: 'memory' }, { readOnly: 'false' as unknown as boolean }])(
    'fails closed for unresolved action policy %j',
    (panel) => {
      expect(panelActionReason(panel as Partial<Panel>)).toContain('Action permissions are unavailable');
    },
  );

  // ported: panelState.test.js::panelState distinguishes known writable, disabled, unavailable and read-only action targets
  it('distinguishes known writable, disabled, unavailable and read-only action targets', () => {
    expect(panelActionReason({ id: 'memory', readOnly: false })).toBeNull();
    expect(panelActionReason({ id: 'memory', enabled: false, readOnly: false })).toMatch(/enabled=false/i);
    expect(panelActionReason({ available: false, unavailableReason: 'No support' })).toBe('No support');
    expect(panelActionReason({ readOnly: true, readOnlyReason: 'Global policy' })).toBe('Global policy');
    expect(panelActionReason({ readOnly: true })).toBe('This panel is read-only.');
  });

  it('strictly follows priority order: disabled before unavailable, unavailable before readOnly', () => {
    expect(
      panelActionReason({
        id: 'memory',
        enabled: false,
        available: false,
        unavailableReason: 'Not available',
        readOnly: true,
        readOnlyReason: 'Read only',
      }),
    ).toMatch(/enabled=false/i);

    expect(
      panelActionReason({
        id: 'memory',
        enabled: true,
        available: false,
        unavailableReason: 'Not available',
        readOnly: true,
        readOnlyReason: 'Read only',
      }),
    ).toBe('Not available');

    expect(
      panelActionReason({
        id: 'memory',
        enabled: true,
        available: true,
        readOnly: true,
        readOnlyReason: 'Read only',
      }),
    ).toBe('Read only');
  });

  // ported: panelNavigation.test.js::panel navigation moves disabled and unavailable panels into the same explicit group used by the sidebar
  it('routePanelState provides canonical route-state fallback descriptions for navigation', () => {
    expect(routePanelState({ id: 'spring', enabled: false })).toEqual({
      kind: 'disabled',
      label: 'Disabled',
      reason: 'Panel is disabled via SHARPIT_PANELS_SPRING_ENABLED=false',
    });

    expect(routePanelState({ id: 'spring', available: false })).toEqual({
      kind: 'unavailable',
      label: 'Unavailable',
      reason: 'required support is unavailable',
    });

    expect(routePanelState({ id: 'spring', available: false, unavailableReason: 'Custom unavailable' })).toEqual({
      kind: 'unavailable',
      label: 'Unavailable',
      reason: 'Custom unavailable',
    });

    expect(routePanelState({ id: 'spring', readOnly: true })).toEqual({
      kind: 'read-only',
      label: 'Read-only',
      reason: 'mutating actions are disabled',
    });

    expect(routePanelState({ id: 'spring', readOnly: true, readOnlyReason: 'Custom read only' })).toEqual({
      kind: 'read-only',
      label: 'Read-only',
      reason: 'Custom read only',
    });

    expect(routePanelState({ id: 'spring', enabled: true, available: true, readOnly: false })).toBeNull();
    expect(routePanelState(null)).toBeNull();
  });
});
