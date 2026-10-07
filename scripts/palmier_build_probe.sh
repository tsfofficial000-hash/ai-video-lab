#!/usr/bin/env bash
# =============================================================================
# TEST E (part 2) — Palmier Pro build + headless launch probe (macOS runner).
# Attempts a SwiftPM build (time-boxed by the workflow step) and, if a binary
# emerges, probes whether it can run/serve MCP without a GUI session.
# =============================================================================
set -uo pipefail
log(){ echo "[PALMIER] $*"; }
metric(){ echo "[METRIC] palmier_$1=$2" | tee -a palmier_metrics.txt; }

cd "$RUNNER_TEMP/palmier-pro" 2>/dev/null || { log "palmier-pro not found - run analyze step first"; exit 0; }

# ---------- 1. Dependency resolution ----------
log "swift package resolve (time-boxed)..."
T0=$(date +%s)
swift package resolve 2>&1 | tail -8
metric spm_resolve_exit "${PIPESTATUS[0]}"
metric spm_resolve_seconds "$(( $(date +%s) - T0 ))"

# ---------- 2. Build attempt (debug; release opt too slow for CI) ----------
log "swift build (time-boxed by step timeout)..."
T1=$(date +%s)
swift build 2>&1 | tail -30
RC=${PIPESTATUS[0]}
metric swift_build_exit "$RC"
metric swift_build_seconds "$(( $(date +%s) - T1 ))"

BIN=".build/debug/PalmierPro"
if [ $RC -eq 0 ] && [ -x "$BIN" ]; then
  metric binary_built yes
  log "binary built: $BIN"

  # ---------- 3. Headless launch probe ----------
  log "attempting headless launch (expecting GUI/NSApplication behavior)..."
  nohup "$BIN" > palmier_launch.log 2>&1 &
  APP_PID=$!
  sleep 12
  if kill -0 "$APP_PID" 2>/dev/null; then
    metric headless_process_alive_after_12s yes
    log "process alive - probing embedded MCP HTTP endpoint"
    curl -s -m 5 -o mcp_probe_out.txt -w "http_code=%{http_code}\n" http://127.0.0.1:19789/mcp > mcp_probe_meta.txt 2>&1
    cat mcp_probe_meta.txt; head -c 400 mcp_probe_out.txt 2>/dev/null; echo
    metric mcp_endpoint_probe "$(head -1 mcp_probe_meta.txt 2>/dev/null)"
    kill -9 "$APP_PID" 2>/dev/null
  else
    wait "$APP_PID" 2>/dev/null
    metric headless_process_alive_after_12s no
    metric headless_exit_code "$?"
  fi
  echo "--- launch log (head) ---"; head -20 palmier_launch.log 2>/dev/null
else
  metric binary_built no
  log "binary NOT built (exit=$RC). On a 5-core hosted runner this is itself the finding: build exceeds CI budget."
fi
echo "[PALMIER-BUILD-DONE]"
