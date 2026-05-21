#!/usr/bin/env bash
# judge-run.sh — Run the LLM judge across a set of comparison results.
#
# Usage:
#   ./judge-run.sh <scripts-dir>                           Judge all results in the directory
#   ./judge-run.sh <scripts-dir> --judge-model <model>     Use a specific model for judging
#   ./judge-run.sh <scripts-dir> --gold-dir <dir>          Gold standard scripts (default: gold/)
#   ./judge-run.sh <scripts-dir> --parallel N              Run N judges in parallel (default: 2)
#   ./judge-run.sh --help                                  Show this help
#
# The <scripts-dir> should be a results/scripts-<timestamp> directory from compare.sh.
# Each subdirectory (s1-skill-model/) must contain prompt.txt and a .js script.
#
# If --gold-dir is provided (or gold/ exists), scenarios with a matching gold/s<N>.js
# file will be scored against the reference implementation for stricter evaluation.
#
# Output: results/judge-<timestamp>.md with per-script scores and a summary table.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
TIMESTAMP=$(date +%Y%m%d-%H%M%S)

JUDGE_MODEL=""
GOLD_DIR=""
PARALLEL=2
SCRIPTS_DIR=""

# ── Argument parsing ──────────────────────────────────────────────────────────

usage() {
  awk '/^#!/{next} /^#/{print substr($0,3)} /^[^#]/{exit}' "$0"
  exit 0
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --help|-h)        usage ;;
    --judge-model)    JUDGE_MODEL="$2"; shift 2 ;;
    --gold-dir)       GOLD_DIR="$2";    shift 2 ;;
    --parallel)       PARALLEL="$2";    shift 2 ;;
    *)
      if [[ -z "$SCRIPTS_DIR" ]]; then
        SCRIPTS_DIR="$1"; shift
      else
        echo "error: unexpected argument: $1" >&2; exit 1
      fi
      ;;
  esac
done

if [[ -z "$SCRIPTS_DIR" ]]; then
  echo "error: <scripts-dir> is required" >&2
  echo "usage: $0 <scripts-dir> [--judge-model <model>] [--gold-dir <dir>] [--parallel N]" >&2
  exit 1
fi

if [[ ! -d "$SCRIPTS_DIR" ]]; then
  echo "error: not a directory: $SCRIPTS_DIR" >&2
  exit 1
fi

# Auto-discover gold dir if not specified
if [[ -z "$GOLD_DIR" && -d "$SCRIPT_DIR/gold" ]]; then
  GOLD_DIR="$SCRIPT_DIR/gold"
fi

# ── Output setup ──────────────────────────────────────────────────────────────

RESULTS_DIR="$SCRIPT_DIR/results"
mkdir -p "$RESULTS_DIR"
OUTPUT_FILE="$RESULTS_DIR/judge-$TIMESTAMP.md"
JUDGE_LABEL="${JUDGE_MODEL:-default}"
GOLD_LABEL="${GOLD_DIR:-none}"

echo "Judge model: $JUDGE_LABEL" >&2
echo "Gold dir:    $GOLD_LABEL" >&2
echo "Scripts dir: $SCRIPTS_DIR" >&2
echo "Parallelism: $PARALLEL" >&2
echo "" >&2

# ── Discover result directories ───────────────────────────────────────────────

# Find all subdirectories that have a prompt.txt (i.e. valid result dirs)
RESULT_DIRS=()
while IFS= read -r -d '' dir; do
  RESULT_DIRS+=("$dir")
done < <(find -L "$SCRIPTS_DIR" -maxdepth 1 -mindepth 1 -type d -print0 | sort -z)

if [[ ${#RESULT_DIRS[@]} -eq 0 ]]; then
  echo "error: no result subdirectories found in $SCRIPTS_DIR" >&2
  exit 1
fi

echo "Found ${#RESULT_DIRS[@]} result directories" >&2

# ── Run judges in parallel ────────────────────────────────────────────────────

judge_one() {
  local dir="$1"
  local json_file="$2"
  local dir_name
  dir_name=$(basename "$dir")

  if [[ ! -f "$dir/prompt.txt" ]]; then
    echo "  SKIP $dir_name (no prompt.txt)" >&2
    echo '{"error": "no prompt.txt"}' > "$json_file"
    return
  fi

  # Check for a script file (k6/scripts/*.js, generated.js, or any .js in tree)
  local has_script=false
  if compgen -G "$dir/k6/scripts/*.js" >/dev/null 2>&1; then
    has_script=true
  elif [[ -f "$dir/generated.js" ]]; then
    has_script=true
  elif find "$dir" -name "*.js" -print -quit 2>/dev/null | grep -q .; then
    has_script=true
  fi

  if ! $has_script; then
    echo "  SKIP $dir_name (no script)" >&2
    echo '{"error": "no script file"}' > "$json_file"
    return
  fi

  echo "  JUDGE $dir_name ..." >&2

  local judge_args=("$dir")
  [[ -n "$JUDGE_MODEL" ]] && judge_args+=(--judge-model "$JUDGE_MODEL")
  [[ -n "$GOLD_DIR" ]] && judge_args+=(--gold-dir "$GOLD_DIR")

  if python3 "$SCRIPT_DIR/llm-judge.py" "${judge_args[@]}" > "$json_file" 2>/dev/null; then
    local total
    total=$(python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('total','err'))" < "$json_file" 2>/dev/null || echo "err")
    echo "  DONE $dir_name -> total=$total" >&2
  else
    echo "  FAIL $dir_name" >&2
    echo '{"error": "llm-judge.py failed"}' > "$json_file"
  fi
}

# Create temp dir for individual judge results
JUDGE_TMP=$(mktemp -d)
trap 'rm -rf "$JUDGE_TMP"' EXIT

active=0
pids=()
dir_names=()

for dir in "${RESULT_DIRS[@]}"; do
  dir_name=$(basename "$dir")
  json_file="$JUDGE_TMP/${dir_name}.json"

  judge_one "$dir" "$json_file" &
  pids+=("$!")
  dir_names+=("$dir_name")
  active=$((active + 1))

  # Throttle parallelism
  if [[ $active -ge $PARALLEL ]]; then
    wait "${pids[0]}" || true
    pids=("${pids[@]:1}")
    active=$((active - 1))
  fi
done

# Wait for remaining
for pid in ${pids[@]+"${pids[@]}"}; do
  wait "$pid" || true
done

echo "" >&2

# ── Consolidate results into a table ──────────────────────────────────────────

{
  echo "# LLM Judge Results — $TIMESTAMP"
  echo ""
  echo "Judge model: \`$JUDGE_LABEL\`"
  echo "Gold dir: \`$GOLD_LABEL\`"
  echo "Scripts dir: \`$SCRIPTS_DIR\`"
  echo ""
  echo "| Scenario | Skill | Model | Gold | Adherence | Quality | Complexity | Robustness | Completeness | Total | Notes |"
  echo "|----------|-------|-------|------|-----------|---------|------------|------------|--------------|-------|-------|"
} > "$OUTPUT_FILE"

# Parse dir names like: s10-k6-create-xk6docs-claude-sonnet-4-6
parse_dir_name() {
  local name="$1"
  local scenario skill model

  # Extract scenario number: s10-... -> S10
  scenario=$(echo "$name" | grep -oE '^s[0-9]+' | sed 's/^s/S/')

  # The rest after s<N>- is skill-model or just skill
  local rest="${name#s[0-9]*-}"

  # Known skill names (longest first to avoid partial matches)
  if [[ "$rest" == k6-create-xk6docs* ]]; then
    skill="k6-create-xk6docs"
    model="${rest#k6-create-xk6docs}"
  elif [[ "$rest" == k6-create-mcp* ]]; then
    skill="k6-create-mcp"
    model="${rest#k6-create-mcp}"
  elif [[ "$rest" == grafana-k6* ]]; then
    skill="grafana-k6"
    model="${rest#grafana-k6}"
  else
    skill="$rest"
    model=""
  fi

  # Strip leading dash from model
  model="${model#-}"
  [[ -z "$model" ]] && model="default"

  echo "$scenario" "$skill" "$model"
}

for dir in "${RESULT_DIRS[@]}"; do
  dir_name=$(basename "$dir")
  json_file="$JUDGE_TMP/${dir_name}.json"

  if [[ ! -f "$json_file" ]]; then
    continue
  fi

  read -r scenario skill model <<< "$(parse_dir_name "$dir_name")"

  # Extract scores
  local_scores=$(python3 -c "
import json, sys
try:
    d = json.load(sys.stdin)
    if 'error' in d:
        print(f\"err|err|err|err|err|err|err|{d['error']}\")
    else:
        gold = 'yes' if d.get('gold') else 'no'
        print(f\"{gold}|{d.get('adherence','?')}|{d.get('quality','?')}|{d.get('complexity','?')}|{d.get('robustness','?')}|{d.get('completeness','?')}|{d.get('total','?')}|{d.get('notes','')}\")
except:
    print('err|err|err|err|err|err|err|parse error')
" < "$json_file" 2>/dev/null || echo "err|err|err|err|err|err|err|script error")

  IFS='|' read -r gold adherence quality complexity robustness completeness total notes <<< "$local_scores"

  printf "| %s | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s |\n" \
    "$scenario" "$skill" "$model" "$gold" "$adherence" "$quality" "$complexity" "$robustness" "$completeness" "$total" "$notes" >> "$OUTPUT_FILE"

  # Also save individual judge result alongside the script
  cp "$json_file" "$dir/judge.json" 2>/dev/null || true
done

# ── Summary statistics ────────────────────────────────────────────────────────

{
  echo ""
  echo "## Summary"
  echo ""
} >> "$OUTPUT_FILE"

python3 - "$JUDGE_TMP" >> "$OUTPUT_FILE" <<'PYEOF'
import json, os, sys
from collections import defaultdict

tmp_dir = sys.argv[1]
by_group = defaultdict(list)  # group = "skill|model"

for f in sorted(os.listdir(tmp_dir)):
    if not f.endswith(".json"):
        continue
    try:
        with open(os.path.join(tmp_dir, f)) as fh:
            d = json.load(fh)
        if "error" in d:
            continue
        # Parse group from filename
        name = f.replace(".json", "")
        # Extract after scenario number
        parts = name.split("-", 1)
        if len(parts) > 1:
            group = parts[1]
        else:
            group = name
        by_group[group].append(d)
    except (json.JSONDecodeError, KeyError):
        continue

if not by_group:
    print("No valid judge results to summarize.")
    sys.exit(0)

dims = ["adherence", "quality", "complexity", "robustness", "completeness", "total"]
print("| Group | N | Adherence | Quality | Complexity | Robustness | Completeness | Total |")
print("|-------|---|-----------|---------|------------|------------|--------------|-------|")

for group in sorted(by_group.keys()):
    results = by_group[group]
    n = len(results)
    avgs = {}
    for dim in dims:
        vals = [r[dim] for r in results if isinstance(r.get(dim), (int, float))]
        avgs[dim] = f"{sum(vals)/len(vals):.1f}" if vals else "n/a"
    print(f"| {group} | {n} | {avgs['adherence']} | {avgs['quality']} | {avgs['complexity']} | {avgs['robustness']} | {avgs['completeness']} | {avgs['total']} |")
PYEOF

echo "" >&2
echo "Results: $OUTPUT_FILE" >&2
cat "$OUTPUT_FILE"
