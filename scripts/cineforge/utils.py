#!/usr/bin/env python3
"""Shared helpers: latency-tagged execution, ffprobe, JSON IO, manifest logging."""
import json
import os
import subprocess
import time
from datetime import datetime, timezone


def now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def ffprobe_json(path):
    out = subprocess.check_output(
        ["ffprobe", "-v", "error", "-print_format", "json", "-show_format", "-show_streams", path])
    return json.loads(out.decode())


def n_cores():
    try:
        return os.cpu_count() or 2
    except Exception:
        return 2


def mem_gb():
    try:
        with open("/proc/meminfo") as f:
            for line in f:
                if line.startswith("MemTotal"):
                    return round(int(line.split()[1]) / 1e6, 1)
    except Exception:
        pass
    return -1


def disk_free_gb(path="."):
    st = os.statvfs(path)
    return round(st.f_bavail * st.f_frsize / 1e9, 1)


def record_stage(reports_dir, stage_name, status, extra=None, t0=None, retries=0,
                 bottleneck="", optimization_applied="", optimization_result=""):
    """Append/update reports/latency.json with one stage record."""
    path = os.path.join(reports_dir, "latency.json")
    data = {"stages": []}
    if os.path.isfile(path):
        try:
            data = json.load(open(path))
        except Exception:
            pass
    rec = {
        "stage_name": stage_name,
        "start_time": getattr(record_stage, "_t0_iso", None) or now_iso(),
        "end_time": now_iso(),
        "duration_seconds": round(time.time() - t0, 1) if t0 else None,
        "status": status,
        "runner_os": os.environ.get("RUNNER_OS", "local"),
        "cpu_cores_detected": n_cores(),
        "memory_peak_estimate_gb": mem_gb(),
        "disk_usage_estimate_gb": disk_free_gb(),
        "artifact_size_mb": None,
        "retries": retries,
        "bottleneck_detected": bottleneck,
        "optimization_applied": optimization,
        "optimization_result": optimization_result,
    }
    if extra:
        rec.update(extra)
    stages = [s for s in data.get("stages", []) if s["stage_name"] != stage_name]
    stages.append(rec)
    data["stages"] = stages
    data["updated_at"] = now_iso()
    os.makedirs(reports_dir, exist_ok=True)
    json.dump(data, open(path, "w"), indent=1)
    return rec


def jdump(obj, path):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    json.dump(obj, open(path, "w"), indent=1)


def jload(path, default=None):
    try:
        return json.load(open(path))
    except Exception:
        return default
