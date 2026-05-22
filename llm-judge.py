#!/usr/bin/env python3
"""
llm-judge.py — Score a generated k6 script against its original prompt.

Uses `opencode run` to call an LLM with a structured rubric. Returns JSON
scores on five dimensions (1-5 each, 25 max).

Usage:
    python3 llm-judge.py <results-dir> [--judge-model <provider/model>] [--gold-dir gold/]

The results dir must contain:
    prompt.txt          — the original prompt
    k6/scripts/*.js     — the generated script (first .js file found)

If a gold standard script exists at <gold-dir>/s<N>.js (where N is the
scenario number parsed from the results dir name), it is included in the
rubric as a reference implementation for stricter scoring.

Output (stdout): JSON object with scores and notes.
"""

import argparse
import json
import os
import re as re_module
import subprocess
import sys
from glob import glob
from pathlib import Path

RUBRIC_BASE = """\
You are a k6 load testing script quality judge. You will be given an ORIGINAL PROMPT \
that describes what script should be generated, and the GENERATED SCRIPT that was produced.\
{gold_intro}

Score the script on each dimension below using an integer from 1 to 5.

## Dimensions

### 1. Prompt Adherence (adherence)
Does the script implement what was asked?{adherence_gold}
- 5: Every requirement from the prompt is implemented correctly (endpoints, executor, VU counts, thresholds, assertions, file name)
- 4: One minor requirement missed or slightly off (e.g. threshold value differs)
- 3: Core functionality present but multiple requirements missed
- 2: Partially implements the prompt, significant gaps
- 1: Does not match the prompt at all

### 2. Code Quality (quality)
Is the code readable, well-structured, and idiomatic k6?{quality_gold}
- 5: Clean imports, descriptive variable names, helpful comments, logical grouping, idiomatic k6 patterns
- 4: Minor naming or style issues, but well-structured overall
- 3: Functional but messy — poor names, unnecessary complexity, or confusing structure
- 2: Hard to read, inconsistent style, misleading comments
- 1: Unreadable or fundamentally broken structure

### 3. Complexity Appropriateness (complexity)
Is the complexity proportional to what was asked?{complexity_gold}
- 5: Exactly right — no unnecessary abstraction, no missing pieces
- 4: Slightly over- or under-engineered but reasonable
- 3: Noticeably over-engineered (unnecessary helpers, excessive config) or too simplistic
- 2: Significantly mismatched complexity
- 1: Wildly over- or under-engineered

### 4. Robustness (robustness)
Would this script give useful signal if something went wrong?{robustness_gold}
- 5: Comprehensive check() assertions, meaningful thresholds, proper resource cleanup (client.close(), page.close() in finally), graceful handling
- 4: Good assertions and thresholds, minor cleanup gap
- 3: Basic checks present but gaps in error handling or thresholds
- 2: Minimal assertions, would silently pass on failures
- 1: No meaningful assertions or error handling

### 5. Runnable Completeness (completeness)
Can you copy-paste this and run it without modification?{completeness_gold}
- 5: Every import used, every variable defined, no TODOs/stubs/placeholders, realistic defaults
- 4: One minor placeholder that wouldn't prevent execution (e.g. a comment saying "replace with your token")
- 3: A few stubs or unused imports, but would likely run
- 2: Has TODOs or undefined references that would cause runtime errors
- 1: Incomplete — would not execute at all

## Response Format

Return ONLY a JSON object, no markdown fencing, no explanation outside the JSON:

{{
    "adherence": <1-5>,
    "quality": <1-5>,
    "complexity": <1-5>,
    "robustness": <1-5>,
    "completeness": <1-5>,
    "total": <sum of above, 5-25>,
    "notes": "<1-2 sentences explaining the most significant strength or weakness>"
}}
"""

# Text injected into the rubric when a gold standard is available.
GOLD_INTRO = """
 You will also be given a REFERENCE SCRIPT (gold standard) — a human-written \
implementation that represents the ideal solution. Use it as the primary benchmark \
for scoring. The generated script should be compared against the reference, not \
just evaluated in isolation. Be strict: any deviation from the reference that \
reduces correctness, readability, or robustness should lower the score."""

GOLD_ADHERENCE = """
Compare against the reference script. Does the generated script cover the same \
endpoints, use the same executor type, apply equivalent thresholds, and include \
equivalent assertions? Deduct for missing features that the reference includes, \
even if the prompt was ambiguous about them."""

GOLD_QUALITY = """
Compare structure, naming, and style against the reference. The reference sets \
the bar for idiomatic k6 code. Deduct if the generated script is less readable \
or uses non-idiomatic patterns where the reference shows a better way."""

GOLD_COMPLEXITY = """
The reference script represents the right level of complexity for this task. \
Score relative to it — if the generated script adds unnecessary abstraction \
or is missing structure the reference includes, deduct accordingly."""

GOLD_ROBUSTNESS = """
The reference script shows what assertions, thresholds, and cleanup should look \
like. Deduct for any check(), threshold, or resource cleanup pattern present in \
the reference but missing from the generated script."""

GOLD_COMPLETENESS = """
The reference script is fully runnable. Compare directly — any placeholder, \
stub, or missing piece that the reference handles should lower the score."""


def _build_rubric(has_gold: bool) -> str:
    """Build the rubric string, with or without gold standard instructions."""
    if has_gold:
        return RUBRIC_BASE.format(
            gold_intro=GOLD_INTRO,
            adherence_gold="\n" + GOLD_ADHERENCE,
            quality_gold="\n" + GOLD_QUALITY,
            complexity_gold="\n" + GOLD_COMPLEXITY,
            robustness_gold="\n" + GOLD_ROBUSTNESS,
            completeness_gold="\n" + GOLD_COMPLETENESS,
        )
    else:
        return RUBRIC_BASE.format(
            gold_intro="",
            adherence_gold="",
            quality_gold="",
            complexity_gold="",
            robustness_gold="",
            completeness_gold="",
        )


def _extract_json(text: str) -> dict | None:
    """Extract a JSON object from LLM output that may contain prose or fences."""
    import re

    # 1. Try parsing the full text directly
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # 2. Look for ```json ... ``` fenced blocks
    fence_match = re.search(r"```(?:json)?\s*\n(.*?)```", text, re.DOTALL)
    if fence_match:
        try:
            return json.loads(fence_match.group(1).strip())
        except json.JSONDecodeError:
            pass

    # 3. Find the first { ... } that contains "adherence" and try to parse it
    brace_start = text.find("{")
    if brace_start != -1:
        # Find matching closing brace by counting depth
        depth = 0
        for i in range(brace_start, len(text)):
            if text[i] == "{":
                depth += 1
            elif text[i] == "}":
                depth -= 1
                if depth == 0:
                    candidate = text[brace_start : i + 1]
                    try:
                        parsed = json.loads(candidate)
                        if "adherence" in parsed:
                            return parsed
                    except json.JSONDecodeError:
                        pass
                    break

    return None


def find_script(results_dir: str) -> str | None:
    """Find the first .js script in the results dir."""
    # Prefer k6/scripts/*.js (agent-written)
    scripts = sorted(glob(os.path.join(results_dir, "k6", "scripts", "*.js")))
    if scripts:
        return scripts[0]
    # Fall back to generated.js (extracted from response)
    gen = os.path.join(results_dir, "generated.js")
    if os.path.isfile(gen):
        return gen
    # Any .js file
    all_js = sorted(glob(os.path.join(results_dir, "**", "*.js"), recursive=True))
    return all_js[0] if all_js else None


def _parse_scenario_number(results_dir: str) -> str | None:
    """Extract scenario number from a results dir name like 's19-k6-create-xk6docs-claude-sonnet-4-6'."""
    dir_name = os.path.basename(results_dir.rstrip("/"))
    m = re_module.match(r"^s(\d+)", dir_name)
    return m.group(1) if m else None


def _find_gold_script(gold_dir: str | None, scenario_num: str | None) -> str | None:
    """Find gold/s<N>.js if it exists."""
    if not gold_dir or not scenario_num:
        return None
    gold_file = os.path.join(gold_dir, f"s{scenario_num}.js")
    return gold_file if os.path.isfile(gold_file) else None


def _failure_scores(results_dir: str, reason: str, gold_dir: str | None = None) -> dict:
    """Return a scored failure that remains visible in aggregate summaries."""
    scenario_num = _parse_scenario_number(results_dir)
    has_gold = _find_gold_script(gold_dir, scenario_num) is not None
    return {
        "adherence": 0,
        "quality": 0,
        "complexity": 0,
        "robustness": 0,
        "completeness": 0,
        "total": 0,
        "notes": reason,
        "script": None,
        "gold": has_gold,
        "failure": reason,
    }


def _read_text_if_exists(path: str) -> str | None:
    if not os.path.isfile(path):
        return None
    return Path(path).read_text().strip()


# Lines that explicitly identify which skill produced the script. The xk6docs
# skill writes a `// Generated by k6-create-xk6docs on <iso-timestamp>` header
# on almost every script; grafana-k6 occasionally writes a `// Generated by
# grafana-k6 skill on <date>` header; mcp-k6 writes none. Leaving these in the
# script biases the LLM judge toward whichever skill it has seen most often,
# so we strip them before showing the script to the judge.
_SKILL_IDENTITY_LINE = re_module.compile(
    r"^\s*//\s*Generated by\b.*$",
    re_module.MULTILINE,
)


def _strip_skill_identity(text: str) -> str:
    """Remove `// Generated by ...` markers so the judge cannot fingerprint the skill."""
    return _SKILL_IDENTITY_LINE.sub("", text).strip()


def _read_json_if_exists(path: str) -> dict | None:
    if not os.path.isfile(path):
        return None
    try:
        return json.loads(Path(path).read_text())
    except json.JSONDecodeError:
        return None


def _cap(scores: dict, key: str, cap: int, reason: str, caps: list[str]) -> None:
    value = scores.get(key)
    if not isinstance(value, (int, float)):
        value = 1
    value = int(value)
    value = max(0, min(5, value))
    if value > cap:
        scores[key] = cap
        caps.append(f"{key}<={cap}: {reason}")
    else:
        scores[key] = value


def _apply_hard_caps(scores: dict, validation: str | None, bp: dict | None) -> dict:
    """Make deterministic failures binding after the LLM scores the script."""
    caps: list[str] = []
    for key in ["adherence", "quality", "complexity", "robustness", "completeness"]:
        _cap(scores, key, 5, "score normalization", caps)

    if validation and not validation.startswith("pass"):
        _cap(scores, "completeness", 2, f"validation={validation}", caps)
        _cap(scores, "robustness", 2, f"validation={validation}", caps)

    if bp:
        categories = bp.get("categories", {})
        prompt_issues = categories.get("prompt_adherence", {}).get("issues", [])
        artifact_issues = categories.get("artifacts", {}).get("issues", [])
        all_issues = "\n".join(bp.get("issues", []))

        if prompt_issues:
            _cap(scores, "adherence", 3, "deterministic prompt-adherence checks failed", caps)
        if artifact_issues:
            _cap(scores, "completeness", 3, "required artifact checks failed", caps)
        if "R3 assertions" in all_issues:
            _cap(scores, "robustness", 3, "missing assertions", caps)
        if "R2 thresholds" in all_issues:
            _cap(scores, "robustness", 3, "missing thresholds", caps)
        if "in finally" in all_issues:
            _cap(scores, "robustness", 4, "resource cleanup is not guaranteed by finally", caps)

        scores["bp_score"] = f"{bp.get('score', '?')}/{bp.get('max', '?')}"
        scores["bp_issues"] = bp.get("issues", [])

    scores["total"] = sum(int(scores[k]) for k in ["adherence", "quality", "complexity", "robustness", "completeness"])
    if caps:
        scores["caps_applied"] = caps
    return scores


def judge(
    results_dir: str,
    judge_model: str | None = None,
    gold_dir: str | None = None,
    blind: bool = True,
) -> dict:
    prompt_file = os.path.join(results_dir, "prompt.txt")
    if not os.path.isfile(prompt_file):
        return _failure_scores(results_dir, "no prompt.txt found", gold_dir)

    prompt_text = Path(prompt_file).read_text().strip()

    script_file = find_script(results_dir)
    if not script_file:
        return _failure_scores(results_dir, "no script file found", gold_dir)

    raw_script_text = Path(script_file).read_text().strip()
    script_text = _strip_skill_identity(raw_script_text) if blind else raw_script_text
    blinded = blind and script_text != raw_script_text
    validation_text = _read_text_if_exists(os.path.join(results_dir, "validation.txt"))
    bp_result = _read_json_if_exists(os.path.join(results_dir, "bp.json"))

    # Look for a gold standard script
    scenario_num = _parse_scenario_number(results_dir)
    gold_file = _find_gold_script(gold_dir, scenario_num)
    gold_text = Path(gold_file).read_text().strip() if gold_file else None
    has_gold = gold_text is not None

    rubric = _build_rubric(has_gold)

    user_message = f"{rubric}\n\n## ORIGINAL PROMPT\n\n{prompt_text}\n\n"
    if gold_text:
        user_message += f"## REFERENCE SCRIPT (gold standard)\n\n```javascript\n{gold_text}\n```\n\n"
    if validation_text or bp_result:
        user_message += "## DETERMINISTIC STATIC ANALYSIS\n\n"
        if validation_text:
            user_message += f"Validation result: `{validation_text}`\n\n"
        if bp_result:
            compact_bp = {
                "score": bp_result.get("score"),
                "max": bp_result.get("max"),
                "issues": bp_result.get("issues", []),
                "categories": bp_result.get("categories", {}),
            }
            user_message += f"Best-practices/static-analysis result:\n```json\n{json.dumps(compact_bp, indent=2)}\n```\n\n"
        user_message += "Treat deterministic failures as binding when assigning scores.\n\n"
    user_message += f"## GENERATED SCRIPT\n\n```javascript\n{script_text}\n```"

    cmd = ["opencode", "run", "--format", "json"]
    if judge_model:
        cmd.extend(["--model", judge_model])
    cmd.append(user_message)

    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=120
        )
        output = result.stdout
    except subprocess.TimeoutExpired:
        return {"error": "opencode timed out", "dir": results_dir}

    # Extract text parts from JSON events
    text_parts = []
    for line in output.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
            if event.get("type") == "text":
                text_parts.append(event["part"]["text"])
        except (json.JSONDecodeError, KeyError):
            continue

    full_text = "".join(text_parts).strip()

    # Extract JSON from the response — the LLM may include prose around it.
    # Strategy: try the full text first, then look for fenced JSON, then find
    # the first { ... } block that parses.
    scores = _extract_json(full_text)
    if scores is not None:
        required = {"adherence", "quality", "complexity", "robustness", "completeness", "total", "notes"}
        if not required.issubset(scores.keys()):
            missing = required - scores.keys()
            scores["warning"] = f"missing keys: {missing}"
        scores["script"] = os.path.relpath(script_file, results_dir)
        scores["gold"] = has_gold
        scores["validation"] = validation_text
        scores["blinded"] = blinded
        return _apply_hard_caps(scores, validation_text, bp_result)

    return {
        "error": "failed to parse judge response as JSON",
        "raw_response": full_text[:500],
        "dir": results_dir,
    }


def main():
    parser = argparse.ArgumentParser(description="Score a k6 script with an LLM judge")
    parser.add_argument("results_dir", help="Path to a single results directory")
    parser.add_argument(
        "--judge-model",
        default=None,
        help="Model to use for judging (provider/model format)",
    )
    parser.add_argument(
        "--gold-dir",
        default=None,
        help="Directory containing gold standard scripts (gold/s<N>.js)",
    )
    parser.add_argument(
        "--no-blind",
        action="store_true",
        help="Do not strip skill-identifying `// Generated by ...` headers before judging (default: blind).",
    )
    args = parser.parse_args()

    if not os.path.isdir(args.results_dir):
        print(json.dumps({"error": f"not a directory: {args.results_dir}"}))
        sys.exit(1)

    scores = judge(
        args.results_dir,
        args.judge_model,
        args.gold_dir,
        blind=not args.no_blind,
    )
    print(json.dumps(scores, indent=2))


if __name__ == "__main__":
    main()
