<script lang="ts">
  import Traces from '../../src/views/Traces.svelte';
  import { panel } from './support';
  import type { Panel } from '../../src/lib/types';

  let currentPanel = $state<Panel>(panel('traces', { readOnly: false }));

  export function updatePanel(newPanel: Panel) {
    currentPanel = newPanel;
  }
</script>

<Traces panel={currentPanel} />
