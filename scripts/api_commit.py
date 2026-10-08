#!/usr/bin/env python3
"""Commit & push files to main via the GitHub git-data API (no git push).

Robust against shallow clones, detached heads, and concurrent runs
(retries on ref conflict). Runs on the runner with the job's GITHUB_TOKEN.

Usage: api_commit.py -m "message" <file1> [<file2> ...]
       (paths are repo-relative; missing files are skipped silently)
Env:   GITHUB_TOKEN (required), GITHUB_REPOSITORY (required)
"""
import base64
import json
import os
import sys
import time
import urllib.error
import urllib.request

REPO = os.environ["GITHUB_REPOSITORY"]
TOKEN = os.environ["GITHUB_TOKEN"]
API = f"https://api.github.com/repos/{REPO}"


def api(url, method="GET", body=None):
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(url, data=data, method=method)
    r.add_header("Authorization", f"Bearer {TOKEN}")
    r.add_header("Accept", "application/vnd.github+json")
    with urllib.request.urlopen(r) as resp:
        return json.loads(resp.read() or b"{}")


def main() -> int:
    args = sys.argv[1:]
    if "-m" not in args:
        print("[API-COMMIT] missing -m message")
        return 2
    msg = args[args.index("-m") + 1]
    files = [a for i, a in enumerate(args) if a != "-m" and args[i - 1] != "-m"]
    files = [f for f in files if os.path.isfile(f)]
    if not files:
        print("[API-COMMIT] no files to commit")
        return 0

    for attempt in range(1, 6):
        try:
            base = api(f"{API}/git/ref/heads/main")["object"]["sha"]
            base_tree = api(f"{API}/git/commits/{base}")["tree"]["sha"]
            tree_items = []
            for f in files:
                content = open(f, "rb").read()
                blob = api(f"{API}/git/blobs", "POST", {
                    "content": base64.b64encode(content).decode(),
                    "encoding": "base64"})["sha"]
                tree_items.append({"path": f, "mode": "100644",
                                   "type": "blob", "sha": blob})
            tree = api(f"{API}/git/trees", "POST", {
                "base_tree": base_tree, "tree": tree_items})["sha"]
            commit = api(f"{API}/git/commits", "POST", {
                "message": msg, "tree": tree, "parents": [base]})["sha"]
            api(f"{API}/git/refs/heads/main", "PATCH",
                {"sha": commit, "force": False})
            print(f"[API-COMMIT] {commit[:8]} pushed ({len(files)} files: "
                  + ", ".join(files) + ")")
            return 0
        except urllib.error.HTTPError as e:
            detail = e.read().decode(errors="replace")[:200]
            print(f"[API-COMMIT] attempt {attempt}: HTTP {e.code} {detail}")
            time.sleep(8)
    return 1


if __name__ == "__main__":
    sys.exit(main())
