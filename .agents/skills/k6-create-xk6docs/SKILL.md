---
name: k6-create-xk6docs
description: Generate and validate k6 load test, functional, and protocol test scripts, using the xk6-docs CLI (with grafana.com web fallback) for documentation lookup. Covers HTTP, WebSocket, gRPC, browser, all executors, custom metrics, k6-testing library, cloud execution, and the full xk6 extension ecosystem. Use whenever the user asks to write, generate, or validate any kind of k6 or load-test script — including when they describe the goal in plain language ("load test this API", "stress test my service") without naming k6 explicitly. Does not require mcp-k6; prefer this skill when mcp-k6 is not configured.
license: MIT
---

# k6 Script Generation (xk6-docs)

> **Efficiency note:** This is a short linear recipe (read example → adapt → save → validate → review). A todo list would just mirror the headings without adding value, so skip the planning overhead and execute the steps directly.
>
> **Agent-agnostic:** The steps below describe capabilities, not specific tools. Where a step says "fetch a URL" or "write a file", use whatever your agent provides for that capability (e.g. a web-fetch tool, a file-write tool, or shell `curl`/`tee`).

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
| Browser + functional test / `expect()` / k6-testing | `examples/functional.js` (browser scenario) |
| Functional/integration tests, `expect()`, k6-testing | `examples/functional.js` |
| Custom metrics, execution module, handleSummary, per-vu-iterations | `examples/metrics.js` |
| Load patterns, all executors (ramping, arrival rate, per-VU, etc.) | `examples/executors.js` |
| Cloud run, `--local-execution`, `cloud` options | `examples/cloud.js` |
| Crypto (HMAC, MD5, SHA256) or encoding (base64) | `examples/crypto-encoding.js` |
| xk6-faker | `examples/ext-faker.js` |
| xk6-redis | `examples/ext-redis.js` |
| xk6-sql / sqlite3 / postgres | `examples/ext-sql.js` |
| xk6-exec | `examples/ext-exec.js` |
| xk6-dns | `examples/ext-dns.js` |
| xk6-tls | `examples/ext-tls.js` |
| xk6-tcp | `examples/ext-tcp.js` |
| xk6-crawler | `examples/ext-crawler.js` |

Example files live in the `examples/` directory alongside this `SKILL.md`.

**When the request matches multiple rows** (e.g. "browser" + "functional test"), prefer the row whose assertion style fits the intent. If the user says "functional test", "assert", "verify", or "expect", use `functional.js` even if the test involves a browser — it demonstrates `expect()` with auto-retrying browser matchers. Use `browser.js` for browser load/performance tests that don't emphasize correctness assertions.

---

## Step 2: Adapt the example

Use the loaded example as the starting point. Adapt it to the user's exact requirements:
- Change endpoints, VU counts, durations, thresholds
- Add or remove scenario steps
- Rename functions and variables to match the domain
- Every expression must be complete and runnable — no `{ ... }`, `// TODO`, or stubs

For multi-scenario scripts (browser + HTTP, cloud): use named `scenarios` with `exec` pointing to separate exported functions.

---

## Step 3: Fill gaps with docs (only if needed)

The example covers common patterns. Adapt from it directly. **Skip this step entirely** if the example provides everything you need.

**Only reach for docs if**:
- The user asks for an API or option not demonstrated in the example, **or**
- You are not confident about the exact signature, option name, or return type

When a gap exists, first establish the docs command (one-time per session).

The `k6 x docs` CLI renders content only when it detects a TTY. Since agents
run non-interactively, wrap every call with `script` to allocate a pseudo-TTY
and pipe the ANSI-stripped content to stdout:

```bash
# Detect OS once (macOS vs Linux have different `script` flags):
if [[ "$(uname -s)" == "Darwin" ]]; then
  DOCS_CMD="script -q /dev/null k6 x docs"
else
  DOCS_CMD="script -qc 'k6 x docs' /dev/null"
fi

# Verify it works — should print a topic list, NOT a "browse files" guide:
$DOCS_CMD 2>/dev/null | head -5
```

If the output still shows "k6 documentation is a directory of markdown files",
the TTY wrapper isn't working. Fall back to **web docs** under
`https://grafana.com/docs/k6/latest/` — fetch pages with whatever web-fetch
capability your agent has (a built-in fetch tool, or `curl` in a shell).

Then look up what you need:

```bash
$DOCS_CMD <path>              # e.g. javascript-api k6-http
$DOCS_CMD <path> --depth 2
$DOCS_CMD search <term>
```

Common CLI paths and the 2-call strategy are in `docs-guidance.md`.

**Do not use unpkg, @types/k6, or any npm type definition URLs.**

---

## Step 4: Save

Line 1 of every script must be a generated-by comment. Get the timestamp and write the file in two parallel calls:

```bash
node -e "console.log(new Date().toISOString())"
```

Then include it as line 1:
```javascript
// Generated by k6-create-xk6docs on 2026-03-25T22:02:20.203Z
```

Save to `k6/scripts/<descriptive-name>.js`. Use lowercase kebab-case filenames. If your file-write capability doesn't create parent directories automatically, `mkdir -p k6/scripts` first.

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

Review the script against the rules below. The checklist is authoritative — only look up docs (`$DOCS_CMD best-practices` or `https://grafana.com/docs/k6/latest/using-k6/`) if you're uncertain about a specific rule.

- **`export const options` with realistic VUs/duration.** Default VUs/durations make the test meaningful out of the box.
- **Define `thresholds` for every load test.** Without thresholds the run can't fail in CI even when performance regresses, which defeats the point of running a load test. At minimum include `http_req_duration` and `http_req_failed` (or the protocol equivalent). Pure functional tests — single-iteration `expect()`-only scripts — can skip this.
- **Include `sleep()` in every load test.** `sleep()` represents user think time; without it, VUs hammer endpoints faster than any real user would, inflating throughput and crowding out the system under test. This applies to HTTP, WebSocket, gRPC, crypto, extension scripts, and all executor types. Browser scripts use `page.waitForTimeout()` instead, and single-iteration functional tests can skip it.
- **Assert every response.** **Browser scripts**: use `expect()` from k6-testing — it auto-retries against locators and replaces `waitFor()` + `isVisible()` + `check()` chains. If you need metric-tracked `check()` inside an async browser function, import from `https://jslib.k6.io/k6-utils/1.5.0/index.js` — the standard `check` from `k6` does NOT work in async contexts. **HTTP/gRPC/WS scripts**: use `check()` for metric-tracked assertions, or `expect()` for functional tests. Silent failures are worse than loud ones.
- **Browser scripts:** wrap interactions in `try/finally` with `page.close()` in `finally`, so pages clean up even when assertions throw.
- **gRPC scripts:** call `client.close()` after each iteration to release the connection.
- **No `let`/`var` at top level** — use `const`, since module-scope state is shared across VUs and mutability there is almost always a bug.
- **No deprecated imports** — `k6/ws` is replaced by `k6/experimental/websockets`.

### Browser scripts — recommended practices

If the script imports `k6/browser`, read `browser-best-practices.md` and apply all checks. Fix issues and re-validate.

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
