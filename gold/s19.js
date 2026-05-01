import { expect } from 'https://jslib.k6.io/k6-testing/0.6.1/index.js';
import { browser } from 'k6/browser';

export const options = {
  scenarios: {
    default: {
      executor: 'shared-iterations',
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
    await page.screenshot({ path: 'screenshots/1-homepage.png' })

    await page.getByRole('link', { name: 'Login' }).click();
    await page.screenshot({ path: 'screenshots/2-login.png' })
    
    await page.locator("#username").fill("default");
    await page.screenshot({ path: 'screenshots/3-fill-username.png' })
    await page.locator("#password").fill("12345678");
    await page.screenshot({ path: 'screenshots/4-fill-password.png' })

    await page.getByRole("button", { name: "Sign in", exact: true }).click();
    await page.screenshot({ path: 'screenshots/5-login-submit.png' })

    await page.getByRole('link', { name: 'Back to main page' }).click();
    await page.screenshot({ path: 'screenshots/6-login-submit-back.png' })

    await page.getByRole("button", { name: "Pizza, Please!", exact: true }).click();
    await page.screenshot({ path: 'screenshots/7-pizza-please.png' })

    await page.getByRole("button", { name: "Love it!", exact: true }).click();
    await page.screenshot({ path: 'screenshots/8-rated.png' })

    await expect(page.locator("#rate-result")).toContainText("Rated!");
    await page.screenshot({ path: 'screenshots/9-see-rated.png' })
  } finally {
    await page.close()
  }
}
