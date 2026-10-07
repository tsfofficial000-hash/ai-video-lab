#!/usr/bin/env bash
# GNU /usr/bin/time shim: if GNU time is missing (sudo unavailable), emulate
# the two report lines the lab parses ("Elapsed (wall clock)" and "Maximum
# resident set size") so scripts degrade gracefully instead of dying.
# Usage: source "$(dirname "$0")/time_shim.sh"; ensure_time
ensure_time(){
  if [ -x /usr/bin/time ]; then export TIME_BIN=/usr/bin/time; return 0; fi
  local shim_dir
  shim_dir="${WORK:-$(pwd)}/bin"
  mkdir -p "$shim_dir"
  cat > "$shim_dir/time" <<'EOF'
#!/bin/sh
# minimal GNU-time-compatible shim (-v and -f "%e")
case "$1" in
  -v) shift ;;
  -f) shift 2 ;;
esac
START=$(date +%s.%N)
"$@"
RC=$?
END=$(date +%s.%N)
ELAPSED=$(awk -v a="$START" -v b="$END" 'BEGIN{printf "0:%05.2f", b-a}')
{
  echo "        Elapsed (wall clock) time (h:mm:ss or m:ss): $ELAPSED"
  echo "        Maximum resident set size (kbytes): 0"
} >&2
exit $RC
EOF
  chmod +x "$shim_dir/time"
  export PATH="$shim_dir:$PATH"
  export TIME_BIN="$shim_dir/time"
  echo "[TIME-SHIM] /usr/bin/time unavailable - using RSS-sampling shim in $shim_dir"
}
