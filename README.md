# k6 Authoring Skills

Two [OpenCode](https://opencode.ai) agent skills for writing k6 test scripts, plus a comparison harness to measure accuracy and token cost.

## Skills

### `k6-create-mcp` — uses [mcp-k6](https://github.com/grafana/mcp-k6)

The agent looks up k6 documentation, type definitions, and validates scripts via the mcp-k6 MCP server.

**Requires:** mcp-k6 configured as an MCP server (e.g. via Docker):
```json
{ "mcpServers": { "k6": { "command": "docker", "args": ["run", "--rm", "-i", "grafana/mcp-k6"] } } }
```
Add to your `opencode.json` at project root.

### `k6-create-xk6docs` — uses [xk6-subcommand-docs](https://github.com/grafana/xk6-docs)

The agent works from a library of built-in example scripts (HTTP, WebSocket, gRPC, browser, functional, executors, cloud, and 8 xk6 extensions) and only calls `k6 x docs` when it needs something not covered by the examples.

**Requires:** a k6 binary with the xk6-docs extension:
```bash
xk6 build --with github.com/grafana/xk6-subcommand-docs@latest -o ./k6-with-docs
```
> Note: the GitHub repo is `xk6-docs` but the Go module path is `xk6-subcommand-docs`.

## Install

Copy the skills into your OpenCode skills directory:

```bash
cp -r .agents/skills/k6-create-mcp     ~/.agents/skills/
cp -r .agents/skills/k6-create-xk6docs ~/.agents/skills/
```

Then in any project, just ask your agent:

> *"Create a k6 load test for https://api.example.com/users with 10 VUs for 30s, p95 < 500ms"*

The right skill will be loaded automatically based on what's available.

## Comparison results

19 scenarios covering the full k6 ecosystem — HTTP, WebSocket, gRPC, browser, functional tests (k6-testing), all 7 executors, custom metrics, cloud run, and 8 xk6 extensions (faker, redis, sql, dns, tls, tcp, crawler, exec). All tests target [QuickPizza](https://quickpizza.grafana.com).

| Scenario | mcp valid | mcp BP | mcp tokens | xk6docs valid | xk6docs BP | xk6docs tokens |
|----------|:---------:|:------:|:----------:|:-------------:|:----------:|:--------------:|
| S1: HTTP basic load | ✅ | 10/10 | 35,378 | ✅ | 10/10 | 22,770 |
| S2: HTTP auth flow | ✅ | 10/10 | 38,005 | ✅ | 10/10 | 27,423 |
| S3: Ramping + custom metrics | ✅ | 10/10 | 40,102 | ✅ | 10/10 | 23,109 |
| S4: WebSocket | ✅ | 10/10 | 32,145 | ✅ | 10/10 | 21,073 |
| S5: gRPC | ✅ | 10/10 | 30,197 | ✅ | 10/10 | 20,610 |
| S6: Browser | ✅ | 10/10 | 44,525 | ✅ | 9/10 | 21,192 |
| S7: k6-testing functional | ✅ | 10/10 | 38,311 | ✅ | 10/10 | 23,457 |
| S8: k6/crypto + encoding | ✅ | 10/10 | 32,349 | ✅ | 10/10 | 22,788 |
| S9: HTML parsing + SharedArray | ✅ | 10/10 | 34,593 | ✅ | 10/10 | 21,690 |
| S10: execution + handleSummary | ✅ | 10/10 | 51,260 | ✅ | 10/10 | 23,154 |
| S11: xk6-faker | ✅ | 10/10 | 33,839 | ✅ | 10/10 | 24,061 |
| S12: xk6-redis | ✅ | 10/10 | 34,285 | ✅ | 10/10 | 21,248 |
| S13: xk6-sql + sqlite3 | ✅ | 10/10 | 26,809 | ✅ | 10/10 | 22,564 |
| S14: xk6-dns + tls + tcp | ✅ | 10/10 | 38,279 | ✅ | 10/10 | 23,913 |
| S15: Dinner-time peak (ramping) | ✅ | 10/10 | 48,754 | ✅ | 10/10 | 23,542 |
| S16: Constant arrival rate | ✅ | 10/10 | 33,466 | ✅ | 9/10 | 22,226 |
| S17: k6 cloud run | ✅ | 10/10 | 38,942 | ✅ | 10/10 | 20,096 |
| S18: k6 cloud --local-execution | ✅ | 10/10 | 36,911 | ✅ | 9/10 | 21,884 |
| S19: Browser functional (login flow) | ✅ | 10/10 | 58,409 | ✅ | 10/10 | 95,591 |
| **Total / average** | **18/19 pass** | **9.95/10** | **711k** | **18/19 pass** | **9.84/10** | **518k** |

**xk6docs uses ~27% fewer tokens overall.** Both skills produce scripts that pass k6 validation and score 9.8–10/10 on the best-practices checklist.

### Best-practices checklist (`bp-check.py`)

Each generated script is scored against 10 rules:

| Rule | Check |
|------|-------|
| R1 | `export const options` exists |
| R2 | `thresholds` defined |
| R3 | `check()` or `expect()` assertions |
| R4 | `sleep()` for think time (load tests) |
| R5 | No placeholder code |
| R6 | No deprecated `k6/ws` import |
| R7 | Browser: `try/finally` with `page.close()` |
| R8 | gRPC: `client.close()` called |
| R9 | No mutable top-level `let`/`var` |
| R10 | Exported test function(s) present |

## Running the comparison

```bash
# Prerequisites
brew install k6 xk6 jq python3
docker pull grafana/mcp-k6

# Build the xk6-docs binary (note: Go module is xk6-subcommand-docs)
xk6 build --with github.com/grafana/xk6-subcommand-docs@latest -o /tmp/k6-with-docs

# Run all 19 scenarios against both skills
export ANTHROPIC_API_KEY=<your-key>
bash compare.sh

# Run a single scenario
bash compare.sh --scenario 19
bash compare.sh --scenario 6 --skill k6-create-xk6docs

# Check a script against best practices
python3 bp-check.py k6/scripts/my-test.js
```

Results are written to `results/comparison-<timestamp>.md`.

## What's covered

| Area | Modules / Extensions |
|------|---------------------|
| Protocols | HTTP/2, WebSocket, gRPC, Browser |
| Assertions | `check()`, k6-testing `expect()` |
| Executors | constant-vus, ramping-vus, constant-arrival-rate, ramping-arrival-rate, per-vu-iterations, shared-iterations, externally-controlled |
| Metrics | Counter, Gauge, Rate, Trend |
| Lifecycle | setup, teardown, handleSummary, SharedArray |
| Cloud | `k6 cloud run`, `--local-execution` |
| xk6 extensions | faker, redis, sql/sqlite3, exec, dns, tls, tcp, crawler |
