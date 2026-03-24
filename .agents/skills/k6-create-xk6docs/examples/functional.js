/**
 * k6 functional test example — k6-testing library
 *
 * Covers: expect() for HTTP assertions, expect(page/locator) for browser
 *         with automatic retry, multi-scenario script with named exec functions,
 *         HTTP + browser in the same script
 *
 * Use this pattern for functional/integration tests instead of check().
 * expect() on browser locators/pages automatically retries until timeout.
 *
 * Key matchers:
 *   HTTP values (instant): toEqual, toBe, toContain, toBeDefined, toBeTruthy,
 *                          toBeGreaterThan, toBeLessThan, toHaveLength, toHaveProperty
 *   Browser (retrying):    toBeVisible, toBeHidden, toBeEnabled, toBeChecked,
 *                          toHaveText, toContainText, toHaveAttribute, toHaveValue,
 *                          toHaveTitle (on page objects)
 *   Non-throwing:          expect.soft(value).toEqual(...) — collects all failures
 */
import { expect } from 'https://jslib.k6.io/k6-testing/0.6.1/index.js';
import { browser } from 'k6/browser';
import http from 'k6/http';

const BASE_URL = 'https://quickpizza.grafana.com';

export const options = {
  scenarios: {
    http_functional: {
      executor: 'shared-iterations',
      vus: 1,
      iterations: 1,
      exec: 'httpTest',
    },
    browser_functional: {
      executor: 'shared-iterations',
      vus: 1,
      iterations: 1,
      exec: 'browserTest',
      options: {
        browser: { type: 'chromium' },
      },
    },
  },
};

// ── HTTP functional test ──────────────────────────────────────────────────────
export function httpTest() {
  const res = http.get(`${BASE_URL}/api/quotes`);

  // Instant assertions (no retry)
  expect(res.status).toEqual(200);
  expect(res.json('quotes')).toBeDefined();
  expect(res.timings.duration).toBeLessThan(2000);

  // Soft assertions — collects all failures instead of throwing on first
  expect.soft(res.headers['Content-Type']).toContain('application/json');
}

// ── Browser functional test ───────────────────────────────────────────────────
export async function browserTest() {
  const page = await browser.newPage();

  try {
    await page.goto(BASE_URL);

    // Page-level retrying assertion
    await expect(page).toHaveTitle(/QuickPizza/);

    // Element-level retrying assertions
    await expect(page.locator('body')).toBeVisible();

    // Click and verify result appears
    const btn = page.locator('button').first();
    await expect(btn).toBeVisible();
    await btn.click();

  } finally {
    await page.close();
  }
}
