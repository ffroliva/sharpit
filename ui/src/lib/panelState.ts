import type { Panel } from './types';

export function panelDisabledReason(panel: { id?: string } | null | undefined): string {
  const id = panel?.id ? panel.id.toUpperCase().replace(/-/g, '_') : 'PANEL';
  return `Panel is disabled via SHARPIT_PANELS_${id}_ENABLED=false`;
}

export function panelActionReason(panel: Partial<Panel> | null | undefined): string | null {
  if (!panel) return 'Action permissions are unavailable. Wait for panel availability or retry loading it.';
  if (panel.enabled === false) return panelDisabledReason(panel);
  if (panel.available === false) return panel.unavailableReason || 'This panel is not available.';
  if (panel.readOnly === true) return panel.readOnlyReason || 'This panel is read-only.';
  if (panel.readOnly !== false) return 'Action permissions are unavailable for this panel.';
  return null;
}

export interface RoutePanelState {
  kind: 'disabled' | 'unavailable' | 'read-only';
  label: 'Disabled' | 'Unavailable' | 'Read-only';
  reason: string;
}

// ported: panelNavigation.js::routePanelState
export function routePanelState(panel: Partial<Panel> | null | undefined): RoutePanelState | null {
  if (panel?.enabled === false) {
    return {
      kind: 'disabled',
      label: 'Disabled',
      reason: panelDisabledReason(panel),
    };
  }
  if (panel?.available === false) {
    return {
      kind: 'unavailable',
      label: 'Unavailable',
      reason: panel.unavailableReason || 'required support is unavailable',
    };
  }
  if (panel?.readOnly === true) {
    return {
      kind: 'read-only',
      label: 'Read-only',
      reason: panel.readOnlyReason || 'mutating actions are disabled',
    };
  }
  return null;
}
