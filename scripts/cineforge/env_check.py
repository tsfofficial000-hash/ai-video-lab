#!/usr/bin/env python3
"""Stage 0: environment check -> reports/environment.json (+ artifact upload ability probe)."""
import json
import os
import shutil
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from utils import jdump, n_cores, mem_gb, disk_free_gb


def ver(cmd):
    try:
        return subprocess.check_output(cmd, stderr=subprocess.STDOUT).decode().strip().split("\n")[0]
    except Exception:
        return None


def main():
    env = {
        "runner_os": os.environ.get("RUNNER_OS", "local"),
        "cpu_cores": n_cores(),
        "ram_gb": mem_gb(),
        "disk_free_gb": disk_free_gb(),
        "python": sys.version.split()[0],
        "node": ver(["node", "--version"]),
        "ffmpeg": ver(["ffmpeg", "-version"]),
        "ffprobe": ver(["ffprobe", "-version"]),
        "curl": ver(["curl", "--version"]),
        "git": ver(["git", "--version"]),
    }
    # yt-dlp installability
    if not shutil.which("yt-dlp"):
        subprocess.run([sys.executable, "-m", "pip", "install", "-q", "yt-dlp"], check=False)
    env["yt_dlp"] = ver(["yt-dlp", "--version"])
    # token + permissions
    tok = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    env["github_token_present"] = bool(tok)
    if tok and os.environ.get("GITHUB_REPOSITORY"):
        import urllib.request
        req = urllib.request.Request(
            f"https://api.github.com/repos/{os.environ['GITHUB_REPOSITORY']}",
            headers={"Authorization": f"Bearer {tok}", "Accept": "application/json"})
        try:
            r = json.loads(urllib.request.urlopen(req, timeout=10).read().decode())
            env["repo_permissions"] = r.get("permissions", {})
        except Exception as e:
            env["repo_permissions"] = {"error": str(e)[:80]}
    # artifact upload ability is exercised by the workflow itself; record intent
    env["artifact_upload"] = "exercised-by-workflow-step"
    jdump(env, "reports/environment.json")
    print(json.dumps(env, indent=1))
    missing = [k for k in ("ffmpeg", "ffprobe", "python") if not env.get(k)]
    sys.exit(1 if missing else 0)


if __name__ == "__main__":
    main()
