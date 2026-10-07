#!/usr/bin/env bash
# =============================================================================
# TEST E2 — Agent-driven headless edit through Palmier Pro's embedded MCP
# server (HTTP 127.0.0.1:19789/mcp) on a macOS-26 CI runner.
#
# Pipeline: build -> launch app -> MCP initialize -> tools/list ->
#   manage_project(create 9:16 1080p) -> import_media (URL footage + local
#   matte) -> add_clips -> export_project(H.264) -> manage_exports poll ->
#   verify output file.
# Everything is JSON-RPC; no GUI interaction. This is the "AI-native editor
# as a CI render node" proof.
# =============================================================================
set -uo pipefail
log(){ echo "[PALMIER-E2] $*"; }
metric(){ echo "[METRIC] palmier_e2_$1=$2" | tee -a palmier_metrics.txt; }
fail(){ echo "[FAIL-E2] $*" | tee -a palmier_metrics.txt; exit 1; }

cd "$RUNNER_TEMP" 2>/dev/null || cd /tmp
rm -rf palmier-pro
log "cloning palmier-io/palmier-pro..."
git clone --depth 1 --quiet https://github.com/palmier-io/palmier-pro.git || fail "clone"
cd palmier-pro || exit 1

log "swift package resolve..."
swift package resolve > spm.log 2>&1
metric spm_resolve_exit "$?"
log "swift build (budget 10 min)..."
T0=$(date +%s)
swift build > build.log 2>&1
RC=$?
metric build_exit "$RC"
metric build_seconds "$(( $(date +%s) - T0 ))"
[ $RC -eq 0 ] || { echo "--- build.log tail ---"; tail -30 build.log; fail "swift build rc=$RC"; }
metric binary_built yes

log "launching app headless (runner GUI session)..."
nohup .build/debug/PalmierPro > launch.log 2>&1 &
APP_PID=$!
UP=""
for i in $(seq 1 30); do
  sleep 2
  if curl -s -m 2 -o /dev/null -w "" "http://127.0.0.1:19789/mcp" 2>/dev/null; then UP=yes; break; fi
done
[ -n "$UP" ] || { tail -20 launch.log; fail "MCP endpoint never came up"; }
metric mcp_endpoint_up yes
log "MCP endpoint is up"

# ---------------- minimal MCP streamable-HTTP client ----------------
SESSION=""
HDRS=/tmp/mcp_h.txt
mcp(){
  local body="$1" resp
  local args=( -s -m 180 -X POST "http://127.0.0.1:19789/mcp"
    -H "Content-Type: application/json"
    -H "Accept: application/json, text/event-stream"
    -H "MCP-Protocol-Version: 2025-06-18" )
  [ -n "$SESSION" ] && args+=( -H "Mcp-Session-Id: $SESSION" )
  args+=( -D "$HDRS" --data-binary "$body" )
  resp=$(curl "${args[@]}")
  # server may answer application/json OR an SSE stream; normalize to JSON lines
  if echo "$resp" | head -1 | grep -q "^event:\|^:"; then
    resp=$(echo "$resp" | sed -n 's/^data://p')
  fi
  # update session id if present
  local sid
  sid=$(grep -i "^mcp-session-id:" "$HDRS" 2>/dev/null | head -1 | awk '{print $2}' | tr -d '\r')
  [ -n "$sid" ] && SESSION="$sid"
  echo "$resp"
}
tool_call(){
  local id="$1" name="$2" args="$3"
  mcp "{\"jsonrpc\":\"2.0\",\"id\":$id,\"method\":\"tools/call\",\"params\":{\"name\":\"$name\",\"arguments\":$args}}"
}
json_get(){  # json_get <json> <python-expr over d>
  echo "$1" | python3 -c "
import json,sys
d=json.load(sys.stdin)
try:
    print($2)
except Exception as e:
    print('')
" 2>/dev/null
}

# ---------------- 1. initialize ----------------
INIT=$(mcp '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"ai-video-lab","version":"1.0"}}}')
SERVER_NAME=$(json_get "$INIT" "d['result']['serverInfo']['name']")
[ -n "$SERVER_NAME" ] || { echo "$INIT" | head -5; fail "initialize failed"; }
metric server_info "$SERVER_NAME"
log "initialized: serverInfo.name=$SERVER_NAME session=$SESSION"
mcp '{"jsonrpc":"2.0","method":"notifications/initialized"}' >/dev/null

# ---------------- 2. tools/list ----------------
TL=$(mcp '{"jsonrpc":"2.0","id":2,"method":"tools/list","params":{}}')
NT=$(json_get "$TL" "len(d['result']['tools'])")
metric tools_listed "$NT"
log "tools listed: $NT"
echo "$TL" | python3 -c "
import json,sys
d=json.load(sys.stdin)
names=[t['name'] for t in d['result']['tools']]
print('[PALMIER-E2] tools:', ', '.join(names))
" 2>/dev/null | tee -a palmier_metrics.txt || true

# ---------------- 3. create project ----------------
P=$(tool_call 3 manage_project '{"action":"create","name":"lab-e2e","aspectRatio":"9:16","quality":"1080p","fps":30}')
PT=$(json_get "$P" "json.dumps(d['result'])[:300]")
[ -n "$PT" ] || { echo "$P" | head -5; fail "manage_project create failed"; }
log "project created: $PT"

# ---------------- 4. import media ----------------
MATTE=$(tool_call 4 import_media '{"source":{"matte":{"hex":"#16233F","aspectRatio":"9:16"}},"name":"LabMatte"}')
MREF_MATTE=$(json_get "$MATTE" "d['result']['content'][0]['text'] and json.loads([c['text'] for c in d['result']['content'] if c['type']=='text'][0]).get('mediaRef','')")
[ -n "$MREF_MATTE" ] || { echo "$MATTE" | head -8; log "matte import parse failed (continuing)"; }
metric matte_media_ref "${MREF_MATTE:-none}"

FOOTAGE=$(tool_call 5 import_media '{"source":{"url":"https://download.blender.org/durian/trailer/sintel_trailer-1080p.mp4"},"name":"Sintel1080"}')
MREF_FOOT=$(json_get "$FOOTAGE" "json.loads([c['text'] for c in d['result']['content'] if c['type']=='text'][0]).get('mediaRef','')")
[ -n "$MREF_FOOT" ] || log "URL import start parse failed — relying on matte"
metric footage_media_ref "${MREF_FOOT:-none}"

# wait for the URL import (background download) up to 5 min
if [ -n "$MREF_FOOT" ]; then
  READY=""
  for i in $(seq 1 60); do
    sleep 5
    GM=$(tool_call 6 get_media "{\"ids\":[\"$MREF_FOOT\"]}")
    ST=$(json_get "$GM" "str(json.loads([c['text'] for c in d['result']['content'] if c['type']=='text'][0]))[:200]")
    echo "[PALMIER-E2] get_media poll $i: $ST"
    if echo "$ST" | grep -q "ready\| Ready"; then READY=yes; break; fi
  done
  metric footage_import_ready "${READY:-timeout}"
fi

# ---------------- 5. add clips ----------------
PRIMARY="${MREF_FOOT:-$MREF_MATTE}"
[ -n "$PRIMARY" ] || fail "no mediaRef available"
ADD=$(tool_call 7 add_clips "{\"entries\":[{\"mediaRef\":\"$PRIMARY\",\"startFrame\":0,\"source\":[3.0,9.0]}]}")
AT=$(json_get "$ADD" "json.dumps(d['result'])[:300]")
[ -n "$AT" ] || { echo "$ADD" | head -8; fail "add_clips failed"; }
log "add_clips ok: $AT"

# ---------------- 6. export ----------------
EX=$(tool_call 8 export_project '{"mode":"video","codec":"H.264","outputPath":"/tmp/palmier_e2_export.mp4"}')
EXT=$(json_get "$EX" "json.dumps(d['result'])[:400]")
[ -n "$EXT" ] || { echo "$EX" | head -8; fail "export_project failed"; }
log "export queued: $EXT"
JOB=$(json_get "$EX" "json.loads([c['text'] for c in d['result']['content'] if c['type']=='text'][0]).get('jobId','')")

# ---------------- 7. poll exports ----------------
if [ -n "$JOB" ]; then
  DONE=""
  for i in $(seq 1 40); do
    sleep 6
    ME=$(tool_call 9 manage_exports "{\"action\":\"list\"}")
    ST=$(json_get "$ME" "json.dumps(d['result'])[:300]")
    echo "[PALMIER-E2] export poll $i: $ST"
    if echo "$ST" | grep -q "completed\|Completed\|success"; then DONE=yes; break; fi
    if echo "$ST" | grep -q "failed\|Failed"; then break; fi
  done
  metric export_job_completed "${DONE:-timeout_or_failed}"
fi

# ---------------- 8. verify ----------------
if [ -s /tmp/palmier_e2_export.mp4 ]; then
  SZ=$(stat -f%z /tmp/palmier_e2_export.mp4)
  metric export_file_bytes "$SZ"
  metric export_verified yes
  cp /tmp/palmier_e2_export.mp4 "$RUNNER_TEMP/../work/" 2>/dev/null || true
  cp /tmp/palmier_e2_export.mp4 palmier_e2_export.mp4 2>/dev/null || true
  command -v ffprobe >/dev/null 2>&1 && ffprobe -v error -show_entries format=duration,size:stream=codec_name,width,height -of json /tmp/palmier_e2_export.mp4 > e2_probe.json || true
  [ -s e2_probe.json ] && cat e2_probe.json
else
  metric export_verified no
  log "export file missing — capturing app diagnostics"
  tail -30 launch.log
fi
kill -9 "$APP_PID" 2>/dev/null
echo "[PALMIER-E2-DONE]"
