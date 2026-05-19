# Browser Recommended Practices

Apply these checks to any script that imports `k6/browser`.

If you are uncertain about any topic, look it up using `DOCS_CMD` (establish it per Step 3 in SKILL.md if not yet set):

```bash
# With CLI:
$DOCS_CMD using-k6-browser/recommended-practices/select-elements
$DOCS_CMD using-k6-browser/recommended-practices/handle-dynamic-elements
$DOCS_CMD using-k6-browser/recommended-practices/sleep-vs-page-wait-for-timeout
$DOCS_CMD using-k6-browser/recommended-practices/clean-up-test-resources-page-close
$DOCS_CMD using-k6-browser/recommended-practices/prevent-cookie-banners-blocking
$DOCS_CMD using-k6-browser/recommended-practices/prevent-too-many-time-series-error
$DOCS_CMD using-k6-browser/recommended-practices/hybrid-approach-to-performance
$DOCS_CMD using-k6-browser/recommended-practices/page-object-model-pattern
$DOCS_CMD using-k6-browser/recommended-practices/simulate-user-input-delay

# Web fallback — fetch with whatever capability your agent has (built-in fetch, or curl):
# https://grafana.com/docs/k6/latest/using-k6-browser/recommended-practices/<topic>/
```

---

## Element selection — use `getBy*` APIs first

More readable and resilient than CSS/XPath:

- `page.getByRole('button', { name: 'Submit' })` — preferred for interactive elements
- `page.getByLabel('Username')` — preferred for form inputs
- `page.getByText('Rated!')` — preferred for text content
- `page.getByTestId('pizza-btn')` — preferred when `data-testid` attributes exist
- `page.getByPlaceholder('Enter email')` — preferred for inputs with placeholders
- Fall back to `page.locator('#id')` or `page.locator('[data-test="x"]')` only when no `getBy*` applies
- Avoid generic `page.locator('button')` (no context) and absolute XPath

## Locator actionability — no `waitFor()` before interactions

Locator APIs (`click()`, `fill()`, `selectOption()`, etc.) have built-in actionability checks. They automatically wait for the element to be visible, enabled, and stable. **Do not call `waitFor()` before an action** — it is redundant and adds unnecessary coupling.

```javascript
// ✅ correct — actionability check is built in
await page.getByRole('button', { name: 'Submit' }).click();

// ❌ wrong — waitFor() before an interaction is redundant
await page.getByRole('button', { name: 'Submit' }).waitFor({ state: 'visible' });
await page.getByRole('button', { name: 'Submit' }).click();
```

`waitFor()` is only appropriate when asserting an element's state **without** interacting with it (e.g., checking that a confirmation message appeared).

## No `waitForLoadState()` after navigation or clicks

Do not call `waitForLoadState()` after `page.goto()` or after clicking a link/button. Instead, interact directly with the first element you expect on the new page — the locator's actionability checks handle the waiting automatically.

```javascript
// ✅ correct — just interact with what you expect next
await page.goto('https://example.com/login');
await page.getByLabel('Username').fill('user');

// ❌ wrong — waitForLoadState adds a slow, brittle wait
await page.goto('https://example.com/login');
await page.waitForLoadState('networkidle');
await page.getByLabel('Username').fill('user');
```

## Assertions — use `expect()` from k6-testing, not `check()`

k6-testing `expect()` provides auto-retrying matchers purpose-built for browser locators. They replace the verbose `waitFor()` → `isVisible()` → `check()` anti-pattern:

```javascript
import { expect } from 'https://jslib.k6.io/k6-testing/0.6.1/index.js';

// ✅ correct — one line, auto-retries until visible or timeout
await expect(page.getByText('Rated!')).toBeVisible();
await expect(page.locator('#result')).toContainText('Success');
await expect(page).toHaveTitle(/Dashboard/);

// ❌ wrong — verbose, redundant (if waitFor succeeds, isVisible is always true)
const el = page.getByText('Rated!');
await el.waitFor({ state: 'visible', timeout: 5000 });
check(await el.isVisible(), { 'visible': (v) => v === true });
```

Available retrying matchers:
- `toBeVisible()`, `toBeHidden()`, `toBeEnabled()`, `toBeChecked()`
- `toHaveText(text)`, `toContainText(text)`
- `toHaveAttribute(name, value)`, `toHaveValue(value)`
- `toHaveTitle(titleOrRegex)` (on page objects)

Use `expect()` for browser correctness assertions. If you need metric-tracked `check()` in an async browser context (e.g. hybrid protocol + browser scripts), import the async-compatible version from k6-utils — the standard `check` from `k6` does not work in async functions:

```javascript
// ✅ async-compatible check — works inside async browser functions
import { check } from 'https://jslib.k6.io/k6-utils/1.5.0/index.js';

// ❌ standard check — does NOT work in async contexts
// import { check } from 'k6';
```

Prefer `expect()` for assertions. Use async `check()` from k6-utils only when you specifically need k6 metric tracking (e.g. `checks` rate threshold) on a value obtained inside an async browser function.

## Other rules

- **User delays**: use `page.waitForTimeout()` not `sleep()` in browser scripts
- **Page cleanup**: `page.close()` must be in a `finally` block
- **Cookie banners**: dismiss consent dialogs before interacting
- **Time series**: avoid high-cardinality tags on browser metrics

If issues found: fix and re-validate. Minor style issues: note but do not re-validate.
