#!/usr/bin/env bash
# =============================================================================
# TEST C — Editly (Node.js/JSON) complex edit.
#   1. shared fixture + whisper SRT
#   2. generate Editly JSON spec from the SRT (AI-agent-style templating)
#   3. render with editly 0.14.2 (node-canvas + bundled ffmpeg)
#   4. hybrid FFmpeg loudnorm pass (Editly has no loudness normalization)
#   5. validate
# NOTE: requires Node 18 (set via actions/setup-node in the workflow).
# =============================================================================
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
WORK="$ROOT/work"
mkdir -p "$WORK"; cd "$WORK" || exit 1

metric(){ echo "[METRIC] $1=$2" | tee -a metrics.txt; }
fail(){ echo "[FAIL-C] $*" | tee -a metrics.txt; exit 1; }
T_ALL=$(date +%s)

echo "[LAB-C] node version: $(node --version)"

# ---------- 1. Fixture + master (comparison reference) + SRT ----------
bash "$ROOT/scripts/build_master.sh" || fail "fixture/master build failed"
bash "$ROOT/scripts/gen_subs.sh" || fail "whisper SRT generation failed"

# ---------- 2. JSON spec generation ----------
python3 "$ROOT/scripts/gen_editly_spec.py" subs.srt > spec.json 2> spec_gen.log \
  || fail "spec generation failed"
echo "[LAB-C] spec.json:"; head -40 spec.json
python3 -c "import json;json.load(open('spec.json'))" || fail "spec.json is not valid JSON"

# ---------- 3. Install + render ----------
if [ ! -x node_modules/.bin/editly ]; then
  T_N0=$(date +%s)
  # headless-gl source-build needs the full X/GL header set; canvas has
  # prebuilds for Node 18. Full npm output captured for forensics.
  npm install editly@0.14.2 --no-fund --no-audit > npm_install.log 2>&1
  RC=$?
  metric editly_npm_install_seconds "$(( $(date +%s) - T_N0 ))"
  if [ $RC -ne 0 ]; then
    echo "--- npm_install.log tail (80) ---"
    tail -80 npm_install.log
    echo "--- npm debug logs ---"
    ls -t /home/runner/.npm/_logs/ 2>/dev/null | head -2 | while read -r f; do
      echo "### $f"; tail -40 "/home/runner/.npm/_logs/$f"; done
    fail "npm install editly rc=$RC (see npm_install.log tail above)"
  fi
fi
[ -x node_modules/.bin/editly ] || fail "editly binary not found after install"

T0=$(date +%s)
./node_modules/.bin/editly spec.json 2>&1 | tail -25
RC=${PIPESTATUS[0]}
[ $RC -eq 0 ] || fail "editly render rc=$RC"
T1=$(date +%s)
metric editly_render_seconds "$((T1-T0))"

# ---------- 4. Hybrid loudnorm pass ----------
ffmpeg -y -v error -i final_editly.mp4 -c:v copy -shortest \
  -af "loudnorm=I=-16:TP=-1.5:LRA=11,aresample=48000" -c:a aac -b:a 192k \
  final_editly_norm.mp4 || fail "loudnorm pass failed"

# ---------- 5. Validate ----------
ffprobe -v error -show_entries format=duration,size:stream=codec_name,width,height -of json final_editly_norm.mp4 > editly_probe.json
FD=$(ffprobe -v error -show_entries format=duration -of csv=p=0 final_editly_norm.mp4)
FS=$(stat -c%s final_editly_norm.mp4)
FW=$(ffprobe -v error -select_streams v:0 -show_entries stream=width -of csv=p=0 final_editly_norm.mp4)
FH=$(ffprobe -v error -select_streams v:0 -show_entries stream=height -of csv=p=0 final_editly_norm.mp4)
metric editly_final_resolution "${FW}x${FH}"
metric editly_final_duration "$FD"
metric editly_final_size_mb "$(awk -v s="$FS" 'BEGIN{printf "%.1f", s/1048576}')"
ffmpeg -y -v error -ss 5 -i final_editly_norm.mp4 -frames:v 1 thumbnail_editly.jpg
metric editly_total_wall_seconds "$(( $(date +%s) - T_ALL ))"
echo "[DONE-C]"
