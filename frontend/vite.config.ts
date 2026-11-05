import react from '@vitejs/plugin-react';
import { defineConfig } from 'vitest/config';

// LAN mode is explicit opt-in: set DUNVYR_DEV_HOST to a LAN IP or "0.0.0.0".
// The default stays on localhost until firewall and allowed origins are configured.
const devHost = process.env.DUNVYR_DEV_HOST?.trim() || false;

// The browser always calls /api on the Vite origin; Vite proxies it to the
// backend, so cookies and Origin checks stay same-origin from any LAN host.
const backendOrigin = process.env.DUNVYR_BACKEND_ORIGIN?.trim() || 'http://127.0.0.1:8000';

export default defineConfig({
  plugins: [react()],
  server: {
    host: devHost,
    proxy: {
      '/api': {
        target: backendOrigin,
        ws: true,
      },
    },
  },
  test: {
    environment: 'jsdom',
    setupFiles: ['./src/test/setup.ts'],
    // Unit tests live in src/; Playwright specs live in e2e/ and must not run here.
    include: ['src/**/*.test.{ts,tsx}'],
    css: false,
  },
});
