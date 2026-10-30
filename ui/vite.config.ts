import { svelte } from '@sveltejs/vite-plugin-svelte';
import { defineConfig } from 'vitest/config';

// sharpit serves the build under its own CSP (script-src 'self', no inline script, no eval).
export default defineConfig({
  plugins: [svelte()],
  base: './', // relative asset URLs: the UI works under any mount path
  build: {
    outDir: '../src/sharpit/ui/static',
    emptyOutDir: true,
    modulePreload: { polyfill: false }, // the polyfill is an inline script the CSP would block
  },
  test: {
    environment: 'node',
    include: ['tests/unit/**/*.test.ts'],
  },
});
