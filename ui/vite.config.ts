import { svelte } from '@sveltejs/vite-plugin-svelte';
import { defineConfig } from 'vitest/config';

// sharpit serves the build under its own CSP (script-src 'self', no inline script, no eval).
export default defineConfig(({ mode }) => ({
  plugins: [svelte()],
  base: './', // relative asset URLs: the UI works under any mount path
  // component tests mount in jsdom, so they need Svelte's browser build, not its server one
  resolve: mode === 'test' ? { conditions: ['browser'] } : undefined,
  build: {
    outDir: '../src/sharpit/ui/static',
    emptyOutDir: true,
    assetsInlineLimit: 0, // no data: URIs; every asset is a file
    modulePreload: { polyfill: false }, // the polyfill is an inline script the CSP would block
    rolldownOptions: {
      // the adapter serves only a flat assets/{file}: no subdirectories
      output: {
        entryFileNames: 'assets/[name]-[hash].js',
        chunkFileNames: 'assets/[name]-[hash].js',
        assetFileNames: 'assets/[name]-[hash][extname]',
      },
    },
  },
  test: {
    environment: 'node',
    include: ['tests/unit/**/*.test.ts', 'tests/component/**/*.test.ts'],
  },
}));
