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
  # --ignore-scripts: install all JS deps first, then patch the 2018-era
  # ANGLE header in gl@5 (uses uintptr_t without <cstdint>; modern GCC-11+
  # rejects it) and only THEN compile the native modules (gl, canvas).
  npm install editly@0.14.2 --ignore-scripts --no-fund --no-audit > npm_install.log 2>&1
  RC=$?
  metric editly_npm_install_seconds "$(( $(date +%s) - T_N0 ))"
  if [ $RC -ne 0 ]; then
    echo "--- npm_install.log tail (80) ---"; tail -80 npm_install.log
    fail "npm install editly rc=$RC"
  fi
  echo "[LAB-C] patching node_modules/gl/angle/src/common/angleutils.h for modern GCC..."
  sed -i 's|^#include <vector>$|#include <vector>\n#include <cstdint>|' \
    node_modules/gl/angle/src/common/angleutils.h
  grep -q "include <cstdint>" node_modules/gl/angle/src/common/angleutils.h \
    && echo "[LAB-C] patch applied" || echo "[LAB-C] WARNING: patch pattern missed"
  npm rebuild gl canvas > npm_rebuild.log 2>&1
  RC=$?
  if [ $RC -ne 0 ]; then
    echo "--- npm_rebuild.log tail (60) ---"; tail -60 npm_rebuild.log
    fail "npm rebuild gl canvas rc=$RC"
  fi
  metric editly_native_rebuild ok
fi
[ -x node_modules/.bin/editly ] || fail "editly binary not found after install"

T0=$(date +%s)
./node_modules/.bin/editly spec.json > editly_render.log 2>&1
RC=$?
if [ $RC -ne 0 ]; then
  echo "[LAB-C] direct render failed (rc=$RC) — retrying under xvfb (headless-GL display)..."
  tail -12 editly_render.log
  command -v xvfb-run >/dev/null 2>&1 || sudo apt-get install -y -qq xvfb >/dev/null
  xvfb-run -a ./node_modules/.bin/editly spec.json >> editly_render.log 2>&1
  RC=$?
fi
tail -18 editly_render.log
[ $RC -eq 0 ] || fail "editly render rc=$RC (direct + xvfb)"
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
