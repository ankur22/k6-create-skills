# k6 Docs Lookup Guidance

Use this file when you need to look up k6 documentation with the docs subcommand.
`DOCS_CMD` is established in Step 3 of `SKILL.md` — substitute it in the commands below.

> **Important:** `DOCS_CMD` must include the `script` TTY wrapper set up in
> Step 3. Without it, every invocation returns a generic "browse files" guide
> instead of actual content. Redirect stderr to suppress AER log lines:
> `$DOCS_CMD <path> 2>/dev/null`

---

## Commands

```
$DOCS_CMD 2>/dev/null                        # overview of all topics
$DOCS_CMD <path> 2>/dev/null                 # read a topic; shows content + subtopics at the bottom
$DOCS_CMD <path> --depth 2 2>/dev/null      # read a topic + 2 levels of subtopics in one call
$DOCS_CMD search <term> 2>/dev/null         # fuzzy search; returns matching paths
```

Paths use spaces or slashes interchangeably.

## Strategy

**2 calls is the target.**

Try a direct path first — wrong paths don't error, they return subtopics to
guide your next call. Only use search or overview when you have no idea where
to look.

Once you have a path (from a subtopics list or search), go to it directly —
don't visit the parent to confirm first.

When a topic page shows a method table with descriptions, that is the complete
API — no need to read individual method sub-pages.

## Rules

- Full parent path required: `using-k6 thresholds` works, `thresholds` alone fails.
- `k6-` prefix is auto-added on `javascript-api` paths where needed.

## Common paths

| Need | Path |
|------|------|
| HTTP | `javascript-api k6-http` |
| Browser | `javascript-api k6-browser` |
| WebSocket | `javascript-api k6-experimental-websockets` |
| gRPC | `javascript-api k6-net-grpc` |
| Custom metrics | `javascript-api k6-metrics` |
| SharedArray | `javascript-api k6-data` |
| Execution info | `javascript-api k6-execution` |
| Crypto | `javascript-api k6-crypto` |
| Encoding | `javascript-api k6-encoding` |
| HTML parsing | `javascript-api k6-html` |
| Scenarios/Executors | `using-k6 scenarios` |
| Thresholds | `using-k6 thresholds` |
| Checks | `using-k6 checks` |
| Test lifecycle | `using-k6 test-lifecycle` |
| Cloud run | `cloud` |
| Best practices | `$DOCS_CMD best-practices` |
