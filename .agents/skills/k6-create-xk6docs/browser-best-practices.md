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

# With web fallback:
WebFetch https://grafana.com/docs/k6/latest/using-k6-browser/recommended-practices/<topic>/
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

## Other rules

- **User delays**: use `page.waitForTimeout()` not `sleep()` in browser scripts
- **Page cleanup**: `page.close()` must be in a `finally` block
- **Cookie banners**: dismiss consent dialogs before interacting
- **Time series**: avoid high-cardinality tags on browser metrics

If issues found: fix and re-validate. Minor style issues: note but do not re-validate.
