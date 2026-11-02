<script lang="ts">
  // 0.4 placeholder (lane F): the owning lane replaces this file when it flips its panels04 flags.
  import type { Panel } from '../lib/types';

  let { panel }: { panel: Panel } = $props();
</script>

<div class="empty"><p class="lead">{panel.title}</p><p>This panel's view is not built yet.</p></div>
