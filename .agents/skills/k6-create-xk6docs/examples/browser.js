/**
 * k6 browser example — k6/browser
 *
 * Covers: browser.newPage(), goto(), locator(), click(),
 *         waitForLoadState(), title(), check(), try/finally page.close(),
 *         shared-iterations scenario with browser options
 *
 * IMPORTANT:
 * - Default function MUST be async.
 * - Do NOT use --vus or --iterations CLI flags — the options.scenarios block
 *   controls load for browser scripts.
 * - browser options go inside the scenario, not at the top level.
 *
 * BROWSER BEST PRACTICES (look up via k6 x docs before reviewing a script):
 *   ./k6-with-docs x docs using-k6-browser/recommended-practices/select-elements
 *   ./k6-with-docs x docs using-k6-browser/recommended-practices/handle-dynamic-elements
 *   ./k6-with-docs x docs using-k6-browser/recommended-practices/sleep-vs-page-wait-for-timeout
 *   ./k6-with-docs x docs using-k6-browser/recommended-practices/clean-up-test-resources-page-close
 *   ./k6-with-docs x docs using-k6-browser/recommended-practices/prevent-cookie-banners-blocking
 *   ./k6-with-docs x docs using-k6-browser/recommended-practices/prevent-too-many-time-series-error
 *   ./k6-with-docs x docs using-k6-browser/recommended-practices/hybrid-approach-to-performance
 *   ./k6-with-docs x docs using-k6-browser/recommended-practices/page-object-model-pattern
 *   ./k6-with-docs x docs using-k6-browser/recommended-practices/simulate-user-input-delay
 */
import { browser } from 'k6/browser';
import { check } from 'k6';

export const options = {
  scenarios: {
    browser_test: {
      executor: 'shared-iterations',
      vus: 1,
      iterations: 1,
      maxDuration: '2m',
      options: {
        browser: { type: 'chromium' },
      },
    },
  },
};

export default async function () {
  const page = await browser.newPage();

  try {
    // Navigate and wait for the page to settle
    await page.goto('https://quickpizza.grafana.com');
    await page.waitForLoadState('networkidle');

    // Interact with page elements
    const firstButton = page.locator('button').first();
    await firstButton.waitFor({ state: 'visible', timeout: 5000 });
    await firstButton.click();

    // Wait for content to update after interaction
    await page.waitForLoadState('networkidle');

    // Assert page state
    const title = await page.title();
    check(title, {
      'page has title': (t) => t.length > 0,
    });

    // Element visibility check
    check(await page.locator('body').isVisible(), {
      'body visible': (v) => v === true,
    });

  } finally {
    // Always close the page — even if the test throws
    await page.close();
  }
}
