---
name: k6-create-xk6docs
description: Generate and validate k6 load test, functional, and protocol test scripts using the xk6-docs CLI for documentation lookup. Covers HTTP, WebSocket, gRPC, browser, all executors, custom metrics, k6-testing library, cloud execution, and the full xk6 extension ecosystem. Use when writing any k6 script and the xk6-docs k6 binary is available (k6 x docs). Does not require mcp-k6.
license: MIT
compatibility: opencode
---

# k6 Script Generation (xk6-docs)

## Step 0: Establish your docs command (do this first, every time)

As of **k6 v1.7.0**, the docs subcommand is auto-provisioned — no manual binary build required. Try in order:

**1. Try without a version flag first (preferred — uses the bundle matching your k6 version):**
```bash
k6 x docs 2>&1 | head -1
```

**2. If that returns a 404 error, fall back to the previous version:**
```bash
k6 x docs --version v1.6.1 2>&1 | head -1
```

**3. If neither works (older k6 binary), try the locally-built binary:**
```bash
./k6-with-docs x docs 2>&1 | head -1
```

> k6 v1.7.0 auto-downloads the docs binary on first run (~30s); subsequent calls are instant from cache.

Set `DOCS_CMD` to the first command that returns a topic list:

| Result | `DOCS_CMD` |
|--------|-----------|
| Step 1 succeeds | `k6 x docs` |
| Step 1 fails with 404, Step 2 succeeds | `k6 x docs --version v1.6.1` |
| Only Step 3 works | `./k6-with-docs x docs` |
| All fail | **Web fallback** via `WebFetch` against `https://grafana.com/docs/k6/latest/`. Read `SETUP.md`. |

Do not skip doc lookups — use web fallback if the subcommand is unavailable.

---

## Step 1: Pick the right example file

Read only the file that matches the user's request. Examples provide structural scaffolding — the correct scaffold, option shapes, and import patterns.

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

Example files: `~/.agents/skills/k6-create-xk6docs/examples/`

---

## Step 2: Adapt the example

Use the loaded example as the starting point. Adapt it to the user's exact requirements:
- Change endpoints, VU counts, durations, thresholds
- Add or remove scenario steps
- Rename functions and variables to match the domain
- Every expression must be complete and runnable — no `{ ... }`, `// TODO`, or stubs

For multi-scenario scripts (browser + HTTP, cloud): use named `scenarios` with `exec` pointing to separate exported functions.

---

## Step 3: Fill gaps with docs

The example covers common patterns. Adapt from it directly. **Only reach for docs if**:
- The user asks for an API or option not demonstrated in the example, **or**
- You are not confident about the exact signature, option name, or return type

When a gap exists, use `DOCS_CMD`:

```bash
# With CLI subcommand:
$DOCS_CMD <path>              # e.g. javascript-api k6-http
$DOCS_CMD <path> --depth 2
$DOCS_CMD search <term>

# With web fallback:
WebFetch https://grafana.com/docs/k6/latest/javascript-api/k6-http/
WebFetch https://grafana.com/docs/k6/latest/using-k6/scenarios/
```

Common CLI paths and the 2-call strategy are in `docs-guidance.md`.
Common web URL patterns: `https://grafana.com/docs/k6/latest/<path>/`

**Do not use unpkg, @types/k6, or any npm type definition URLs.**

---

## Step 4: Save

```bash
mkdir -p k6/scripts
```

Before writing the file, get the current UTC timestamp by trying these commands in order — use the output of the first one that succeeds:

```bash
# 1. Node.js (most developer machines)
node -e "console.log(new Date().toISOString())"

# 2. Python 3
python3 -c "import datetime; print(datetime.datetime.now(datetime.timezone.utc).isoformat(timespec='milliseconds').replace('+00:00', 'Z'))"

# 3. Perl (pre-installed on macOS and most Linux)
perl -e 'use POSIX; use Time::HiRes qw(gettimeofday); my($s,$u)=gettimeofday(); printf POSIX::strftime("%Y-%m-%dT%H:%M:%S.",gmtime($s)).sprintf("%03dZ",$u/1000)'

# 4. PowerShell (Windows)
powershell -Command "[DateTime]::UtcNow.ToString('yyyy-MM-ddTHH:mm:ss.fffZ')"

# 5. Last resort — BSD date (macOS/Linux, no real milliseconds)
date -u +"%Y-%m-%dT%H:%M:%S.000Z"
```

> **Note:** Do NOT use `date -u +"%Y-%m-%dT%H:%M:%S.%3NZ"` — `%3N` is Linux-only and produces literal `3NZ` on macOS.

Replace `{{GENERATED_AT}}` on line 1 of the script with the timestamp output. The result should read:

```
// Generated by k6-create-xk6docs on 2026-03-25T22:02:20.203Z
```

Then save to `k6/scripts/<descriptive-name>.js` via the Write tool. Lowercase kebab-case.

---

## Step 5: Validate

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

```bash
# With CLI:   $DOCS_CMD best-practices
# With web:   WebFetch https://grafana.com/docs/k6/latest/using-k6/
```

Key checks:
- `export const options` with realistic VUs/duration and `thresholds`
- `sleep()` for think time in load tests (not needed in browser/functional scripts)
- `check()` or `expect()` assertions on every response
- Browser scripts: `try/finally` with `page.close()` in `finally`
- gRPC scripts: `client.close()` after each iteration
- No `let`/`var` at top level (use `const`)
- No deprecated imports (`k6/ws` → `k6/experimental/websockets`)

### Browser scripts — recommended practices

If the script imports `k6/browser`, look up each topic using `DOCS_CMD`:

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

Key points:

- **Use `getBy*` APIs as the first choice for element selection** — they are more readable and resilient than CSS/XPath strings:
  - `page.getByRole('button', { name: 'Submit' })` — preferred for interactive elements
  - `page.getByLabel('Username')` — preferred for form inputs
  - `page.getByText('Rated!')` — preferred for text content
  - `page.getByTestId('pizza-btn')` — preferred when `data-testid` attributes exist
  - `page.getByPlaceholder('Enter email')` — preferred for inputs with placeholders
  - Fall back to `page.locator('#id')` or `page.locator('[data-test="x"]')` only when no semantic `getBy*` applies
  - Avoid generic `page.locator('button')` (no context) and absolute XPath
- **Dynamic elements**: use `locator.waitFor({ state: 'visible' })` after navigation, not just `waitForLoadState()`
- **User delays**: use `page.waitForTimeout()` not `sleep()` in browser scripts
- **Page cleanup**: `page.close()` must be in a `finally` block
- **Cookie banners**: dismiss consent dialogs before interacting
- **Time series**: avoid high-cardinality tags on browser metrics

If issues found: fix and re-validate. Minor style issues: note but do not re-validate.

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
