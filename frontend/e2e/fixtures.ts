import AxeBuilder from '@axe-core/playwright';
import { test as base, expect, type Page } from '@playwright/test';

/**
 * The fixtures every spec uses:
 * - `baseURL` is the server the global setup started;
 * - the page fails the test on any console error or uncaught exception. The browser also logs
 *   every 4xx answer as an error; those from `/api/` are the API answering as designed (a 401
 *   before the login, a 422 for a form), so they are left out. 5xx answers and failed assets
 *   still fail the test;
 * - `checkA11y` runs axe for WCAG 2.1 A and AA (plan §10.1), once running transitions end.
 */

interface Fixtures {
  checkA11y: (page?: Page) => Promise<void>;
}

export const test = base.extend<Fixtures>({
  baseURL: async ({}, use) => {
    const url = process.env.RISO_E2E_URL;
    if (!url) throw new Error('RISO_E2E_URL is not set; the global setup did not run');
    await use(url);
  },

  page: async ({ page }, use) => {
    const problems: string[] = [];
    page.on('console', (message) => {
      if (message.type() !== 'error') return;
      const text = message.text();
      const apiClientError =
        /^Failed to load resource: the server responded with a status of 4\d\d/.test(text) &&
        new URL(message.location().url || 'http://x/').pathname.startsWith('/api/');
      if (!apiClientError) problems.push(`console: ${text}`);
    });
    page.on('pageerror', (error) => problems.push(`page: ${error.message}`));
    await use(page);
    expect(problems, 'the page logged errors').toEqual([]);
  },

  checkA11y: async ({ page }, use) => {
    await use(async (target = page) => {
      // After `emulateMedia`, Mantine applies the scheme in an effect: wait until the page
      // shows the emulated one (up to a second; a scheme chosen with the toggle wins), then two
      // frames, so the colour transitions it starts are running before they are awaited below
      // (CI caught a segmented control's labels half-way to the dark colours).
      await target.evaluate(async () => {
        const wanted = matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
        const until = performance.now() + 1000;
        while (
          document.documentElement.getAttribute('data-mantine-color-scheme') !== wanted &&
          performance.now() < until
        ) {
          await new Promise((resolve) => setTimeout(resolve, 20));
        }
        await new Promise((resolve) => {
          requestAnimationFrame(() => requestAnimationFrame(resolve));
        });
      });
      // A dialog or menu that is still fading in has blended colours; axe would measure
      // the contrast of a half-transparent button. Let running transitions finish first
      // (not the endless ones, such as a loader's spin). One cancelled meanwhile (a menu
      // closing as a dialog opens) has ended too: its `finished` rejects with an AbortError.
      const settle = () =>
        target.evaluate(() =>
          Promise.all(
            document
              .getAnimations()
              .filter((animation) => animation.effect?.getComputedTiming().endTime !== Infinity)
              .map((animation) => animation.finished.catch(() => undefined)),
          ),
        );
      const analyze = () =>
        new AxeBuilder({ page: target })
          .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'])
          .analyze();
      await settle();
      let results = await analyze();
      // A fade that began after the wait above (a toast closing on its timer) shows blended
      // colours for a moment. Contrast is a property of the settled page: when it is the only
      // finding, let the running transitions end and look once more. A real one stays.
      if (
        results.violations.length > 0 &&
        results.violations.every((v) => v.id === 'color-contrast')
      ) {
        await settle();
        await target.waitForTimeout(250);
        results = await analyze();
      }
      const found = results.violations.map((v) => {
        const where = v.nodes
          .slice(0, 5)
          .map((node) => node.target.join(' '))
          .join(', ');
        return `${v.id} (${v.impact ?? 'unknown'}): ${v.help} — ${String(v.nodes.length)} node(s): ${where}`;
      });
      expect(found, 'axe violations').toEqual([]);
    });
  },
});

export { expect };

/** Whether the page scrolls sideways, which no screen should at any of our widths. */
export async function scrollsHorizontally(page: Page): Promise<boolean> {
  return page.evaluate(
    () => document.documentElement.scrollWidth > document.documentElement.clientWidth,
  );
}
