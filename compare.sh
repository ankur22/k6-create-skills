#!/usr/bin/env bash
# compare.sh — Compare k6-create-mcp and k6-create-xk6docs skills on accuracy and token cost.
#
# Usage:
#   ./compare.sh                   Run all scenarios against both skills
#   ./compare.sh --scenario N      Run only scenario N (1-30)
#   ./compare.sh --skill NAME      Run only one skill (k6-create-mcp, k6-create-xk6docs, or grafana-k6)
#   ./compare.sh --help            Show this help
#
# Requirements:
#   - k6 binary on PATH (standard k6 with xk6-docs for S1-S10, S15-S18)
#   - opencode CLI on PATH
#   - jq on PATH
#   - python3 on PATH
#   - Docker on PATH (for S5 gRPC, S12 Redis)
#   - xk6 binary for building extension binaries (first run builds them to /tmp/)
#
# Custom k6 binaries (built automatically on first run if xk6 is available):
#   /tmp/k6-faker           — S11 (xk6-faker)
#   /tmp/k6-extensions      — S12 (xk6-redis + xk6-exec)
#   /tmp/k6-sql-sqlite      — S13 (xk6-sql + sqlite3, requires CGO_ENABLED=1)
#   /tmp/k6-net-extensions  — S14 (xk6-dns + xk6-tls + xk6-tcp + xk6-crawler)
#
# Scenarios:
#   S1:  HTTP REST basic load (quickpizza.grafana.com)
#   S2:  HTTP auth flow (register, login, pizza, rate)
#   S3:  Ramping stages with custom Counter/Rate metrics
#   S4:  WebSocket (wss://quickpizza.grafana.com/ws)
#   S5:  gRPC (local quickpizza Docker on localhost:3334)
#   S6:  Browser (quickpizza.grafana.com UI)
#   S7:  k6-testing functional (HTTP + browser, expect() assertions)
#   S8:  k6/crypto + k6/encoding (request signing, base64)
#   S9:  k6/html + k6/data SharedArray (HTML parsing + shared data)
#   S10: k6/execution + handleSummary + per-vu-iterations executor
#   S11: xk6-faker (fake user data for quickpizza)
#   S12: xk6-redis + Docker Redis (cache quickpizza API responses)
#   S13: xk6-sql + sqlite3 (log test results to SQLite DB)
#   S14: xk6-dns + xk6-tls + xk6-tcp (infrastructure checks for quickpizza.grafana.com)
#   S15: Dinner-time peak ramping-vus (realistic takeaway load pattern)
#   S16: Constant arrival rate (constant-arrival-rate executor, 20 RPS)
#   S17: k6 cloud run script (generate only, cloud options)
#   S18: k6 cloud run --local-execution (hybrid, generate only)
#   S19: Browser login flow (functional test with screenshots)
#   S20: Binary file download (save to disk via xk6-exec)
#   S21: Smoke test (1 VU, 1 iteration, minimal)
#   S22: Environment variable parameterization
#   S23: CSV data-driven test (SharedArray, inline CSV)
#   S24: Groups and tags (synchronous HTTP only)
#   S25: Batch parallel requests (http.batch)
#   S26: Spike test (sudden traffic surge, ramping-vus)
#   S27: File upload (multipart form data)
#   S28: Custom handleSummary (multi-format export)
#   S29: Thresholds with abortOnFail
#   S30: Multi-stage stress test (breaking point)
#
# Output: results/comparison-<timestamp>.md

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
RESULTS_DIR="$SCRIPT_DIR/results"
TIMESTAMP=$(date +%Y%m%d-%H%M%S)
OUTPUT_FILE="$RESULTS_DIR/comparison-$TIMESTAMP.md"
SCRIPTS_DIR="$RESULTS_DIR/scripts-$TIMESTAMP"
PROTO_DIR="$SCRIPT_DIR/proto"

# Standard k6 binary (xk6-docs enhanced)
K6_DEFAULT="${K6_BIN:-k6}"

# xk6 extension binaries — built on demand
K6_FAKER="/tmp/k6-faker"
K6_EXTENSIONS="/tmp/k6-extensions"
K6_SQL_SQLITE="/tmp/k6-sql-sqlite"
K6_NET_EXTENSIONS="/tmp/k6-net-extensions"

# k6 binary with xk6-subcommand-docs (for xk6docs skill live doc lookups)
# Note: the GitHub repo is xk6-docs but the Go module is xk6-subcommand-docs
K6_WITH_DOCS="/tmp/k6-with-docs"

FILTER_SKILL=""
FILTER_SCENARIO=""
QUICKPIZZA_CONTAINER=""
REDIS_CONTAINER=""

# ── Per-scenario k6 binary ────────────────────────────────────────────────────

get_k6_binary() {
  case "$1" in
    11) echo "$K6_FAKER" ;;
    12) echo "$K6_EXTENSIONS" ;;
    13) echo "$K6_SQL_SQLITE" ;;
    14) echo "$K6_NET_EXTENSIONS" ;;
    20) echo "$K6_EXTENSIONS" ;; # needs xk6-exec for file writes
    *)  echo "$K6_DEFAULT" ;;
  esac
}

# ── Scenario definitions ──────────────────────────────────────────────────────

get_scenario() {
  case "$1" in
    1) cat <<'EOF'
Load test the QuickPizza REST API at https://quickpizza.grafana.com using k6/http. The test should:
- GET /api/quotes and check status is 200 and response body contains 'quotes'
- GET /api/names and check status is 200
Run with 5 VUs for 30 seconds. Add thresholds: p(95) of http_req_duration under 500ms and http_req_failed rate under 1%. Use check() for assertions. Include sleep(1) between iterations. Save to k6/scripts/quickpizza-basic-load.js.
EOF
    ;;
    2) cat <<'EOF'
Create a k6 script testing the QuickPizza authentication flow at https://quickpizza.grafana.com. The flow per VU:
1. POST /api/users with JSON {username, password} using a unique username (combine __VU and Date.now()). Expect status 201.
2. POST /api/users/token/login with JSON {username, password}. Expect status 200 with 'token' field.
3. POST /api/pizza (NOT GET) with Authorization header "Token <token>" and Content-Type application/json. Send null or {} as body. Expect status 200, response has pizza.id.
4. POST /api/ratings with JSON {stars: 5, pizza_id: <id>} and Authorization header. Expect status 201.
Use 3 VUs for 30 seconds. Use check() for all assertions. All JavaScript must be complete and runnable. Save to k6/scripts/quickpizza-auth-flow.js.
EOF
    ;;
    3) cat <<'EOF'
Create a k6 script with ramping stages testing https://quickpizza.grafana.com/api/quotes. Use a ramping-vus scenario with stages: ramp from 0 to 10 VUs over 30s, hold at 10 VUs for 1 minute, ramp down to 0 over 30s. Add custom metrics: a Counter named 'quote_requests' and a Rate named 'quote_success_rate'. Increment the counter on each request, add to the rate based on whether status is 200. Add thresholds: quote_success_rate > 95% and p(95) of http_req_duration under 800ms. Save to k6/scripts/quickpizza-ramp-metrics.js.
EOF
    ;;
    4) cat <<'EOF'
Create a k6 WebSocket test for QuickPizza. Use "import { WebSocket } from 'k6/experimental/websockets'" to connect to wss://quickpizza.grafana.com/ws. Each VU should:
1. Open a WebSocket connection
2. On 'open' event, send JSON { "ws_visitor_id": "VU_" + __VU, "msg": "order_pizza" }
3. On 'message' event, JSON.parse received data, log it, close connection
4. On 'error' event, log e.error (string property, not a method)
Use a shared-iterations scenario with 5 VUs and 10 iterations. The default function must be synchronous. Save to k6/scripts/quickpizza-websocket.js.
EOF
    ;;
    5) cat <<'EOF'
Create a k6 gRPC test for a local QuickPizza instance at localhost:3334 (plaintext). The proto file is at ./proto/quickpizza.proto relative to where k6 runs from — use client.load(['./proto'], 'quickpizza.proto'). Use 'import { Client, StatusOK } from "k6/net/grpc"'. Each iteration:
1. client.connect('localhost:3334', { plaintext: true })
2. Call quickpizza.GRPC/Status with {} — check StatusOK and message.ready === true
3. Call quickpizza.GRPC/RatePizza with { ingredients: ["Pepperoni", "Mozzarella"], dough: "Traditional" } — check StatusOK and starsRating between 1 and 5
4. client.close()
Use 3 VUs for 20 seconds. Threshold: p(95) grpc_req_duration under 500ms. Save to k6/scripts/quickpizza-grpc.js.
EOF
    ;;
    6) cat <<'EOF'
Create a k6 browser test for https://quickpizza.grafana.com using "import { browser } from 'k6/browser'". Use a shared-iterations scenario with 1 VU, 1 iteration, options: { browser: { type: 'chromium' } }. The async default function should:
1. const page = await browser.newPage()
2. await page.goto('https://quickpizza.grafana.com')
3. Click any visible button using page.locator('button').first().click()
4. Wait for page state using page.waitForLoadState('networkidle')
5. check() that page title is not empty
6. Close page in try/finally
Do NOT use --vus or --iterations flags; use options.scenarios. Save to k6/scripts/quickpizza-browser.js.
EOF
    ;;
    7) cat <<'EOF'
Create a k6 script testing QuickPizza using "import { expect } from 'https://jslib.k6.io/k6-testing/0.6.1/index.js'" with TWO scenarios:

Scenario 1 'http_functional' (shared-iterations, vus: 1, iterations: 1, exec: 'httpTest'):
- GET https://quickpizza.grafana.com/api/quotes
- expect(res.status).toEqual(200)
- expect(res.json('quotes')).toBeDefined()

Scenario 2 'browser_functional' (shared-iterations, vus: 1, iterations: 1, options: { browser: { type: 'chromium' } }, exec: 'browserTest'):
- import { browser } from 'k6/browser'
- await page.goto('https://quickpizza.grafana.com')
- await expect(page).toHaveTitle(/QuickPizza/) — retrying browser assertion
- await expect(page.locator('body')).toBeVisible() — retrying

Export named functions httpTest() and async browserTest(). browserTest: try/finally with page.close(). Save to k6/scripts/quickpizza-functional.js.
EOF
    ;;
    8) cat <<'EOF'
Create a k6 script demonstrating k6/crypto and k6/encoding with the QuickPizza API at https://quickpizza.grafana.com. The script should:
1. Import { hmac, md5, randomBytes } from 'k6/crypto' and encoding from 'k6/encoding'
2. For each iteration, generate a unique request ID using randomBytes(16) then encoding.b64encode()
3. Compute an HMAC-SHA256 signature of the request body using hmac('sha256', 'secret-key', body, 'hex')
4. Compute an MD5 hash of the response body
5. Encode Basic Auth credentials using encoding.b64encode('testuser:testpass')
6. Send a GET request to https://quickpizza.grafana.com/api/get with X-Request-ID and Authorization: Basic headers
7. Check status is 200 and verify the request ID is a non-empty string
Use 3 VUs for 20 seconds. Save to k6/scripts/quickpizza-crypto-encoding.js.
EOF
    ;;
    9) cat <<'EOF'
Create a k6 script that uses k6/html and k6/data SharedArray to test https://quickpizza.grafana.com. The script should:
1. Import { parseHTML } from 'k6/html' and { SharedArray } from 'k6/data'
2. Define a SharedArray named 'endpoints' with an inline array (not a file) of 3 endpoint paths: ['/api/quotes', '/api/names', '/api/adjectives']
3. In the default function: use __VU modulo the array length to pick an endpoint from the SharedArray
4. Fetch https://quickpizza.grafana.com + the chosen endpoint, check status 200
5. Also fetch https://quickpizza.grafana.com/login (NOT the root / which is a JavaScript SPA with no server-rendered elements) and parse it with parseHTML. Check that doc.find('button').size() > 0 — the /login page has a server-rendered submit button
6. Log the heading text using doc.find('h1').text()
Use 5 VUs for 30 seconds. Save to k6/scripts/quickpizza-html-data.js.
EOF
    ;;
    10) cat <<'EOF'
Create a k6 script that uses k6/execution and handleSummary with the per-vu-iterations executor testing https://quickpizza.grafana.com. The script should:
1. Import execution from 'k6/execution'
2. Use a per-vu-iterations scenario: 5 VUs, each running 3 iterations, maxDuration 2m
3. In the default function: use execution.vu.idInTest to log which VU is running, use execution.scenario.iterationInInstance for the iteration number
4. Fetch https://quickpizza.grafana.com/api/quotes, check status 200, tag request with { vu: String(execution.vu.idInTest) }
5. Implement handleSummary() that returns a custom summary to stdout showing total requests and success rate
Use check() for assertions. Save to k6/scripts/quickpizza-execution-summary.js.
EOF
    ;;
    11) cat <<'EOF'
Create a k6 script using the xk6-faker extension (import { Faker } from 'k6/x/faker') to generate fake user data for registering users on QuickPizza at https://quickpizza.grafana.com. The script should:
1. Create a Faker instance with seed 42: const fake = new Faker(42)
2. In each iteration, generate a fake username using fake.internet.username() but append __VU and Date.now() to make it unique
3. Use fake.internet.password() for the password (or a static one if the method doesn't exist — check by attempting a simple password)
4. Register the user via POST /api/users with JSON {username, password}, Content-Type application/json
5. Check status is 201 (created)
6. Also generate a fake name with fake.person.firstName() + ' ' + fake.person.lastName() and log it
Use 5 VUs for 20 seconds. Note: this script requires a k6 binary built with xk6-faker. Save to k6/scripts/quickpizza-faker.js.
EOF
    ;;
    12) cat <<'EOF'
Create a k6 script using the xk6-redis extension (import redis from 'k6/x/redis') to cache QuickPizza API responses in Redis. IMPORTANT: xk6-redis Client is instantiated with a URL string: new redis.Client('redis://localhost:6379') — do NOT use an options object. The script should:
1. Create client: const client = new redis.Client('redis://localhost:6379')
2. In each async default function iteration:
   a. Check Redis for cached response: const cached = await client.get('pizza:quotes')
   b. If cached: log 'cache hit', parse and use the cached value
   c. If not cached: fetch https://quickpizza.grafana.com/api/quotes, store response body in Redis with await client.set('pizza:quotes', res.body, 30) (30 second TTL)
3. Check that a value was obtained (either from cache or API), check status logic accordingly
4. Track cache hits with a Counter metric named 'cache_hits'
Use 5 VUs for 30 seconds. Note: requires k6 binary with xk6-redis AND a Redis instance on localhost:6379. Save to k6/scripts/quickpizza-redis-cache.js.
EOF
    ;;
    13) cat <<'EOF'
Create a k6 script using xk6-sql with the sqlite3 driver to log QuickPizza test results to a SQLite database. Import: "import sql from 'k6/x/sql'" and "import driver from 'k6/x/sql/driver/sqlite3'". IMPORTANT API: db.query() returns a plain JavaScript ARRAY of row objects (not a ResultSet with .next()). For example: const rows = db.query('SELECT count(*) as cnt FROM t'); console.log(rows[0].cnt). The script should:
1. Open a database: const db = sql.open(driver, '/tmp/quickpizza_results.db')
2. In setup(), create table: db.exec('DROP TABLE IF EXISTS results'); db.exec('CREATE TABLE results (id INTEGER PRIMARY KEY AUTOINCREMENT, endpoint TEXT, status INTEGER, duration REAL)')
3. In default function: fetch https://quickpizza.grafana.com/api/quotes, record with db.exec('INSERT INTO results (endpoint, status, duration) VALUES (?, ?, ?)', '/api/quotes', res.status, res.timings.duration)
4. check() that status is 200
5. In teardown(), query total: const rows = db.query('SELECT count(*) as cnt FROM results'); log 'Total recorded: ' + rows[0].cnt
Use 3 VUs for 20 seconds. Note: requires k6 binary with xk6-sql + xk6-sql-driver-sqlite3 built with CGO_ENABLED=1. Save to k6/scripts/quickpizza-sql-log.js.
EOF
    ;;
    14) cat <<'EOF'
Create a k6 script using xk6-dns, xk6-tls, and xk6-tcp extensions for infrastructure checks on quickpizza.grafana.com. The script should have THREE scenarios:

Scenario 1 'dns_check' (shared-iterations, 1 VU, 1 iteration, exec: 'dnsCheck'):
- import dns from 'k6/x/dns'
- IMPORTANT API: dns.lookup(host) uses the system DNS resolver (no nameserver needed). It returns a Promise: const ips = await dns.lookup('quickpizza.grafana.com')
- check that ips is not null and ips.length > 0
- The function must be async.

Scenario 2 'tls_check' (shared-iterations, 1 VU, 1 iteration, exec: 'tlsCheck'):
- import tls from 'k6/x/tls'
- IMPORTANT API: getCertificate takes only the hostname, NO port argument, and is async: const cert = await tls.getCertificate('quickpizza.grafana.com')
- cert.expires is a millisecond timestamp — check it is in the future: cert.expires > Date.now()
- The function must be async.

Scenario 3 'tcp_check' (shared-iterations, 1 VU, 1 iteration, exec: 'tcpCheck'):
- import tcp from 'k6/x/tcp'
- IMPORTANT API: use event-driven Socket: const socket = new tcp.Socket()
- socket.on('connect', () => { connected = true; socket.destroy(); })
- socket.on('error', (err) => { console.error(err); })
- Use a Promise to wait: await new Promise((resolve) => { socket.on('close', resolve); socket.connect(443, 'quickpizza.grafana.com'); })
- check the connected flag is true
- The function must be async.

Export async functions dnsCheck, tlsCheck, tcpCheck. Note: requires k6 binary with xk6-dns + xk6-tls + xk6-tcp. Save to k6/scripts/quickpizza-infra-checks.js.
EOF
    ;;
    15) cat <<'EOF'
Create a k6 script simulating a realistic dinner-time peak load on QuickPizza (https://quickpizza.grafana.com) using the ramping-vus executor. Model a takeaway website that gets quiet morning traffic, builds through the afternoon, peaks during dinner (7-8pm), then quiets down. Use these stages:
- 5 minutes ramp to 5 VUs (morning background)
- 10 minutes ramp to 20 VUs (afternoon ordering)
- 15 minutes ramp to 60 VUs (pre-dinner surge, 6-7pm)
- 20 minutes hold at 80 VUs (dinner peak, 7-8pm)
- 10 minutes ramp to 20 VUs (post-dinner)
- 5 minutes ramp to 0 (kitchen closes)
gracefulRampDown: '2m'. Each VU iteration: GET /api/quotes and POST /api/pizza (with Authorization: Token 'abc1234567890123' — 16 chars), check statuses. Add thresholds: p(95) http_req_duration < 1000ms, http_req_failed rate < 2%. Include sleep(1) between iterations. Save to k6/scripts/quickpizza-dinner-peak.js.
EOF
    ;;
    16) cat <<'EOF'
Create a k6 script using the constant-arrival-rate executor to simulate a steady stream of pizza orders at https://quickpizza.grafana.com. The scenario should maintain exactly 20 iterations per second for 2 minutes, with preAllocatedVUs: 40 and maxVUs: 100. Each iteration: GET /api/quotes, check status 200. Add thresholds: p(95) http_req_duration < 500ms, http_req_failed rate < 1%. Also add a second scenario using ramping-arrival-rate that starts at 5 RPS, ramps to 30 RPS over 1 minute, holds for 2 minutes, then ramps back to 0. Save to k6/scripts/quickpizza-arrival-rate.js.
EOF
    ;;
    17) cat <<'EOF'
Create a k6 cloud run script for QuickPizza that includes the cloud-specific options needed for k6 cloud run. The script should:
1. Export options with a top-level cloud configuration block: projectID: 1234567 (placeholder), name: 'QuickPizza Cloud Load Test', and a multi-region distribution with 60% in 'amazon:us:ashburn' and 40% in 'amazon:eu:dublin'
2. Use a ramping-vus scenario with stages: ramp to 50 VUs over 2 minutes, hold for 5 minutes, ramp down to 0 over 1 minute
3. Test https://quickpizza.grafana.com/api/quotes with check() and p(95) threshold
4. Add a comment at the top explaining how to run: 'k6 cloud login --token <TOKEN>' then 'k6 cloud run script.js'
This script is for cloud execution — do NOT include local validation attempts. Save to k6/scripts/quickpizza-cloud.js.
EOF
    ;;
    18) cat <<'EOF'
Create a k6 cloud run --local-execution script for QuickPizza. This runs the test locally but streams results to Grafana Cloud. The script should:
1. Include the same top-level cloud options as a cloud run script: projectID: 1234567, name: 'QuickPizza Hybrid Test'
2. Use a constant-arrival-rate scenario: 15 RPS for 3 minutes, preAllocatedVUs: 30, maxVUs: 100
3. Test POST /api/pizza at https://quickpizza.grafana.com with Authorization: Token 'abc1234567890123' (16 chars), check status 200
4. Add a comment at the top: to run: 'k6 cloud login --token <TOKEN>' then 'k6 cloud run --local-execution script.js'
5. Include a note in the script that --local-execution means the test runs on the local machine but results go to Grafana Cloud
This script validates locally. Save to k6/scripts/quickpizza-cloud-local-exec.js.
EOF
    ;;
    19) cat <<'EOF'
I want you to test https://quickpizza.grafana.com/. Click login. Login with the credentials that are in the page (default/12345678). Click on back to main page. Click on pizza please. Click love it. I want this to be a functional test, so make sure after clicking on love it you see "Rated!". Also ensure that there are screenshots in place after each call API call to capture what has happened.
EOF
    ;;
    20) cat <<'EOF'
We need to create an HTTP K6 test script. It should be one VU, one iteration. Its main job will be to download a binary (from https://github.com/grafana/k6/releases/download/v1.6.1/k6-v1.6.1-linux-amd64.deb) and save it to the local disk.
EOF
    ;;
    21) cat <<'EOF'
Create a minimal k6 smoke test for https://quickpizza.grafana.com/api/quotes. Use 1 VU, 1 iteration (via options, not CLI flags). GET the endpoint, check status 200 and that the response body is valid JSON. Add a threshold: p(95) http_req_duration under 1000ms. No sleep needed — this is a single-iteration smoke test. Save to k6/scripts/quickpizza-smoke.js.
EOF
    ;;
    22) cat <<'EOF'
Create a k6 script that reads configuration from environment variables. The script should:
1. Read __ENV.BASE_URL (default to 'https://quickpizza.grafana.com' if not set)
2. Read __ENV.AUTH_TOKEN (default to 'abc1234567890123' if not set)
3. Read __ENV.TARGET_VUS (parse as integer, default to 5)
4. Use these in a load test: GET ${BASE_URL}/api/quotes with Authorization: Token header
5. Also GET ${BASE_URL}/api/names
6. check() both responses for status 200
7. Add thresholds: p(95) http_req_duration < 500ms, http_req_failed rate < 1%
8. Use the VU count from __ENV.TARGET_VUS in options
9. Duration: 30 seconds, sleep(1) between iterations
Save to k6/scripts/quickpizza-env-params.js.
EOF
    ;;
    23) cat <<'EOF'
Create a k6 data-driven test using SharedArray with inline CSV data (not a file). The script should:
1. Import { SharedArray } from 'k6/data'
2. Define a SharedArray named 'endpoints' that returns an array of objects parsed from an inline CSV string using split/map (not papaparse). The CSV data:
   path,expected_status,description
   /api/quotes,200,Get pizza quotes
   /api/names,200,Get pizza names
   /api/adjectives,200,Get pizza adjectives
3. In each iteration, pick an endpoint using __VU and __ITER modulo the array length
4. Fetch https://quickpizza.grafana.com + the picked path
5. check() that status matches expected_status from the data row
6. Log the description field
7. Use 3 VUs for 30 seconds. Add thresholds: p(95) http_req_duration < 500ms. Include sleep(1).
Save to k6/scripts/quickpizza-data-driven.js.
EOF
    ;;
    24) cat <<'EOF'
Create a k6 load test for https://quickpizza.grafana.com that uses group() to organize requests and custom tags for filtering. IMPORTANT: group() only works in synchronous contexts — do NOT use it with browser or async APIs. The script should:
1. Import { group } from 'k6' and http from 'k6/http'
2. group('read_operations', () => { ... }) containing:
   - GET /api/quotes with tags: { name: 'quotes', operation: 'read' }
   - GET /api/names with tags: { name: 'names', operation: 'read' }
   - check() both for status 200
3. group('write_operations', () => { ... }) containing:
   - POST /api/pizza with Authorization: Token 'abc1234567890123', Content-Type: application/json, body: null
   - Tag with { name: 'pizza', operation: 'write' }
   - check() for status 200
4. Add tag-based thresholds: 'http_req_duration{operation:read}': ['p(95)<300'], 'http_req_duration{operation:write}': ['p(95)<800']
5. Use 5 VUs for 30 seconds. Include sleep(1).
Save to k6/scripts/quickpizza-groups-tags.js.
EOF
    ;;
    25) cat <<'EOF'
Create a k6 script that uses http.batch() to send parallel requests to https://quickpizza.grafana.com. The script should:
1. Use http.batch() to send 5 requests in parallel:
   - GET /api/quotes
   - GET /api/names
   - GET /api/adjectives
   - GET /api/quotes (second call)
   - GET /api/names (second call)
2. The batch call should use the array-of-arrays format: [['GET', url], ['GET', url], ...]
3. check() that all 5 responses have status 200
4. Add a custom Trend metric named 'batch_duration' that records the total time for the batch (measure Date.now() before and after)
5. Add thresholds: p(95) http_req_duration < 500ms, http_req_failed rate < 1%, batch_duration p(95) < 1000
6. Use 5 VUs for 30 seconds. Include sleep(1).
Save to k6/scripts/quickpizza-batch.js.
EOF
    ;;
    26) cat <<'EOF'
Create a k6 spike test for https://quickpizza.grafana.com/api/quotes simulating a sudden traffic surge. Use a ramping-vus executor with these stages:
- 10 seconds at 2 VUs (normal baseline)
- 10 seconds ramp to 200 VUs (instant spike)
- 30 seconds hold at 200 VUs (sustained spike)
- 10 seconds ramp down to 2 VUs (traffic drops)
- 30 seconds hold at 2 VUs (recovery)
- 10 seconds ramp to 0 (end)
Each iteration: GET /api/quotes, check status 200, check response contains 'quotes'. Add thresholds: p(95) http_req_duration < 2000ms (relaxed for spike), http_req_failed rate < 5%. Include sleep(0.5) for tight iteration pacing. Save to k6/scripts/quickpizza-spike.js.
EOF
    ;;
    27) cat <<'EOF'
Create a k6 script that uploads a file to https://quickpizza.grafana.com via multipart form data. The script should:
1. Use open() in init context to load a small text file. Since we don't have a real file, create one first: the script should use a setup-generated approach — but since open() only works in init, generate the bytes inline: const fileData = 'name,rating\nMargherita,5\nPepperoni,4\nHawaiian,3\n'
2. Use http.file(fileData, 'ratings.csv', 'text/csv') to create a file object
3. POST to https://quickpizza.grafana.com/api/ratings with the file as multipart form data, plus a field 'description' with value 'Pizza ratings upload'
4. check() that the response status is one of [200, 201, 400, 404] (the endpoint may not accept uploads, but the script must be valid k6)
5. Add thresholds: p(95) http_req_duration < 2000ms
6. Use 2 VUs for 20 seconds. Include sleep(1).
Save to k6/scripts/quickpizza-file-upload.js.
EOF
    ;;
    28) cat <<'EOF'
Create a k6 script that implements a custom handleSummary to export results in multiple formats. The script should:
1. GET https://quickpizza.grafana.com/api/quotes, check status 200
2. Add a custom Counter named 'successful_requests' — increment on status 200
3. Use 3 VUs for 20 seconds. Add thresholds: p(95) http_req_duration < 500ms
4. Implement handleSummary(data) that returns an object with:
   - 'stdout': a human-readable text summary showing total requests, success rate, p95 latency, and threshold pass/fail
   - '/tmp/quickpizza-summary.json': JSON.stringify(data) for the full raw summary
5. The stdout summary should format nicely with headers and aligned values, not just dump JSON
6. Include sleep(1).
Save to k6/scripts/quickpizza-custom-summary.js.
EOF
    ;;
    29) cat <<'EOF'
Create a k6 script that uses thresholds with abortOnFail to stop the test early if performance degrades. The script should:
1. GET https://quickpizza.grafana.com/api/quotes
2. check() status 200 and response body contains 'quotes'
3. Define thresholds with abortOnFail:
   - http_req_duration: [{ threshold: 'p(99)<3000', abortOnFail: true, delayAbortEval: '10s' }]
   - http_req_failed: [{ threshold: 'rate<0.1', abortOnFail: true, delayAbortEval: '10s' }]
   - checks: [{ threshold: 'rate>0.9', abortOnFail: true, delayAbortEval: '10s' }]
4. Also add non-aborting thresholds: p(95) http_req_duration < 500ms
5. Use a ramping-vus scenario: ramp from 0 to 10 VUs over 30s, hold at 10 for 1 minute, ramp to 0 over 30s
6. Include sleep(1).
Save to k6/scripts/quickpizza-abort-thresholds.js.
EOF
    ;;
    30) cat <<'EOF'
Create a k6 multi-stage stress test for https://quickpizza.grafana.com to find the breaking point. Use a ramping-vus executor with stages:
- 2 minutes ramp to 10 VUs (warm-up)
- 3 minutes ramp to 50 VUs (normal load)
- 3 minutes ramp to 100 VUs (heavy load)
- 3 minutes ramp to 200 VUs (stress)
- 3 minutes ramp to 300 VUs (breaking point)
- 5 minutes ramp to 0 (recovery)
gracefulRampDown: '2m'. Each iteration: GET /api/quotes and GET /api/names. check() both for status 200. Add thresholds: p(95) http_req_duration < 1500ms, p(99) < 3000ms, http_req_failed rate < 10%. Add a custom Rate metric named 'acceptable_latency' that tracks whether each request was under 500ms. Include sleep(1). Save to k6/scripts/quickpizza-stress-test.js.
EOF
    ;;
    *) echo "" ;;
  esac
}

# ── Argument parsing ──────────────────────────────────────────────────────────

usage() {
  awk '/^#!/{next} /^#/{print substr($0,3)} /^[^#]/{exit}' "$0"
  exit 0
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --help|-h)      usage ;;
    --skill)        FILTER_SKILL="$2";    shift 2 ;;
    --scenario)     FILTER_SCENARIO="$2"; shift 2 ;;
    *) echo "Unknown argument: $1" >&2; exit 1 ;;
  esac
done

# ── Dependency checks ─────────────────────────────────────────────────────────

check_deps() {
  local missing=""
  command -v k6       >/dev/null 2>&1 || missing="$missing k6"
  command -v opencode >/dev/null 2>&1 || missing="$missing opencode"
  command -v jq       >/dev/null 2>&1 || missing="$missing jq"
  command -v python3  >/dev/null 2>&1 || missing="$missing python3"
  command -v docker   >/dev/null 2>&1 || missing="$missing docker"
  if [[ -n "$missing" ]]; then
    echo "error: missing requirements:$missing" >&2; exit 1
  fi
}

# ── Extension binary management ───────────────────────────────────────────────

ensure_binary() {
  local binary="$1"; shift
  local label="$1"; shift
  local args=("$@")

  if [[ -f "$binary" ]]; then return 0; fi

  if ! command -v xk6 >/dev/null 2>&1; then
    echo "warning: xk6 not found, cannot build $label" >&2
    return 1
  fi

  echo "Building $label..." >&2
  if xk6 build "${args[@]}" -o "$binary" >/dev/null 2>&1; then
    echo "Built: $binary" >&2
  else
    echo "warning: failed to build $label" >&2
    return 1
  fi
}

ensure_all_binaries() {
  local scenarios="$1"
  for s in $scenarios; do
    case "$s" in
      11) ensure_binary "$K6_FAKER" "k6-faker" \
            --with github.com/grafana/xk6-faker@latest ;;
      12) ensure_binary "$K6_EXTENSIONS" "k6-extensions(redis+exec)" \
            --with github.com/grafana/xk6-redis@latest \
            --with github.com/grafana/xk6-exec@latest ;;
      13) CGO_ENABLED=1 ensure_binary "$K6_SQL_SQLITE" "k6-sql-sqlite" \
            --with github.com/grafana/xk6-sql@latest \
            --with github.com/grafana/xk6-sql-driver-sqlite3@latest || true ;;
      14) ensure_binary "$K6_NET_EXTENSIONS" "k6-net-extensions" \
            --with github.com/grafana/xk6-dns@latest \
            --with github.com/grafana/xk6-tls@latest \
            --with github.com/grafana/xk6-tcp@latest \
            --with github.com/grafana/xk6-crawler@latest ;;
    esac
  done

  # Always build k6-with-docs for the xk6docs skill to use live doc lookups.
  # The GitHub repo is xk6-docs but the Go module path is xk6-subcommand-docs.
  ensure_binary "$K6_WITH_DOCS" "k6-with-docs(xk6-subcommand-docs)" \
    --with github.com/grafana/xk6-subcommand-docs@latest || \
    echo "warning: k6-with-docs not built — xk6docs skill will use examples-only mode" >&2
}

# ── Docker management ─────────────────────────────────────────────────────────

start_quickpizza() {
  echo "Starting quickpizza Docker container for gRPC..." >&2
  QUICKPIZZA_CONTAINER=$(docker run -d --rm \
    -p 3333:3333 -p 3334:3334 \
    ghcr.io/grafana/quickpizza-local:latest 2>/dev/null) || { echo "warning: failed to start quickpizza" >&2; return 1; }
  local i=0
  while [[ $i -lt 30 ]]; do
    curl -sf --max-time 2 http://localhost:3333/ready >/dev/null 2>&1 && { echo "quickpizza ready" >&2; return 0; }
    sleep 1; i=$((i+1))
  done
  echo "warning: quickpizza not ready" >&2
  docker stop "$QUICKPIZZA_CONTAINER" >/dev/null 2>&1 || true; QUICKPIZZA_CONTAINER=""
  return 1
}

stop_quickpizza() {
  [[ -n "$QUICKPIZZA_CONTAINER" ]] && { docker stop "$QUICKPIZZA_CONTAINER" >/dev/null 2>&1 || true; QUICKPIZZA_CONTAINER=""; }
}

start_redis() {
  echo "Starting Redis Docker container for S12..." >&2
  REDIS_CONTAINER=$(docker run -d --rm -p 6379:6379 redis:alpine 2>/dev/null) || { echo "warning: failed to start Redis" >&2; return 1; }
  sleep 2
  echo "Redis ready" >&2
}

stop_redis() {
  [[ -n "$REDIS_CONTAINER" ]] && { docker stop "$REDIS_CONTAINER" >/dev/null 2>&1 || true; REDIS_CONTAINER=""; }
}

# ── Script generation ─────────────────────────────────────────────────────────

generate_script() {
  local skill="$1"
  local prompt="$2"
  local out_dir="$3"

  mkdir -p "$out_dir"
  [[ -d "$PROTO_DIR" ]] && cp -r "$PROTO_DIR" "$out_dir/proto"

  # k6 v1.7.0+ auto-provisions the docs subcommand — no binary copy needed.
  # The agent runs 'k6 x docs --version v1.6.1' and the extension is fetched
  # from cache automatically. No manual k6-with-docs binary required.

  local full_prompt="Load and follow the $skill skill. Then: $prompt"
  opencode run --format json --dir "$out_dir" "$full_prompt" 2>/dev/null
}

# ── Text + token extraction ───────────────────────────────────────────────────

extract_text()   { jq -r 'select(.type == "text") | .part.text' 2>/dev/null; }
extract_tokens() { jq -r 'select(.type == "step_finish") | .part.tokens.total' 2>/dev/null | tail -1; }

# ── Script extraction — prefer JS blocks over shell/output blocks ─────────────

extract_script() {
  local text="$1"
  echo "$text" | python3 - <<'PYEOF'
import sys, re
text = sys.stdin.read()
for m in re.finditer(r'```[^\n]*\n(.*?)```', text, re.DOTALL):
    block = m.group(1)
    if 'import ' in block or 'export ' in block or 'export default' in block:
        print(block.rstrip())
        sys.exit(0)
if text:
    # Fall back to first block
    m = re.search(r'```[^\n]*\n(.*?)```', text, re.DOTALL)
    if m:
        print(m.group(1).rstrip())
PYEOF
}

# ── Script finder — agent-written files take priority over response extraction ─

find_script_file() {
  local run_dir="$1"
  local gen="$run_dir/generated.js"

  # Prefer generated.js if it contains actual JS
  if [[ -f "$gen" ]] && grep -q "import\|export" "$gen" 2>/dev/null; then
    echo "$gen"; return
  fi

  # Find any .js file the agent wrote (excluding generated.js)
  local written
  written=$(find "$run_dir" -name "*.js" -not -name "generated.js" 2>/dev/null | head -1)
  [[ -n "$written" ]] && { echo "$written"; return; }

  [[ -f "$gen" ]] && echo "$gen"
}

# ── Validation ────────────────────────────────────────────────────────────────

validate_script_file() {
  local script_file="$1"
  local k6_bin="${2:-$K6_DEFAULT}"
  local scenario_num="${3:-0}"

  [[ ! -f "$script_file" ]] && { echo "no_script"; return; }

  local cmd

  if grep -q "from 'k6/browser'\|from \"k6/browser\"" "$script_file"; then
    # Browser: must not use --vus/--iterations
    cmd="$k6_bin run $script_file"

  elif grep -q "executor:" "$script_file" && grep -qE "ramping-vus|ramping-arrival-rate|constant-arrival-rate" "$script_file"; then
    # Long-running executors: use k6 inspect to validate parse/import without executing.
    if $k6_bin inspect "$script_file" >/dev/null 2>&1; then
      echo "pass"
    else
      echo "fail"
    fi
    return

  elif grep -q "executor:" "$script_file"; then
    # Multi-scenario (named exec functions): must not use --vus/--iterations
    cmd="$k6_bin run $script_file"

  else
    cmd="$k6_bin run --vus 1 --iterations 1 $script_file"
  fi

  # Run with the specified binary first; if it fails due to missing extension
  # dependency (k6/x/*), retry with the full extensions binary.
  if $cmd >/dev/null 2>&1; then
    echo "pass"
  else
    # Check if the failure is an extension dependency issue
    local err_out
    err_out=$($cmd 2>&1 || true)
    if echo "$err_out" | grep -q "k6/x/" && [[ "$k6_bin" != "$K6_EXTENSIONS" && -f "$K6_EXTENSIONS" ]]; then
      local ext_cmd="${cmd/$k6_bin/$K6_EXTENSIONS}"
      $ext_cmd >/dev/null 2>&1 && echo "pass(ext-bin)" || echo "fail"
    else
      echo "fail"
    fi
  fi
}

# ── Per-skill worker (runs in background) ────────────────────────────────────
# Writes a single result line to a temp file, then exits.

run_skill_worker() {
  local scenario_num="$1"
  local skill="$2"
  local k6_bin="$3"
  local prompt="$4"
  local result_file="$5"   # where to write the markdown table row

  local run_dir="$SCRIPTS_DIR/s${scenario_num}-${skill}"
  mkdir -p "$run_dir"

  echo ">>> scenario=$scenario_num skill=$skill binary=$(basename "$k6_bin")" >&2

  local start end duration
  start=$(date +%s)

  local json_events=""
  json_events=$(generate_script "$skill" "$prompt" "$run_dir") || true

  end=$(date +%s)
  duration=$((end - start))

  echo "$json_events" > "$run_dir/events.jsonl"

  local assistant_text tokens
  assistant_text=$(echo "$json_events" | extract_text)
  tokens=$(echo "$json_events" | extract_tokens)
  tokens="${tokens:-n/a}"
  echo "$assistant_text" > "$run_dir/response.md"

  # Extract script from response
  local script_content
  script_content=$(extract_script "$assistant_text")
  local generated_js="$run_dir/generated.js"
  [[ -n "$script_content" ]] && echo "$script_content" > "$generated_js"

  local script_file
  script_file=$(find_script_file "$run_dir")

  # Validate
  local valid
  if [[ "$scenario_num" == "5" ]]; then
    if [[ -z "$script_file" || ! -f "$script_file" ]]; then
      valid="no_script"
    else
      local script_dir; script_dir=$(dirname "$script_file")
      mkdir -p "$script_dir/proto"
      cp "$PROTO_DIR/quickpizza.proto" "$script_dir/proto/" 2>/dev/null || true
      local script_name; script_name=$(basename "$script_file")
      (cd "$script_dir" && "$k6_bin" run --vus 1 --iterations 1 "$script_name" >/dev/null 2>&1) \
        && valid="pass" || valid="fail"
    fi
  else
    valid=$(validate_script_file "$script_file" "$k6_bin" "$scenario_num")
  fi

  # Best-practices static score
  local bp_score="n/a"
  if [[ -n "$script_file" && -f "$script_file" ]]; then
    bp_raw=$(python3 "$SCRIPT_DIR/bp-check.py" "$script_file" 2>/dev/null)
    bp_score=$(echo "$bp_raw" | python3 -c "import sys,json; d=json.load(sys.stdin); print(f\"{d['score']}/{d['max']}\")" 2>/dev/null || echo "n/a")
    bp_issues=$(echo "$bp_raw" | python3 -c "import sys,json; d=json.load(sys.stdin); print(', '.join(d['issues']) or 'none')" 2>/dev/null || echo "")
    [[ -n "$bp_issues" && "$bp_issues" != "none" ]] && echo "    bp_issues: $bp_issues" >&2
  fi

  echo "    valid=$valid tokens=$tokens bp=$bp_score duration=${duration}s" >&2

  # Write result row to temp file (will be merged into output in order)
  printf "| S%s | %s | %s | %s | %s | %s |\n" \
    "$scenario_num" "$skill" "$valid" "$bp_score" "$tokens" "$duration" > "$result_file"
}

# ── Main ──────────────────────────────────────────────────────────────────────

main() {
  check_deps
  mkdir -p "$RESULTS_DIR" "$SCRIPTS_DIR"

  local scenarios="1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16 17 18 19 20 21 22 23 24 25 26 27 28 29 30"
  [[ -n "$FILTER_SCENARIO" ]] && scenarios="$FILTER_SCENARIO"
  local skills="k6-create-mcp k6-create-xk6docs"
  [[ -n "$FILTER_SKILL" ]] && skills="$FILTER_SKILL"

  ensure_all_binaries "$scenarios"

  for s in $scenarios; do
    [[ "$s" == "5" ]] && { start_quickpizza || echo "WARNING: S5 gRPC may fail" >&2; break; }
  done
  for s in $scenarios; do
    [[ "$s" == "12" ]] && { start_redis || echo "WARNING: S12 Redis may fail" >&2; break; }
  done

  trap 'stop_quickpizza; stop_redis; wait' EXIT INT TERM

  echo "# k6 Skill Comparison — $TIMESTAMP" > "$OUTPUT_FILE"
  echo "" >> "$OUTPUT_FILE"
  echo "| Scenario | Skill | Valid | BP Score | Tokens | Duration (s) |" >> "$OUTPUT_FILE"
  echo "|----------|-------|-------|----------|--------|--------------|" >> "$OUTPUT_FILE"

  for scenario_num in $scenarios; do
    local prompt
    prompt=$(get_scenario "$scenario_num")
    if [[ -z "$prompt" ]]; then
      echo "error: unknown scenario: $scenario_num" >&2; continue
    fi

    local k6_bin
    k6_bin=$(get_k6_binary "$scenario_num")

    if [[ "$k6_bin" != "$K6_DEFAULT" && ! -f "$k6_bin" ]]; then
      echo ">>> scenario=$scenario_num: SKIP (binary $k6_bin not available)" >&2
      for skill in $skills; do
        printf "| S%s | %s | %s | %s | %s | %s |\n" \
          "$scenario_num" "$skill" "skip(no binary)" "n/a" "n/a" "0" >> "$OUTPUT_FILE"
      done
      continue
    fi

    # ── Run both skills in parallel ─────────────────────────────────────────
    local pids=()
    local result_files=()
    local skill_order=()

    for skill in $skills; do
      local result_file="$SCRIPTS_DIR/s${scenario_num}-${skill}.result"
      run_skill_worker "$scenario_num" "$skill" "$k6_bin" "$prompt" "$result_file" &
      pids+=("$!")
      result_files+=("$result_file")
      skill_order+=("$skill")
    done

    # Wait for all workers for this scenario, then collect results in order
    for i in "${!pids[@]}"; do
      wait "${pids[$i]}" || true
    done

    # Append results to output in the original skill order
    for result_file in "${result_files[@]}"; do
      if [[ -f "$result_file" ]]; then
        cat "$result_file" >> "$OUTPUT_FILE"
        rm -f "$result_file"
      fi
    done
  done

  stop_quickpizza
  stop_redis

  echo "" >> "$OUTPUT_FILE"
  echo "Scripts saved to: \`$SCRIPTS_DIR\`" >> "$OUTPUT_FILE"
  echo "" >&2
  echo "Results: $OUTPUT_FILE" >&2
  cat "$OUTPUT_FILE"
}

main "$@"
