#!/usr/bin/env bash
# =============================================================================
# push_logs.sh — persist a run's condensed logs into logs/<tool>/ on main.
#   1. writes logs/<tool>/run-$RUN_ID.md  ([METRIC] digest + log tail)
#   2. commits everything under logs/<tool>/ — git push first (verbose),
#      git-data-API fallback (scripts/api_commit.py) if push fails.
# Usage: JOB_STATUS=success push_logs.sh <tool> <primary_log_file>
# (caller may pre-copy extra evidence files into logs/<tool>/ first)
# =============================================================================
set -uo pipefail
TOOL="${1:?tool name required}"
PRIMARY_LOG="${2:?primary log file required}"
cd "${GITHUB_WORKSPACE:-$(pwd)}" || exit 1
STATUS="${JOB_STATUS:-unknown}"

mkdir -p "logs/$TOOL"
OUT="logs/$TOOL/run-${GITHUB_RUN_ID:-local}.md"
{
  echo "# \`${TOOL}\` — run ${GITHUB_RUN_ID:-local} @ ${GITHUB_SHA:0:7} (${GITHUB_EVENT_NAME:-manual})"
  echo
  echo "- Result: \`$STATUS\`"
  echo
  echo "## [METRIC] digest"
  echo '```text'
  { cat work/metrics.txt 2>/dev/null
    grep -hE '^\[(METRIC|LAB|WARN|FAIL|DONE|SRT-WRITTEN|SUBS|MASTER|FETCH|SPEC|TIME-SHIM|PALMIER|API-COMMIT|PUSH-LOGS)' "$PRIMARY_LOG" 2>/dev/null
  } | sort -u || true
  echo '```'
  echo
  echo "## Log tail (last 60 lines of $PRIMARY_LOG)"
  echo '```text'
  tail -60 "$PRIMARY_LOG" 2>/dev/null || echo "(missing)"
  echo '```'
} > "$OUT"

echo "=== git push attempt (verbose) ==="
git config user.name "ai-video-lab-bot"
git config user.email "github-actions[bot]@users.noreply.github.com"
git add -f "logs/$TOOL/" 2>/dev/null || true
git commit -m "logs($TOOL): run ${GITHUB_RUN_ID:-local} — $STATUS" 2>&1 | tail -3 || true
ok=0
for i in 1 2 3; do
  echo "--- push attempt $i: pull --rebase then push ---"
  git pull --rebase origin main 2>&1 | tail -3 || true
  git push origin HEAD:main 2>&1 | tail -6
  [ ${PIPESTATUS[0]} -eq 0 ] && ok=1 && break
  sleep 8
done
if [ "$ok" -eq 1 ]; then
  echo "[PUSH-LOGS] git push ok"
  exit 0
fi
echo "[PUSH-LOGS] git push failed after 3 attempts — falling back to git-data API"
FILES=$(find "logs/$TOOL" -type f | head -20)
echo "[PUSH-LOGS] API commit of: $FILES"
python3 scripts/api_commit.py -m "logs($TOOL): run ${GITHUB_RUN_ID:-local} — $STATUS" $FILES \
  || echo '::warning::could not push logs via git or API'
