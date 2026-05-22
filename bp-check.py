#!/usr/bin/env python3
"""
bp-check.py - Static k6 script scorer.

Usage:
    python3 bp-check.py <script.js>
    python3 bp-check.py <script.js> --scenario 19 --manifest scenario-manifest.json --result-dir <run-dir>

Exit code: 0 always (non-blocking). Output keeps the historical fields:
    {"score": N, "max": M, "issues": [...]}

It also emits categorized details for downstream analysis:
    validity, best_practices, protocol_specific, prompt_adherence, artifacts
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Any


def _strip_comments(code: str) -> str:
    """Remove JS comments while preserving strings and newlines."""
    out: list[str] = []
    i = 0
    in_string: str | None = None
    escaped = False

    while i < len(code):
        ch = code[i]
        nxt = code[i + 1] if i + 1 < len(code) else ""

        if in_string:
            out.append(ch)
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == in_string:
                in_string = None
            i += 1
            continue

        if ch in {"'", '"', "`"}:
            in_string = ch
            out.append(ch)
            i += 1
            continue

        if ch == "/" and nxt == "/":
            i += 2
            while i < len(code) and code[i] != "\n":
                i += 1
            if i < len(code):
                out.append("\n")
                i += 1
            continue

        if ch == "/" and nxt == "*":
            i += 2
            while i + 1 < len(code) and not (code[i] == "*" and code[i + 1] == "/"):
                if code[i] == "\n":
                    out.append("\n")
                i += 1
            i += 2
            continue

        out.append(ch)
        i += 1

    return "".join(out)


def _normalise(code: str) -> str:
    return re.sub(r"\s+", "", code)


def _new_category() -> dict[str, Any]:
    return {"score": 0, "max": 0, "issues": [], "skipped": []}


def _add_rule(
    categories: dict[str, dict[str, Any]],
    category: str,
    name: str,
    ok: bool,
    skipped: bool = False,
) -> None:
    cat = categories.setdefault(category, _new_category())
    if skipped:
        cat["skipped"].append(name)
        return
    cat["max"] += 1
    if ok:
        cat["score"] += 1
    else:
        cat["issues"].append(name)


def _has_import(code: str, module: str) -> bool:
    return bool(re.search(rf"\bimport\b[\s\S]*?\bfrom\s*['\"]{re.escape(module)}['\"]", code))


def _has_default_export(code: str) -> bool:
    return bool(
        re.search(r"export\s+default\s+(?:async\s+)?function\b", code)
        or re.search(r"export\s+default\s+(?:async\s*)?\([^)]*\)\s*=>", code)
    )


def _has_named_export(code: str, name: str) -> bool:
    if name == "default":
        return _has_default_export(code)
    return bool(re.search(rf"export\s+(?:async\s+)?function\s+{re.escape(name)}\b", code))


def _exported_functions_ok(code: str) -> bool:
    exec_names = re.findall(r"\bexec\s*:\s*['\"]([A-Za-z_$][\w$]*)['\"]", code)
    if exec_names:
        return all(_has_named_export(code, name) for name in exec_names)
    return _has_default_export(code)


def _is_single_iteration(code: str) -> bool:
    return bool(re.search(r"\biterations\s*:\s*1\b", code)) and bool(
        re.search(r"\bvus\s*:\s*1\b", code)
    )


def _needs_thresholds(code: str, is_functional: bool, is_browser: bool) -> bool:
    # Smoke tests (1 VU + 1 iteration) and pure functional tests do not need
    # latency/failure-rate thresholds — they assert correctness, not performance.
    if _is_single_iteration(code):
        return False
    if is_functional:
        return False
    return bool(
        re.search(
            r"\bduration\s*:|\bstages\s*:|ramping-vus|constant-vus|arrival-rate|\bvus\s*:",
            code,
        )
    )


def _needs_sleep(code: str, is_browser: bool, is_functional: bool) -> bool:
    # Browser scripts use page.waitForTimeout, single-iteration smoke tests are
    # explicitly one-shot, and arrival-rate executors pace themselves.
    if is_browser or _is_single_iteration(code) or is_functional:
        return False
    if re.search(r"constant-arrival-rate|ramping-arrival-rate", code):
        return False
    return bool(re.search(r"\bduration\s*:|\bstages\s*:|ramping-vus|constant-vus|\bvus\s*:", code))


def _actual_relpath(path: str, result_dir: str | None) -> str:
    p = Path(path).resolve()
    if result_dir:
        try:
            return p.relative_to(Path(result_dir).resolve()).as_posix()
        except ValueError:
            pass
    parts = p.parts
    if "k6" in parts:
        idx = parts.index("k6")
        return Path(*parts[idx:]).as_posix()
    return p.name


def _load_manifest(manifest_path: str | None, scenario: str | None) -> dict[str, Any] | None:
    if not manifest_path or not scenario or not os.path.isfile(manifest_path):
        return None
    with open(manifest_path) as f:
        manifest = json.load(f)
    return manifest.get("scenarios", {}).get(str(scenario))


def _check_manifest_rule(
    rule: dict[str, Any],
    code: str,
    raw_code: str,
    path: str,
    result_dir: str | None,
) -> bool:
    typ = rule.get("type")
    flags = re.MULTILINE | re.DOTALL
    # Rules may opt into raw_code (with comments) when the prompt asks for
    # documentation/comments specifically. Default is the comment-stripped code.
    target = raw_code if rule.get("target") == "raw" else code
    norm = _normalise(target)

    if typ == "regex":
        return bool(re.search(rule["pattern"], target, flags))
    if typ == "not_regex":
        return not bool(re.search(rule["pattern"], target, flags))
    if typ == "import":
        return _has_import(code, rule["module"])
    if typ == "no_import":
        return not _has_import(code, rule["module"])
    if typ == "contains":
        return rule["value"] in target
    if typ == "http_request":
        method = re.escape(str(rule["method"]).lower())
        path_literal = rule["path"]
        path_fragment = re.escape(path_literal)
        # Direct: http.METHOD(`...path...`) inline.
        if re.search(rf"http\.{method}\s*\([\s\S]*?{path_fragment}", code, flags):
            return True
        # Indirect: a const holds the URL, and http.METHOD(CONST) calls it.
        const_pattern = rf"\bconst\s+(\w+)\s*=\s*[`'\"][^`'\"]*{path_fragment}[^`'\"]*[`'\"]"
        for var in re.findall(const_pattern, code):
            if re.search(rf"http\.{method}\s*\(\s*{re.escape(var)}\b", code, flags):
                return True
        return False
    if typ == "grpc_invoke":
        method = re.escape(rule["method"])
        return bool(re.search(rf"\.invoke\s*\(\s*['\"]{method}['\"]", code, flags))
    if typ == "option_number":
        return bool(re.search(rf"\b{re.escape(rule['key'])}\s*:\s*{int(rule['value'])}\b", code))
    if typ == "option_duration":
        return bool(
            re.search(
                rf"\b{re.escape(rule['key'])}\s*:\s*['\"]{re.escape(rule['value'])}['\"]",
                code,
            )
        )
    if typ == "threshold":
        metric = _normalise(rule["metric"])
        expression = _normalise(rule["expression"])
        return metric in norm and expression in norm
    if typ == "screenshot_count":
        return len(re.findall(r"\.screenshot\s*\(", code)) >= int(rule.get("min", 1))
    if typ == "file_path":
        return _actual_relpath(path, result_dir) == rule["path"]
    if typ == "sync_default_function":
        return not bool(re.search(r"export\s+default\s+async\s+function", code))
    if typ == "browser_expect":
        text = re.escape(rule.get("text", ""))
        return bool(re.search(rf"expect\s*\([\s\S]*?{text}[\s\S]*?\)\.", code, flags))

    return False


def _apply_manifest_checks(
    categories: dict[str, dict[str, Any]],
    manifest: dict[str, Any] | None,
    code: str,
    raw_code: str,
    path: str,
    result_dir: str | None,
) -> None:
    if not manifest:
        return
    for rule in manifest.get("checks", []):
        category = rule.get("category", "prompt_adherence")
        name = f"{rule.get('id', 'manifest')}: {rule.get('description', rule.get('type', 'check'))}"
        _add_rule(categories, category, name, _check_manifest_rule(rule, code, raw_code, path, result_dir))


def _score_existing_file(
    path: str,
    scenario: str | None = None,
    manifest_path: str | None = None,
    result_dir: str | None = None,
) -> dict[str, Any]:
    with open(path) as f:
        raw_code = f.read()

    code = _strip_comments(raw_code)
    categories: dict[str, dict[str, Any]] = {"validity": _new_category()}
    _add_rule(categories, "validity", "script file exists", True)

    is_browser = _has_import(code, "k6/browser")
    is_grpc = _has_import(code, "k6/net/grpc")
    is_websocket = _has_import(code, "k6/experimental/websockets")
    is_functional = "jslib.k6.io/k6-testing" in code
    is_async = bool(re.search(r"export\s+(?:default\s+)?async\s+function", code))

    # General best-practices checks.
    _add_rule(categories, "best_practices", "R1 export const options", bool(re.search(r"export\s+const\s+options", code)))

    if _needs_thresholds(code, is_functional, is_browser):
        _add_rule(categories, "best_practices", "R2 thresholds defined", bool(re.search(r"\bthresholds\s*:", code)))
    else:
        _add_rule(categories, "best_practices", "R2 thresholds defined", True, skipped=True)

    _add_rule(categories, "best_practices", "R3 assertions (check/expect)", bool(re.search(r"\bcheck\s*\(|\bexpect\s*\(", code)))

    if _needs_sleep(code, is_browser, is_functional):
        _add_rule(categories, "best_practices", "R4 pacing sleep()", bool(re.search(r"\bsleep\s*\(", code)))
    else:
        _add_rule(categories, "best_practices", "R4 pacing sleep()", True, skipped=True)

    _add_rule(
        categories,
        "best_practices",
        "R5 no placeholders ({ ... }/TODO/FIXME)",
        not bool(re.search(r"\{\s*\.\.\.\s*\}|//\s*TODO|//\s*FIXME", raw_code)),
    )
    _add_rule(categories, "best_practices", "R6 no deprecated k6/ws import", not _has_import(code, "k6/ws"))
    _add_rule(categories, "best_practices", "R9 no mutable top-level let/var", not bool(re.search(r"^(?:let|var)\s+\w+", code, re.MULTILINE)))
    _add_rule(categories, "best_practices", "R10 exported test function(s)", _exported_functions_ok(code))

    if is_browser and is_async:
        standard_k6_check = bool(re.search(r"import\s*\{[^}]*\bcheck\b[^}]*\}\s*from\s*['\"]k6['\"]", code))
        _add_rule(categories, "protocol_specific", "P1 browser async avoids standard k6 check()", not standard_k6_check)

    # Protocol-specific checks.
    if is_browser:
        _add_rule(categories, "protocol_specific", "P2 browser page.close() in finally", bool(re.search(r"\bfinally\s*\{[\s\S]*?\.close\s*\(\s*\)", code)))
        _add_rule(categories, "protocol_specific", "P3 browser avoids waitForLoadState()", "waitForLoadState" not in code)
        _add_rule(
            categories,
            "protocol_specific",
            "P4 browser uses expect() or async-safe check()",
            bool(re.search(r"\bexpect\s*\(", code)) or "jslib.k6.io/k6-utils" in code,
        )

    if is_grpc:
        _add_rule(categories, "protocol_specific", "P5 gRPC client.close() called", bool(re.search(r"\bclient\.close\s*\(", code)))
        _add_rule(categories, "protocol_specific", "P6 gRPC client.close() in finally", bool(re.search(r"\bfinally\s*\{[\s\S]*?\bclient\.close\s*\(", code)))

    if is_websocket:
        _add_rule(categories, "protocol_specific", "P7 WebSocket has error handler", bool(re.search(r"(?:addEventListener|on)\s*\(\s*['\"]error['\"]", code)))
        _add_rule(categories, "protocol_specific", "P8 WebSocket JSON.parse guarded", "JSON.parse" not in code or bool(re.search(r"try\s*\{[\s\S]{0,400}JSON\.parse", code)))
        _add_rule(categories, "protocol_specific", "P9 WebSocket has close fallback or maxDuration", bool(re.search(r"setTimeout|setInterval|maxDuration", code)))

    manifest = _load_manifest(manifest_path, scenario)
    _apply_manifest_checks(categories, manifest, code, raw_code, path, result_dir)

    score_value = sum(cat["score"] for cat in categories.values())
    max_value = sum(cat["max"] for cat in categories.values())
    issues = [issue for cat in categories.values() for issue in cat["issues"]]
    skipped = [issue for cat in categories.values() for issue in cat["skipped"]]

    return {
        "score": score_value,
        "max": max_value,
        "issues": issues,
        "skipped": skipped,
        "categories": categories,
        "scenario": str(scenario) if scenario else None,
        "manifest": bool(manifest),
        "script": _actual_relpath(path, result_dir),
    }


def score(
    path: str | None,
    scenario: str | None = None,
    manifest_path: str | None = None,
    result_dir: str | None = None,
) -> dict[str, Any]:
    if not path or not os.path.exists(path):
        categories = {"validity": _new_category()}
        _add_rule(categories, "validity", "script file exists", False)
        return {
            "score": 0,
            "max": 1,
            "issues": ["script file exists"],
            "skipped": [],
            "categories": categories,
            "scenario": str(scenario) if scenario else None,
            "manifest": False,
            "script": None,
        }
    return _score_existing_file(path, scenario, manifest_path, result_dir)


def main() -> None:
    parser = argparse.ArgumentParser(description="Static best-practices scorer for k6 scripts")
    parser.add_argument("script", nargs="?", help="Path to script.js")
    parser.add_argument("--scenario", default=None, help="Scenario number for manifest checks")
    parser.add_argument("--manifest", default=None, help="Path to scenario-manifest.json")
    parser.add_argument("--result-dir", default=None, help="Run directory for relative artifact checks")
    args = parser.parse_args()

    print(json.dumps(score(args.script, args.scenario, args.manifest, args.result_dir)))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # Non-blocking by design.
        print(json.dumps({"score": 0, "max": 1, "issues": [f"bp-check failed: {exc}"]}))
        sys.exit(0)
