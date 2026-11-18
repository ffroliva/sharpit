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
