/// <reference types="vitest/config" />
import react from '@vitejs/plugin-react';
import { defineConfig } from 'vite';

// In development Vite serves the app and proxies /api to `riso serve --port 8001`.
// The build goes to ../riso/web/dist, which `riso serve` serves at / (git-ignored).
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: { '/api': 'http://localhost:8001' },
  },
  build: {
    outDir: '../riso/web/dist',
    emptyOutDir: true,
  },
  test: {
    environment: 'jsdom',
    setupFiles: ['./src/test/setup.ts'],
    include: ['src/**/*.test.{ts,tsx}'],
    restoreMocks: true,
    unstubGlobals: true,
    // The tests render the whole app in jsdom and are CPU-bound: one worker per logical core
    // (two per physical one) only slows each test towards the 5 s timeout without finishing
    // sooner. Half the cores ran as fast, the slowest test at 3.1 s instead of 4.5 s.
    maxWorkers: '50%',
  },
});
