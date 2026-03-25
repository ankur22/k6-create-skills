/**
 * k6 browser example — k6/browser
 *
 * Covers: browser.newPage(), goto(), getBy* APIs, locator(), click(),
 *         waitFor(), waitForLoadState(), check(), try/finally page.close(),
 *         shared-iterations scenario with browser options
 *
 * ELEMENT SELECTION — use getBy* APIs as the first choice:
 *   page.getByRole('button', { name: 'Submit' })  ← preferred for interactive elements
 *   page.getByLabel('Username')                    ← preferred for labelled inputs
 *   page.getByText('Rated!')                       ← preferred for text content
 *   page.getByTestId('pizza-btn')                  ← preferred when data-testid exists
 *   page.getByPlaceholder('Enter email')           ← preferred for placeholder inputs
 *   page.locator('#id')                            ← fallback: stable ID attribute
 *   page.locator('[data-test="x"]')               ← fallback: custom data attribute
 *   page.locator('button[type="submit"]')          ← fallback: unambiguous attribute
 *   page.locator('button').first()                 ← last resort only — no context
 *   page.locator('//xpath')                        ← avoid: fragile, hard to read
 *
 * IMPORTANT:
 * - Default function MUST be async.
 * - Do NOT use --vus or --iterations CLI flags — the options.scenarios block
 *   controls load for browser scripts.
 * - browser options go inside the scenario, not at the top level.
 *
 * BROWSER BEST PRACTICES (look up via k6 x docs before reviewing a script):
 *   $DOCS_CMD using-k6-browser/recommended-practices/select-elements
 *   $DOCS_CMD using-k6-browser/recommended-practices/handle-dynamic-elements
 *   $DOCS_CMD using-k6-browser/recommended-practices/sleep-vs-page-wait-for-timeout
 *   $DOCS_CMD using-k6-browser/recommended-practices/clean-up-test-resources-page-close
 *   $DOCS_CMD using-k6-browser/recommended-practices/prevent-cookie-banners-blocking
 *   $DOCS_CMD using-k6-browser/recommended-practices/prevent-too-many-time-series-error
 *   $DOCS_CMD using-k6-browser/recommended-practices/hybrid-approach-to-performance
 *   $DOCS_CMD using-k6-browser/recommended-practices/page-object-model-pattern
 *   $DOCS_CMD using-k6-browser/recommended-practices/simulate-user-input-delay
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
    await page.goto('https://quickpizza.grafana.com');
    await page.waitForLoadState('networkidle');

    // ── getByRole: preferred for buttons, links, headings, inputs ────────────
    // Matches by ARIA role + accessible name — resilient to DOM restructuring.
    const pizzaBtn = page.getByRole('button', { name: 'Pizza, Please!' });
    await pizzaBtn.waitFor({ state: 'visible', timeout: 5000 });
    await pizzaBtn.click();
    await page.waitForLoadState('networkidle');

    // ── getByText: preferred for asserting visible text ───────────────────────
    const recommendation = page.getByText('Our recommendation:');
    await recommendation.waitFor({ state: 'visible', timeout: 10000 });

    // ── getByRole again for the rating button ─────────────────────────────────
    await page.getByRole('button', { name: 'Love it!' }).click();

    // ── getByText to assert transient confirmation ────────────────────────────
    const rated = page.getByText('Rated!');
    await rated.waitFor({ state: 'visible', timeout: 5000 });

    check(await rated.isVisible(), {
      'rated confirmation visible': (v) => v === true,
    });

    // ── Fallback to locator() only when no getBy* applies ────────────────────
    // e.g. stable ID or unambiguous attribute selector:
    // const input = page.locator('#username');
    // const submit = page.locator('button[type="submit"]');

  } finally {
    // Always close the page — even if the test throws
    await page.close();
  }
}
