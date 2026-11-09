import { defineConfig, devices } from '@playwright/test';
import { mkdtempSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

// E2E runs against real servers on loopback only. Default ports differ from the
// `make dev` defaults (8000/5173) so a parallel dev session cannot collide.
const LOOPBACK = '127.0.0.1';

function readPort(name: string, fallback: number): number {
  const raw = process.env[name]?.trim();
  if (!raw) {
    return fallback;
  }
  if (!/^\d+$/.test(raw) || Number(raw) < 1 || Number(raw) > 65535) {
    throw new Error(`${name} must be a TCP port number, got "${raw}"`);
  }
  return Number(raw);
}

const backendPort = readPort('DUNVYR_E2E_BACKEND_PORT', 8100);
const frontendPort = readPort('DUNVYR_E2E_FRONTEND_PORT', 5273);
const frontendURL = `http://${LOOPBACK}:${frontendPort}`;
const databaseDirectory = mkdtempSync(join(process.env.TMPDIR ?? tmpdir(), 'dunvyr-e2e-'));
process.on('exit', () => rmSync(databaseDirectory, { recursive: true, force: true }));

export default defineConfig({
  testDir: './e2e',
  // The two smoke projects share one backend process and one database. Each
  // browser context is its own concurrent client, so scenarios run serially to
  // avoid cross-project write contention in the E2E database.
  workers: 1,
  use: {
    baseURL: frontendURL,
  },
  projects: [
    {
      name: 'smoke-desktop',
      use: {
        browserName: 'chromium',
        viewport: { width: 1280, height: 720 },
      },
    },
    {
      name: 'smoke-mobile',
      use: {
        ...devices['Pixel 5'],
        browserName: 'chromium',
      },
    },
  ],
  webServer: [
    {
      // Private transient file: QueuePool avoids the named-memory URL's
      // SingletonThreadPool eviction of connections still used by worker threads.
      command: `mise exec -- uv run uvicorn --factory dunvyr.main:create_app --host ${LOOPBACK} --port ${backendPort}`,
      cwd: '../backend',
      env: {
        DUNVYR_DATABASE_URL: `sqlite+pysqlite:///${join(databaseDirectory, 'e2e.db')}`,
        DUNVYR_AUTO_MIGRATE: '1',
        DUNVYR_ALLOWED_ORIGINS: `http://${LOOPBACK}:${frontendPort}`,
        // Never inherit a live provider into browser checks.
        DUNVYR_NARRATION_PROVIDER: 'fake',
        DUNVYR_NARRATION_FAKE_FAIL_FIRST: process.env.DUNVYR_E2E_NARRATION_FAIL_FIRST ?? '0',
      },
      url: `http://${LOOPBACK}:${backendPort}/health`,
      reuseExistingServer: false,
      timeout: 120_000,
    },
    {
      // reuses the DUNVYR_DEV_HOST contract of vite.config.ts; --strictPort keeps
      // a busy port an explicit failure instead of a silent fallback port.
      command: `mise exec -- npm run dev -- --port ${frontendPort} --strictPort`,
      cwd: '.',
      env: {
        DUNVYR_DEV_HOST: LOOPBACK,
        DUNVYR_BACKEND_ORIGIN: `http://${LOOPBACK}:${backendPort}`,
      },
      url: `${frontendURL}/`,
      reuseExistingServer: false,
      timeout: 120_000,
    },
  ],
});
