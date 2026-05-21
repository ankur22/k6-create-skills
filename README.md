# k6 Authoring Skills

[OpenCode](https://opencode.ai) agent skills for writing k6 test scripts, plus a comparison harness to measure accuracy and token cost.

## Skills

### `mcp-k6` — raw [mcp-k6](https://github.com/grafana/mcp-k6) MCP server (no skill)

No skill wrapper — the agent uses the mcp-k6 MCP server tools directly (docs lookup, validation, execution) with no orchestration instructions. This tests whether the MCP server is self-sufficient.

**Requires:** mcp-k6 configured as an MCP server (e.g. via Docker):
```json
{ "mcpServers": { "k6": { "command": "docker", "args": ["run", "--rm", "-i", "grafana/mcp-k6"] } } }
```
Add to your `opencode.json` at project root.

### `k6-create-xk6docs` — uses [xk6-subcommand-docs](https://github.com/grafana/xk6-docs)

The agent works from built-in example scripts and uses `k6 x docs` to fill any gaps. Browser tests also get the full recommended-practices review via the docs CLI.

**Requires:** k6 v1.7.0+ (auto-provisions the docs subcommand on first use — no manual build):
```bash
k6 x docs   # works out of the box with k6 v1.7.0+
```

> On first run k6 auto-downloads the extension binary (~30s), then serves from cache.
> If you get a 404 error, fall back to `k6 x docs --version v1.6.1`.

If you're on an older k6, build the binary manually:
```bash
xk6 build --with github.com/grafana/xk6-subcommand-docs@latest -o ./k6-with-docs
```

## Install

**Via [skills.sh](https://skills.sh) (recommended):**

```bash
# Install both skills
npx skills add ankur22/k6-create-skills

# Install the xk6docs skill only
npx skills add ankur22/k6-create-skills --skill k6-create-xk6docs

# Install the grafana-k6 skill only
npx skills add ankur22/k6-create-skills --skill grafana-k6
```

**Manually:**

```bash
cp -r .agents/skills/k6-create-xk6docs ~/.agents/skills/
cp -r .agents/skills/grafana-k6        ~/.agents/skills/
```

For the raw mcp-k6 condition (no skill), just configure the MCP server in `opencode.json` — no skill installation needed.

Then in any project, just ask your agent:

> *"Create a k6 load test for https://api.example.com/users with 10 VUs for 30s, p95 < 500ms"*

The right skill is loaded automatically based on what's configured.

## Comparison results

**29 scenarios × 3 conditions.** All tests target [QuickPizza](https://quickpizza.grafana.com).

| Condition | Valid | BP Score (avg) | Tokens (avg) | LLM Judge (avg /25) |
|-----------|:-----:|:--------------:|:------------:|:-------------------:|
| **mcp-k6** (raw, no skill) | 29/29 | 9.7/10 | ~59k | 24.0 |
| **k6-create-xk6docs** | 28/28 | 9.9/10 | ~34k | 24.2 |
| **grafana-k6** | 29/29 | 9.7/10 | ~41k | 24.2 |

Quality is a three-way tie (24.0–24.2/25). The raw MCP server is self-sufficient but costs 74% more tokens than xk6docs. The pure skill (grafana-k6) matches MCP quality with no external dependencies.

### Best-practices checker (`bp-check.py`)

Each generated script is scored against categorized static checks. The JSON output keeps
`score`, `max`, and `issues` for the comparison table, and adds per-category detail for
judge input and debugging:

| Category | Purpose |
|----------|---------|
| `validity` | Script file exists |
| `best_practices` | General k6 script hygiene |
| `protocol_specific` | Browser, WebSocket, and gRPC-specific rules |
| `prompt_adherence` | Scenario-manifest checks for representative scenarios |
| `artifacts` | Required file paths and generated artifacts such as screenshots |

General best-practice coverage includes:

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

Representative scenarios are also checked against `scenario-manifest.json` for exact
requirements. The current manifest covers S1, S4, S5, S19, and S27.

The LLM judge reads `validation.txt` and `bp.json` from each run directory and applies
hard caps for deterministic failures, such as missing scripts, failed validation,
missing requested artifacts, missing assertions, missing thresholds, or cleanup that is
not guaranteed by `finally`.

## Running the comparison

```bash
# Prerequisites
brew install k6 xk6 jq python3
docker pull grafana/mcp-k6   # needed for the raw mcp-k6 condition

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

# Run all 29 scenarios against all 3 conditions (parallel execution)
export ANTHROPIC_API_KEY=<your-key>
bash compare.sh

# Run a single scenario
bash compare.sh --scenario 19
bash compare.sh --scenario 1 --skill mcp-k6

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
| Cloud | `k6 cloud run`, `--local-execution`, `cloud` options, multi-region |
| xk6 extensions | faker, redis, sql/sqlite3, exec, dns, tls, tcp, crawler |
| Browser best practices | All 9 recommended-practices topics auto-reviewed via `k6 x docs` |
