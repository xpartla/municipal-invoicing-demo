import { defineConfig, devices } from '@playwright/test';

/**
 * E2E journeys against the real backend serving the built SPA (plan §13.2). The global setup
 * starts `riso serve` on a free port with a temporary database; build the SPA first
 * (`pnpm build`, or `scripts/check.sh full`, which does both).
 */
export default defineConfig({
  testDir: './e2e',
  globalSetup: './e2e/global-setup.ts',
  fullyParallel: true,
  forbidOnly: Boolean(process.env.CI),
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? [['list'], ['html', { open: 'never' }]] : [['list']],
  use: {
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    locale: 'sk-SK',
    timezoneId: 'Europe/Bratislava',
  },
  // The three widths of plan §10.1: phone, tablet, desktop.
  projects: [
    {
      name: 'phone',
      use: { ...devices['Desktop Chrome'], viewport: { width: 390, height: 844 } },
    },
    {
      name: 'tablet',
      use: { ...devices['Desktop Chrome'], viewport: { width: 820, height: 1180 } },
    },
    {
      name: 'desktop',
      use: { ...devices['Desktop Chrome'], viewport: { width: 1280, height: 800 } },
    },
  ],
});
