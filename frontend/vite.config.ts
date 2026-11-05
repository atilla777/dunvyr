import react from '@vitejs/plugin-react';
import { defineConfig } from 'vitest/config';

// LAN mode is explicit opt-in: set DUNVYR_DEV_HOST to a LAN IP or "0.0.0.0".
// The default stays on localhost until firewall and allowed origins are configured.
const devHost = process.env.DUNVYR_DEV_HOST?.trim() || false;

export default defineConfig({
  plugins: [react()],
  server: {
    host: devHost,
  },
  test: {
    environment: 'jsdom',
    setupFiles: ['./src/test/setup.ts'],
    css: false,
  },
});
