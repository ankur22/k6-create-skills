# k6 Docs Lookup Guidance

Use this file when you need to look up k6 documentation with the docs subcommand.
The docs binary is either `k6 x docs` or `./k6-with-docs x docs` — use whichever
worked in Step 0 of the skill.

---

## Commands

```
<binary> x docs                        # overview of all topics
<binary> x docs <path>                 # read a topic; shows content + subtopics at the bottom
<binary> x docs <path> --depth 2      # read a topic + 2 levels of subtopics in one call
<binary> x docs search <term>         # fuzzy search; returns matching paths
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
| Best practices | `<binary> x docs best-practices` |
