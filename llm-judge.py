#!/usr/bin/env python3
"""
llm-judge.py — Score a generated k6 script against its original prompt.

Uses `opencode run` to call an LLM with a structured rubric. Returns JSON
scores on five dimensions (1-5 each, 25 max).

Usage:
    python3 llm-judge.py <results-dir> [--judge-model <provider/model>]

The results dir must contain:
    prompt.txt          — the original prompt
    k6/scripts/*.js     — the generated script (first .js file found)

Output (stdout): JSON object with scores and notes.
"""

import argparse
import json
import os
import subprocess
import sys
from glob import glob
from pathlib import Path

RUBRIC = """\
You are a k6 load testing script quality judge. You will be given an ORIGINAL PROMPT \
that describes what script should be generated, and the GENERATED SCRIPT that was produced.

Score the script on each dimension below using an integer from 1 to 5.

## Dimensions

### 1. Prompt Adherence (adherence)
Does the script implement what was asked?
- 5: Every requirement from the prompt is implemented correctly (endpoints, executor, VU counts, thresholds, assertions, file name)
- 4: One minor requirement missed or slightly off (e.g. threshold value differs)
- 3: Core functionality present but multiple requirements missed
- 2: Partially implements the prompt, significant gaps
- 1: Does not match the prompt at all

### 2. Code Quality (quality)
Is the code readable, well-structured, and idiomatic k6?
- 5: Clean imports, descriptive variable names, helpful comments, logical grouping, idiomatic k6 patterns
- 4: Minor naming or style issues, but well-structured overall
- 3: Functional but messy — poor names, unnecessary complexity, or confusing structure
- 2: Hard to read, inconsistent style, misleading comments
- 1: Unreadable or fundamentally broken structure

### 3. Complexity Appropriateness (complexity)
Is the complexity proportional to what was asked?
- 5: Exactly right — no unnecessary abstraction, no missing pieces
- 4: Slightly over- or under-engineered but reasonable
- 3: Noticeably over-engineered (unnecessary helpers, excessive config) or too simplistic
- 2: Significantly mismatched complexity
- 1: Wildly over- or under-engineered

### 4. Robustness (robustness)
Would this script give useful signal if something went wrong?
- 5: Comprehensive check() assertions, meaningful thresholds, proper resource cleanup (client.close(), page.close() in finally), graceful handling
- 4: Good assertions and thresholds, minor cleanup gap
- 3: Basic checks present but gaps in error handling or thresholds
- 2: Minimal assertions, would silently pass on failures
- 1: No meaningful assertions or error handling

### 5. Runnable Completeness (completeness)
Can you copy-paste this and run it without modification?
- 5: Every import used, every variable defined, no TODOs/stubs/placeholders, realistic defaults
- 4: One minor placeholder that wouldn't prevent execution (e.g. a comment saying "replace with your token")
- 3: A few stubs or unused imports, but would likely run
- 2: Has TODOs or undefined references that would cause runtime errors
- 1: Incomplete — would not execute at all

## Response Format

Return ONLY a JSON object, no markdown fencing, no explanation outside the JSON:

{
    "adherence": <1-5>,
    "quality": <1-5>,
    "complexity": <1-5>,
    "robustness": <1-5>,
    "completeness": <1-5>,
    "total": <sum of above, 5-25>,
    "notes": "<1-2 sentences explaining the most significant strength or weakness>"
}
"""


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


def judge(results_dir: str, judge_model: str | None = None) -> dict:
    prompt_file = os.path.join(results_dir, "prompt.txt")
    if not os.path.isfile(prompt_file):
        return {"error": "no prompt.txt found", "dir": results_dir}

    prompt_text = Path(prompt_file).read_text().strip()

    script_file = find_script(results_dir)
    if not script_file:
        return {"error": "no script file found", "dir": results_dir}

    script_text = Path(script_file).read_text().strip()

    user_message = (
        f"{RUBRIC}\n\n"
        f"## ORIGINAL PROMPT\n\n{prompt_text}\n\n"
        f"## GENERATED SCRIPT\n\n```javascript\n{script_text}\n```"
    )

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
        return scores

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
    args = parser.parse_args()

    if not os.path.isdir(args.results_dir):
        print(json.dumps({"error": f"not a directory: {args.results_dir}"}))
        sys.exit(1)

    scores = judge(args.results_dir, args.judge_model)
    print(json.dumps(scores, indent=2))


if __name__ == "__main__":
    main()
