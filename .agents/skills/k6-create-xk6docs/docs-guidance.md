# k6 Docs Lookup Guidance

Use this file when you need to look up k6 documentation with the docs subcommand.
`DOCS_CMD` was set in Step 0. Substitute it below.

As of **k6 v1.7.0** the subcommand auto-provisions — no manual build needed.
The `--version v1.6.1` flag is required until the v1.7.x doc bundle ships.

---

## Commands

```
$DOCS_CMD                        # overview of all topics
$DOCS_CMD <path>                 # read a topic; shows content + subtopics at the bottom
$DOCS_CMD <path> --depth 2      # read a topic + 2 levels of subtopics in one call
$DOCS_CMD search <term>         # fuzzy search; returns matching paths
```

If `DOCS_CMD` is `k6 x docs --version v1.6.1`, append the path after the flag:
```
k6 x docs --version v1.6.1 javascript-api/k6-http
k6 x docs --version v1.6.1 search websocket
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
