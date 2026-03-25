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

The agent works from built-in example scripts and uses `k6 x docs` to fill any gaps. Browser tests also get the full recommended-practices review via the docs CLI.

**Requires:** k6 v1.7.0+ (auto-provisions the docs subcommand on first use — no manual build):
```bash
k6 x docs --version v1.6.1   # works out of the box with k6 v1.7.0+
```

> **Note:** `--version v1.6.1` is required until the v1.7.x doc bundle is published.
> On first run k6 auto-downloads the extension binary (~30s), then serves from cache.

If you're on an older k6, build the binary manually:
```bash
xk6 build --with github.com/grafana/xk6-subcommand-docs@latest -o ./k6-with-docs
```

## Install

Copy the skills into your OpenCode skills directory:

```bash
cp -r .agents/skills/k6-create-mcp     ~/.agents/skills/
cp -r .agents/skills/k6-create-xk6docs ~/.agents/skills/
```

Then in any project, just ask your agent:

> *"Create a k6 load test for https://api.example.com/users with 10 VUs for 30s, p95 < 500ms"*

The right skill is loaded automatically based on what's configured.

## Comparison results

**20 scenarios — 40/40 pass.** All tests target [QuickPizza](https://quickpizza.grafana.com).

| Scenario | mcp valid | mcp BP | mcp tokens | xk6docs valid | xk6docs BP | xk6docs tokens |
|----------|:---------:|:------:|:----------:|:-------------:|:----------:|:--------------:|
| S1: HTTP basic load | ✅ | 10/10 | 32,891 | ✅ | 10/10 | 24,974 |
| S2: HTTP auth flow | ✅ | 10/10 | 29,500 | ✅ | 10/10 | 25,149 |
| S3: Ramping + custom metrics | ✅ | 10/10 | 45,603 | ✅ | 10/10 | 26,416 |
| S4: WebSocket | ✅ | 8/10 | 33,999 | ✅ | 9/10 | 23,888 |
| S5: gRPC | ✅ | 10/10 | 30,038 | ✅ | 10/10 | 23,253 |
| S6: Browser | ✅ | 10/10 | 27,578 | ✅ | 9/10 | 24,865 |
| S7: k6-testing functional | ✅ | 10/10 | 62,132 | ✅ | 10/10 | 26,682 |
| S8: k6/crypto + encoding | ✅ | 10/10 | 42,456 | ✅ | 10/10 | 23,910 |
| S9: HTML parsing + SharedArray | ✅ | 10/10 | 38,931 | ✅ | 10/10 | 24,742 |
| S10: execution + handleSummary | ✅ | 10/10 | 46,252 | ✅ | 9/10 | 25,164 |
| S11: xk6-faker | ✅ | 10/10 | 34,872 | ✅ | 10/10 | 41,252 |
| S12: xk6-redis | ✅ | 10/10 | 33,856 | ✅ | 10/10 | 26,784 |
| S13: xk6-sql + sqlite3 | ✅ | 10/10 | 37,265 | ✅ | 9/10 | 22,352 |
| S14: xk6-dns + tls + tcp | ✅ | 10/10 | 33,592 | ✅ | 10/10 | 27,339 |
| S15: Dinner-time peak (ramping) | ✅ | 10/10 | 46,425 | ✅ | 10/10 | 24,589 |
| S16: Constant arrival rate | ✅ | 9/10 | 41,771 | ✅ | 10/10 | 29,115 |
| S17: k6 cloud run | ✅ | 10/10 | 51,922 | ✅ | 10/10 | 21,807 |
| S18: k6 cloud --local-execution | ✅ | 9/10 | 45,024 | ✅ | 9/10 | 22,907 |
| S19: Browser login flow | ✅ | 10/10 | 84,846 | ✅ | 9/10 | 42,296 |
| S20: Binary file download | ✅ | 9/10 | 69,957 | ✅ | 9/10 | 46,001 |
| **Total / average** | **20/20** | **9.75/10** | **869k** | **20/20** | **9.65/10** | **553k** |

**xk6docs uses 36% fewer tokens overall.** Both skills produce scripts that pass k6 validation with near-identical best-practices scores (9.65 vs 9.75 out of 10).

### Best-practices checker (`bp-check.py`)

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

# Build extension binaries (for xk6 extension scenarios)
xk6 build --with github.com/grafana/xk6-faker@latest -o /tmp/k6-faker
xk6 build --with github.com/grafana/xk6-redis@latest \
           --with github.com/grafana/xk6-exec@latest  -o /tmp/k6-extensions
xk6 build --with github.com/grafana/xk6-dns@latest  \
           --with github.com/grafana/xk6-tls@latest  \
           --with github.com/grafana/xk6-tcp@latest  \
           --with github.com/grafana/xk6-crawler@latest -o /tmp/k6-net-extensions
CGO_ENABLED=1 xk6 build --with github.com/grafana/xk6-sql@latest \
           --with github.com/grafana/xk6-sql-driver-sqlite3@latest -o /tmp/k6-sql-sqlite

# Run all 20 scenarios against both skills (parallel execution)
export ANTHROPIC_API_KEY=<your-key>
bash compare.sh

# Run a single scenario
bash compare.sh --scenario 19
bash compare.sh --scenario 1 --skill k6-create-xk6docs

# Check a script against best practices
python3 bp-check.py k6/scripts/my-test.js
```

Results are written to `results/comparison-<timestamp>.md`.

## What's covered

| Area | Modules / Extensions |
|------|---------------------|
| Protocols | HTTP/2, WebSocket (`k6/experimental/websockets`), gRPC, Browser |
| Assertions | `check()`, k6-testing `expect()` (with auto-retry for browser locators) |
| Executors | constant-vus, ramping-vus, constant-arrival-rate, ramping-arrival-rate, per-vu-iterations, shared-iterations, externally-controlled |
| Built-in modules | k6/metrics, k6/data, k6/execution, k6/crypto, k6/encoding, k6/html, k6/timers |
| Lifecycle | setup, teardown, handleSummary, SharedArray |
| Cloud | `k6 cloud run`, `--local-execution`, `ext.loadimpact` multi-region |
| xk6 extensions | faker, redis, sql/sqlite3, exec, dns, tls, tcp, crawler |
| Browser best practices | All 9 recommended-practices topics auto-reviewed via `k6 x docs` |
