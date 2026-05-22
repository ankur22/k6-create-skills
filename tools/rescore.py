#!/usr/bin/env python3
"""
tools/rescore.py - Re-apply the new bp-check categorization and llm-judge
hard caps to an existing comparison run, without calling the LLM again.

Usage:
    python3 tools/rescore.py <scripts-dir>
    python3 tools/rescore.py <scripts-dir> --comparison <md> --judge <md> --output <md>

Reads:
    <scripts-dir>/s<N>-<skill>/      run directories
    results/comparison-<ts>.md        validation values per run
    results/judge-<ts>.md             original LLM scores per run

Writes:
    <scripts-dir>/s<N>-<skill>/bp.json         new categorized checker output
    <scripts-dir>/s<N>-<skill>/validation.txt  backfilled validation result
    results/rescore-<ts>.md                    before/after comparison report
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "scenario-manifest.json"


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


bp_check = _load_module("bp_check", ROOT / "bp-check.py")
llm_judge = _load_module("llm_judge", ROOT / "llm-judge.py")


def parse_comparison(path: Path) -> dict[str, dict[str, str]]:
    out: dict[str, dict[str, str]] = {}
    if not path.exists():
        return out
    for line in path.read_text().splitlines():
        if not re.match(r"^\| S\d+ \|", line):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) < 7:
            continue
        scen, skill, _model, validation, bp = cells[:5]
        key = f"{scen.lower()}-{skill}"
        out[key] = {"validation": validation, "bp": bp}
    return out


def parse_judge(path: Path) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    if not path.exists():
        return out
    for line in path.read_text().splitlines():
        if not re.match(r"^\| S\d+ \|", line):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) < 10:
            continue
        scen, skill = cells[0], cells[1]
        key = f"{scen.lower()}-{skill}"
        try:
            out[key] = {
                "adherence": int(cells[4]),
                "quality": int(cells[5]),
                "complexity": int(cells[6]),
                "robustness": int(cells[7]),
                "completeness": int(cells[8]),
                "total": int(cells[9]),
                "notes": cells[10] if len(cells) > 10 else "",
            }
        except ValueError:
            out[key] = {"error": True, "notes": cells[10] if len(cells) > 10 else ""}
    return out


def find_script(run_dir: Path) -> Path | None:
    primary = sorted((run_dir / "k6" / "scripts").glob("*.js")) if (run_dir / "k6" / "scripts").exists() else []
    if primary:
        return primary[0]
    candidates = sorted(p for p in run_dir.rglob("*.js") if p.name != "generated.js")
    if candidates:
        return candidates[0]
    gen = run_dir / "generated.js"
    if gen.exists():
        return gen
    return None


def scen_from_name(name: str) -> str | None:
    m = re.match(r"^s(\d+)-", name)
    return m.group(1) if m else None


def latest_judge(results_dir: Path, timestamp: str) -> Path | None:
    candidates = sorted(results_dir.glob("judge-*.md"))
    return candidates[-1] if candidates else None


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("scripts_dir")
    parser.add_argument("--comparison", default=None)
    parser.add_argument("--judge", default=None)
    parser.add_argument("--output", default=None)
    args = parser.parse_args()

    scripts_dir = Path(args.scripts_dir).resolve()
    timestamp = scripts_dir.name.replace("scripts-", "")

    comparison_path = Path(args.comparison) if args.comparison else ROOT / "results" / f"comparison-{timestamp}.md"
    judge_path = Path(args.judge) if args.judge else latest_judge(ROOT / "results", timestamp)
    output = Path(args.output) if args.output else ROOT / "results" / f"rescore-{timestamp}.md"

    comparison = parse_comparison(comparison_path)
    judge = parse_judge(judge_path) if judge_path else {}

    rows: list[dict[str, Any]] = []
    for run_dir in sorted(p for p in scripts_dir.iterdir() if p.is_dir()):
        name = run_dir.name
        scen = scen_from_name(name)
        if not scen:
            continue
        skill = name[len(f"s{scen}-"):]
        meta = comparison.get(name, {})
        validation = meta.get("validation")
        old_bp = meta.get("bp", "n/a")
        old_judge = judge.get(name, {})

        if validation:
            (run_dir / "validation.txt").write_text(f"{validation}\n")

        script = find_script(run_dir)
        new_bp = bp_check.score(
            str(script) if script else None,
            scenario=scen,
            manifest_path=str(MANIFEST),
            result_dir=str(run_dir),
        )
        (run_dir / "bp.json").write_text(json.dumps(new_bp, indent=2) + "\n")

        if not old_judge or old_judge.get("error"):
            base = {"adherence": 0, "quality": 0, "complexity": 0, "robustness": 0, "completeness": 0}
            capped = llm_judge._apply_hard_caps(dict(base), validation, new_bp)
            old_total: Any = "err" if old_judge.get("error") else "n/a"
            new_total = capped["total"]
            caps = capped.get("caps_applied", []) + ["pre-existing failure preserved"]
        else:
            base = {
                "adherence": old_judge["adherence"],
                "quality": old_judge["quality"],
                "complexity": old_judge["complexity"],
                "robustness": old_judge["robustness"],
                "completeness": old_judge["completeness"],
            }
            capped = llm_judge._apply_hard_caps(dict(base), validation, new_bp)
            old_total = old_judge["total"]
            new_total = capped["total"]
            caps = capped.get("caps_applied", [])

        rows.append({
            "name": name,
            "scen": scen,
            "skill": skill,
            "old_bp": old_bp,
            "new_bp": f"{new_bp['score']}/{new_bp['max']}",
            "manifest": new_bp.get("manifest"),
            "validation": validation,
            "old_total": old_total,
            "new_total": new_total,
            "caps": [c for c in caps if "score normalization" not in c],
            "issues": new_bp.get("issues", []),
        })

    lines: list[str] = [
        f"# Rescore report - {scripts_dir.name}",
        "",
        f"Source comparison: `{comparison_path.name}`",
        f"Source judge:      `{judge_path.name if judge_path else 'none'}`",
        "",
        "## Per-run before/after",
        "",
        "| Scenario | Skill | Validation | BP old | BP new | Manifest | Judge old | Judge new | Delta | Caps applied |",
        "|----------|-------|------------|--------|--------|----------|-----------|-----------|-------|--------------|",
    ]
    for r in rows:
        delta = ""
        if isinstance(r["new_total"], int) and isinstance(r["old_total"], int):
            d = r["new_total"] - r["old_total"]
            delta = f"{d:+d}"
        caps = "; ".join(r["caps"])[:200] if r["caps"] else ""
        lines.append(
            f"| S{r['scen']} | {r['skill']} | {r['validation'] or 'n/a'} | {r['old_bp']} | "
            f"{r['new_bp']} | {'yes' if r['manifest'] else 'no'} | {r['old_total']} | {r['new_total']} | "
            f"{delta} | {caps} |"
        )

    by_skill: dict[str, dict[str, list[float]]] = defaultdict(
        lambda: {
            "old_all": [],
            "new_all": [],
            "old_passing": [],
            "new_passing": [],
            "bp_old": [],
            "bp_new": [],
            "failures": [],
        }
    )
    for r in rows:
        skill_data = by_skill[r["skill"]]
        old_is_int = isinstance(r["old_total"], int)
        new_is_int = isinstance(r["new_total"], int)
        if old_is_int:
            skill_data["old_all"].append(float(r["old_total"]))
            if r["old_total"] > 0:
                skill_data["old_passing"].append(float(r["old_total"]))
        if new_is_int:
            skill_data["new_all"].append(float(r["new_total"]))
            if r["new_total"] > 0:
                skill_data["new_passing"].append(float(r["new_total"]))
        if (new_is_int and r["new_total"] == 0) or r["old_total"] == "err":
            skill_data["failures"].append(r["name"])
        for label, value in (("bp_old", r["old_bp"]), ("bp_new", r["new_bp"])):
            if isinstance(value, str) and "/" in value:
                a, b = value.split("/")
                try:
                    skill_data[label].append(int(a) / int(b) * 100.0)
                except (ValueError, ZeroDivisionError):
                    pass

    def avg(values: list[float]) -> str:
        return f"{sum(values) / len(values):.2f}" if values else "n/a"

    def avg_pct(values: list[float]) -> str:
        return f"{sum(values) / len(values):.1f}%" if values else "n/a"

    lines += [
        "",
        "## Summary by skill",
        "",
        "Two views: **including failures** (S27 no-script counts as 0) and",
        "**passing only** (apples-to-apples comparison ignoring no-script runs).",
        "",
        "| Skill | N | Judge old (all) | Judge new (all) | Judge old (passing) | Judge new (passing) | BP old | BP new | Failures |",
        "|-------|---|-----------------|-----------------|---------------------|---------------------|--------|--------|----------|",
    ]
    for skill, data in sorted(by_skill.items()):
        n = max(len(data["new_all"]), len(data["old_all"]))
        failures = len(data["failures"])
        lines.append(
            f"| {skill} | {n} | {avg(data['old_all'])} | {avg(data['new_all'])} | "
            f"{avg(data['old_passing'])} | {avg(data['new_passing'])} | "
            f"{avg_pct(data['bp_old'])} | {avg_pct(data['bp_new'])} | {failures} |"
        )

    # Movers: top N largest changes per skill.
    lines += [
        "",
        "## Biggest judge-score changes",
        "",
        "| Scenario | Skill | Delta | Caps applied |",
        "|----------|-------|-------|--------------|",
    ]
    movers = [
        r for r in rows
        if isinstance(r["new_total"], int) and isinstance(r["old_total"], int)
        and r["new_total"] != r["old_total"]
    ]
    movers.sort(key=lambda r: abs(r["new_total"] - r["old_total"]), reverse=True)
    for r in movers[:15]:
        delta = r["new_total"] - r["old_total"]
        caps = "; ".join(r["caps"])[:180] if r["caps"] else ""
        lines.append(f"| S{r['scen']} | {r['skill']} | {delta:+d} | {caps} |")

    cap_kinds = defaultdict(int)
    for r in rows:
        for c in r["caps"]:
            kind = c.split(":")[0]
            cap_kinds[kind] += 1
    if cap_kinds:
        lines += [
            "",
            "## Cap-application frequency",
            "",
            "| Cap | Count |",
            "|-----|-------|",
        ]
        for kind, count in sorted(cap_kinds.items(), key=lambda kv: -kv[1]):
            lines.append(f"| {kind} | {count} |")

    output.write_text("\n".join(lines) + "\n")
    print(str(output))


if __name__ == "__main__":
    main()
