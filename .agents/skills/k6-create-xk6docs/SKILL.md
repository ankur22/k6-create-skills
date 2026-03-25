---
name: k6-create-xk6docs
description: Generate and validate k6 load test, functional, and protocol test scripts using the xk6-docs CLI for documentation lookup. Covers HTTP, WebSocket, gRPC, browser, all executors, custom metrics, k6-testing library, cloud execution, and the full xk6 extension ecosystem. Use when writing any k6 script and the xk6-docs k6 binary is available (k6 x docs). Does not require mcp-k6.
license: MIT
compatibility: opencode
---

# k6 Script Generation (xk6-docs)

## Step 0: Check prerequisites (do this first, every time)

```bash
k6 x docs 2>&1 | head -1
```

If that fails, try the locally-built binary:
```bash
./k6-with-docs x docs 2>&1 | head -1
```

- **If either succeeds**: note which command works (`k6 x docs` or `./k6-with-docs x docs`) — use that exact command for all doc lookups. Read `docs-guidance.md` in this skill's directory for how to use it efficiently.
- **If both fail**: read `SETUP.md` in this skill's directory, inform the user, and offer to build `./k6-with-docs`. Continue in **examples-only mode** — skip all doc lookups and work entirely from the example files.

---

## Step 1: Pick the right example file

Read only the file that matches the user's request.

| User needs | Read this file |
|-----------|---------------|
| HTTP REST, auth flow, batch requests | `examples/http.js` |
| HTML parsing with parseHTML, SharedArray | `examples/html.js` |
| WebSocket | `examples/websocket.js` |
| gRPC | `examples/grpc.js` |
| Browser automation | `examples/browser.js` |
| Functional/integration tests, `expect()`, k6-testing | `examples/functional.js` |
| Custom metrics, execution module, handleSummary, per-vu-iterations | `examples/metrics.js` |
| Load patterns, all executors (ramping, arrival rate, per-VU, etc.) | `examples/executors.js` |
| Cloud run, `--local-execution`, `ext.loadimpact` | `examples/cloud.js` |
| Crypto (HMAC, MD5, SHA256) or encoding (base64) | `examples/crypto-encoding.js` |
| xk6-faker | `examples/ext-faker.js` |
| xk6-redis | `examples/ext-redis.js` |
| xk6-sql / sqlite3 / postgres | `examples/ext-sql.js` |
| xk6-exec | `examples/ext-exec.js` |
| xk6-dns | `examples/ext-dns.js` |
| xk6-tls | `examples/ext-tls.js` |
| xk6-tcp | `examples/ext-tcp.js` |
| xk6-crawler | `examples/ext-crawler.js` |

Example files live at: `~/.agents/skills/k6-create-xk6docs/examples/`

If the request spans multiple areas, read both relevant files.

---

## Step 2: Adapt the example

Use the loaded example as the starting point. Adapt it to the user's exact requirements:
- Change endpoints, VU counts, durations, thresholds
- Add or remove scenario steps
- Rename functions and variables to match the domain
- Every expression must be complete and runnable — no `{ ... }`, `// TODO`, or stubs

For multi-scenario scripts (browser + HTTP, cloud): use named `scenarios` with `exec` pointing to separate exported functions.

---

## Step 3: Use docs only when the example is not enough

**Default: do not call the docs command.** The examples cover all common patterns. Adapt from them directly.

**Only reach for docs if** the user explicitly asks for an API, option, or feature that is not demonstrated in the example you loaded — and you cannot confidently infer the correct usage from the example alone.

When you do need docs, follow `docs-guidance.md` (in this skill's directory). Target 2 calls maximum.

---

## Step 4: Save

```bash
mkdir -p k6/scripts
```

Save to `k6/scripts/<descriptive-name>.js` via the Write tool. Lowercase kebab-case.

---

## Step 5: Validate

Detect the script type and choose the right command:

| Script type | Command |
|------------|---------|
| Imports `k6/browser` | `k6 run k6/scripts/<name>.js` |
| Has named `executor:` blocks | `k6 run k6/scripts/<name>.js` |
| Has `ramping-vus` or `*-arrival-rate` only | `k6 inspect k6/scripts/<name>.js` |
| Everything else (HTTP, WS, gRPC) | `k6 run --vus 1 --iterations 1 k6/scripts/<name>.js` |

If validation fails: read stderr, fix the root cause, retry up to **3 attempts**. After 3 failures, present the error and ask the user how to proceed.

---

## Step 6: Best-practices review

### General checks (all scripts)

If `./k6-with-docs x docs best-practices` is available, run it and review the script against the output. Otherwise check directly:

- `export const options` with realistic VUs/duration and `thresholds` defined
- `sleep()` between iterations for load tests (skip for browser/functional scripts)
- `check()` or `expect()` assertions on every response
- Browser scripts use `try/finally` with `page.close()` in the `finally` block
- gRPC scripts call `client.close()` after each iteration
- No `let`/`var` at top level (use `const`; mutable globals contaminate across VUs)
- No deprecated imports (`k6/ws` → `k6/experimental/websockets`)

### Browser scripts — fetch the full recommended practices

If the script imports `k6/browser`, look up each of the following topics and
review the generated script against them:

```
./k6-with-docs x docs using-k6-browser/recommended-practices/select-elements
./k6-with-docs x docs using-k6-browser/recommended-practices/handle-dynamic-elements
./k6-with-docs x docs using-k6-browser/recommended-practices/sleep-vs-page-wait-for-timeout
./k6-with-docs x docs using-k6-browser/recommended-practices/clean-up-test-resources-page-close
./k6-with-docs x docs using-k6-browser/recommended-practices/prevent-cookie-banners-blocking
./k6-with-docs x docs using-k6-browser/recommended-practices/prevent-too-many-time-series-error
./k6-with-docs x docs using-k6-browser/recommended-practices/hybrid-approach-to-performance
./k6-with-docs x docs using-k6-browser/recommended-practices/page-object-model-pattern
./k6-with-docs x docs using-k6-browser/recommended-practices/simulate-user-input-delay
```

Key points to check:
- **Selectors**: prefer `aria-label`, `data-test-*`, or XPath text over generic tags or class names
- **Dynamic elements**: use `locator.waitFor()` after navigation, not just `waitForLoadState()`
- **sleep vs waitForTimeout**: use `page.waitForTimeout()` to simulate user delays in browser scripts; `sleep()` blocks the event loop
- **Page cleanup**: `page.close()` must be in a `finally` block, never in a conditional path
- **Cookie banners**: dismiss consent dialogs before interacting if the site shows them
- **Time series**: avoid tagging browser metrics with high-cardinality values

If issues are found: fix and re-validate. Minor style issues: note but do not re-validate.

---

## Step 7: Present results

1. Full script with file path
2. Validation output
3. Best-practices notes (issues found, or "all checks passed")
4. Suggested run command

```bash
k6 run --vus 10 --duration 30s k6/scripts/api-load-test.js
k6 run k6/scripts/browser-test.js
k6 cloud run k6/scripts/cloud-test.js
k6 cloud run --local-execution k6/scripts/hybrid-test.js
./k6-with-faker run k6/scripts/faker-test.js
K6_BROWSER_HEADLESS=true k6 run k6/scripts/browser-test.js
```

## Step 8: Execute

If the user confirms, run the command.
