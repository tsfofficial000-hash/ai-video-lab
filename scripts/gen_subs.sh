#!/usr/bin/env bash
# =============================================================================
# Shared: generates work/subs.srt from work/refmix.m4a via faster-whisper.
# Idempotent — skips if subs.srt already exists. Used by tests A, B, C.
# =============================================================================
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT/work" || exit 1

if [ -s subs.srt ]; then echo "[SUBS] subs.srt already present"; exit 0; fi
[ -s refmix.m4a ] || { echo "[FAIL-SUBS] refmix.m4a missing - run build_master.sh first"; exit 1; }

[ -d .venv ] || python3 -m venv .venv || exit 1
./.venv/bin/pip install -q --upgrade pip
# av pinned to 14.2.0: PyAV >= 16 removed the `metadata_errors` kwarg that
# faster-whisper 1.x passes to av.open() (14.2.0 has broad manylinux wheels)
./.venv/bin/pip install -q faster-whisper "av==14.2.0" || exit 1
./.venv/bin/python "$ROOT/scripts/make_srt.py" refmix.m4a subs.srt || exit 1
echo "[SUBS-READY]"
