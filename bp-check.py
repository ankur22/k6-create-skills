#!/usr/bin/env python3
"""
bp-check.py — Static best-practices scorer for k6 scripts.

Usage: python3 bp-check.py <script.js>
Exit code: 0 always (non-blocking). Outputs JSON: {"score":N,"max":10,"issues":[...]}

Rules (10 points total):
  R1  exports options block (export const options)
  R2  thresholds defined  (skip for cloud / functional scripts)
  R3  has assertions      (check() or expect())
  R4  sleep() for think time (skip for browser / functional / extension-only)
  R5  no placeholder code  ({ ... } / TODO / FIXME)
  R6  no deprecated k6/ws  (use k6/experimental/websockets)
  R7  browser: try/finally with page.close()  (browser only)
  R8  gRPC: client.close() called             (gRPC only)
  R9  no mutable top-level state (no top-level let/var)
  R10 has exported test function(s)
"""

import sys, re, json, os

def score(path):
    if not path or not os.path.exists(path):
        return {"score": 0, "max": 10, "issues": ["no script file"]}

    with open(path) as f:
        code = f.read()

    is_browser    = bool(re.search(r"from ['\"]k6/browser['\"]", code))
    is_grpc       = bool(re.search(r"from ['\"]k6/net/grpc['\"]", code))
    is_functional = bool(re.search(r"jslib\.k6\.io/k6-testing", code))
    is_cloud      = bool(re.search(r"(?:ext\.loadimpact|^\s*cloud\s*:\s*\{)", code, re.MULTILINE))
    is_extension  = bool(re.search(r"from ['\"]k6/x/", code)) and \
                    not bool(re.search(r"from ['\"]k6/http['\"]|from ['\"]k6/net/grpc['\"]|from ['\"]k6/experimental/websockets['\"]", code))
    is_long_exec  = bool(re.search(r"ramping-vus|ramping-arrival-rate|constant-arrival-rate", code))

    rules = []

    # R1 options block
    rules.append(("R1 export const options", bool(re.search(r"export\s+const\s+options", code))))

    # R2 thresholds
    if is_cloud or is_functional:
        rules.append(("R2 thresholds (n/a cloud/functional)", True))
    else:
        rules.append(("R2 thresholds defined", bool(re.search(r"thresholds\s*:", code))))

    # R3 assertions
    rules.append(("R3 assertions (check/expect)", bool(re.search(r"\bcheck\s*\(|\bexpect\s*\(", code))))

    # R4 sleep
    if is_browser or is_functional or is_extension:
        rules.append(("R4 sleep (n/a browser/functional/extension)", True))
    else:
        rules.append(("R4 sleep() for think time", bool(re.search(r"\bsleep\s*\(", code))))

    # R5 no placeholders
    rules.append(("R5 no placeholders ({ ... }/TODO/FIXME)", not bool(re.search(r"\{\s*\.\.\.\s*\}|//\s*TODO|//\s*FIXME", code))))

    # R6 no deprecated k6/ws
    rules.append(("R6 no deprecated k6/ws import", not bool(re.search(r"from ['\"]k6/ws['\"]", code))))

    # R7 browser cleanup
    if is_browser:
        ok = bool(re.search(r"\bfinally\b", code)) and bool(re.search(r"\.close\(\)", code))
        rules.append(("R7 browser: try/finally + page.close()", ok))
    else:
        rules.append(("R7 browser cleanup (n/a)", True))

    # R8 gRPC cleanup
    if is_grpc:
        rules.append(("R8 gRPC: client.close()", bool(re.search(r"client\.close\(\)", code))))
    else:
        rules.append(("R8 gRPC cleanup (n/a)", True))

    # R9 no mutable global state
    rules.append(("R9 no mutable top-level let/var", not bool(re.search(r"^(?:let|var)\s+\w+", code, re.MULTILINE))))

    # R10 exported test function
    rules.append(("R10 exported test function(s)", bool(re.search(r"export\s+(default\s+)?(async\s+)?function|export\s+const\s+options", code))))

    passed = sum(1 for _, ok in rules if ok)
    issues = [name for name, ok in rules if not ok]
    return {"score": passed, "max": len(rules), "issues": issues}


if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else None
    result = score(path)
    print(json.dumps(result))
