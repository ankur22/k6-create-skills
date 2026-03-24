---
name: k6-create-mcp
description: Generate and validate k6 load test, functional, and protocol test scripts using the mcp-k6 MCP server tools. Covers HTTP, WebSocket, gRPC, browser, all executors, custom metrics, k6-testing library, cloud execution, and the full xk6 extension ecosystem. Use when asked to write or generate any kind of k6 script and mcp-k6 is configured.
license: MIT
compatibility: opencode
---

# k6 Script Generation (mcp-k6)

Generate k6 scripts using the mcp-k6 MCP server. All documentation, type definitions, validation, and execution go through the MCP server — do not use external references or baked-in examples.

## Step 0: Confirm the MCP server is available

Check that `validate_script`, `list_sections`, and `get_documentation` are available as tools.

If they are **not** available: output exactly the following line and stop immediately — do not attempt to write any script:

```
MCP_UNAVAILABLE: mcp-k6 tools not found. Configure with: {"mcpServers":{"k6":{"command":"docker","args":["run","--rm","-i","grafana/mcp-k6"]}}}
```

Do not ask the user any questions. Do not continue. Stop.

---

## Step 1: Research

Use `list_sections` to locate the relevant documentation areas. Use `get_documentation` to fetch content for each section you need. For every API you plan to use, open the corresponding type definition via `types://k6/**/*.d.ts` — the type defs are the source of truth for import paths, option shapes, and return types, and override doc examples where they conflict.

---

## Step 2: Best practices

Read `docs://k6/best_practices`. Apply patterns relevant to the user's scenario.

---

## Step 3: Write the script

Write a complete, runnable k6 script. No `{ ... }`, `// TODO`, or stubs — every expression must be executable. For multi-scenario scripts (browser + HTTP, cloud), use named `scenarios` with `exec` pointing to separate exported functions.

---

## Step 4: Save

```bash
mkdir -p k6/scripts
```

Save to `k6/scripts/<descriptive-name>.js` via the Write tool. Lowercase kebab-case filename.

---

## Step 5: Validate

Call `validate_script` with the script content.

If it returns errors: read the error, fix the root cause, call `validate_script` again. Retry up to **3 attempts**. After 3 failures, present the script and the error to the user and ask how to proceed.

---

## Step 6: Best-practices review

Read `docs://k6/best_practices`. Check the generated script against it and flag any issues as warnings — do not block on them unless critical.

Key things to verify:
- `export const options` with realistic VUs/duration and `thresholds`
- `sleep()` between iterations in load tests (prevents hammering; skip for browser/functional scripts)
- `check()` or `expect()` assertions on every response
- Browser scripts use `try/finally` with `page.close()` in the `finally` block
- gRPC scripts call `client.close()` after each iteration
- No `let`/`var` at top level (use `const`; mutable globals cause cross-VU contamination)
- No deprecated imports (e.g. `k6/ws` — use `k6/experimental/websockets`)

If there are issues: fix them in the script, re-validate, then continue to Step 7.
If only minor style issues: note them in the output but do not re-validate.

---

## Step 7: Present results

1. Full script with file path
2. Result from `validate_script`
3. Best-practices notes (issues found, or "all checks passed")
4. Proposed `run_script` parameters for the scenario

---

## Step 8: Execute

If the user confirms, call `run_script` with the proposed parameters.
