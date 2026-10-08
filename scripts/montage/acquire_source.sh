#!/usr/bin/env bash
# acquire_source.sh <youtube_url> <dest.mp4> [release_tag]
# Ladder: (1) yt-dlp multi-client on runner  (2) loader.to tunnel
#         (3) pre-uploaded GitHub release asset (guaranteed fallback)
# Env: GITHUB_TOKEN (for step 3), GH_REPO optional (defaults to origin)
set -uo pipefail

URL="${1:?youtube url}"
DEST="${2:?dest path}"
REL_TAG="${3:-source-v1}"
REPO="${GITHUB_REPOSITORY:-tsfofficial000-hash/ai-video-lab}"

log() { echo "[acquire] $*"; }

validate() {
  local f="$1"
  command -v ffprobe >/dev/null || return 1
  local dur
  dur=$(ffprobe -v error -show_entries format=duration -of csv=p=0 "$f" 2>/dev/null || echo 0)
  python3 - "$f" <<'PY'
import json, subprocess, sys
try:
    d = json.loads(subprocess.check_output(
        ["ffprobe", "-v", "error", "-print_format", "json", "-show_streams", sys.argv[1]]).decode())
    vs = [s for s in d["streams"] if s["codec_type"] == "video"]
    as_ = [s for s in d["streams"] if s["codec_type"] == "audio"]
    sys.exit(0 if (vs and len(as_) >= 1) else 1)
except Exception:
    sys.exit(1)
PY
  [ $? -eq 0 ] || return 1
  python3 -c "import sys;sys.exit(0 if float('$dur' or 0) > 8 else 1)" || return 1
  return 0
}

# ---- 1. yt-dlp multi-client -------------------------------------------------
if command -v yt-dlp >/dev/null 2>&1; then
  for client in tv android ios mweb web_embedded tv_embedded default; do
    log "yt-dlp attempt client=$client"
    if timeout 300 yt-dlp --no-warnings --force-ipv4 --socket-timeout 20 --no-playlist \
        --extractor-args "youtube:player_client=$client" \
        -f "bv*[height<=1080][vcodec^=avc1]+ba[acodec^=mp4a]/b[height<=1080][acodec^=mp4a]/bv*+ba/b" \
        --merge-output-format mp4 --ffmpeg-location "$(command -v ffmpeg)" \
        -o "$DEST.part" "$URL" 2>>yt_dlp_errors.log; then
      mv "$DEST.part" "$DEST"
      if validate "$DEST"; then log "OK via yt-dlp/$client"; exit 0; fi
    fi
  done
  log "yt-dlp exhausted all clients"
else
  log "yt-dlp not installed"
fi

# ---- 2. loader.to tunnel ----------------------------------------------------
log "trying loader.to tunnel (this can take several minutes)"
if URL_DL=$(timeout 600 python3 "$(dirname "$0")/loader_tunnel.py" "$URL" 1080 2>>loader_tunnel.log); then
  log "tunnel ready, downloading"
  curl -sL --retry 3 --max-time 900 -o "$DEST.part" "$URL_DL" && \
  mv "$DEST.part" "$DEST" && validate "$DEST" && { log "OK via loader.to tunnel"; exit 0; }
else
  log "loader.to tunnel failed (see loader_tunnel.log)"
fi

# ---- 3. release asset fallback ----------------------------------------------
log "falling back to release asset ($REL_TAG)"
if command -v gh >/dev/null 2>&1; then
  gh release download "$REL_TAG" --repo "$REPO" --pattern "*.mp4" --output "$DEST" --clobber && \
    validate "$DEST" && { log "OK via gh release"; exit 0; }
else
  API="https://api.github.com/repos/$REPO/releases/tags/$REL_TAG"
  ASSET_URL=$(curl -s -H "Authorization: Bearer $GITHUB_TOKEN" "$API" \
    | python3 -c "import json,sys;d=json.load(sys.stdin);print(next((a['url'] for a in d.get('assets',[]) if a['name'].endswith('.mp4')),''))")
  if [ -n "$ASSET_URL" ]; then
    curl -sL -H "Authorization: Bearer $GITHUB_TOKEN" --max-time 900 -o "$DEST" "$ASSET_URL" && \
      validate "$DEST" && { log "OK via API release asset"; exit 0; }
  fi
fi

log "ALL SOURCES FAILED"
exit 1
