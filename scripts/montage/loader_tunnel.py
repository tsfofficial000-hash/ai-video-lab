#!/usr/bin/env python3
"""loader.to -> oceansaver tunnel YouTube fetch (used locally AND on runner).

Usage: loader_tunnel.py <youtube_url> [quality]   # quality: 1080|1440|4k
Prints a direct download URL on success; exits 1 on failure.
"""
import json
import sys
import time
import urllib.parse
import urllib.request

UA = "Mozilla/5.0 (X11; Linux x86_64; rv:132.0) Gecko/20100101 Firefox/132.0"


def http(url, timeout=20, headers=None, data=None, method="GET"):
    h = {"User-Agent": UA, "Accept": "*/*"}
    if headers:
        h.update(headers)
    req = urllib.request.Request(url, data=data, headers=h, method=method)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def main():
    url, quality = sys.argv[1], (sys.argv[2] if len(sys.argv) > 2 else "1080")
    ep = f"https://loader.to/ajax/download.php?format={quality}&url={urllib.parse.quote(url, safe='')}"
    j = json.loads(http(ep).decode())
    if not j.get("success") or not j.get("id"):
        print(f"start failed: {str(j)[:200]}", file=sys.stderr)
        sys.exit(1)
    jid = j["id"]
    print(f"job={jid}", file=sys.stderr)
    for i in range(210):
        time.sleep(4)
        try:
            p = json.loads(http(f"https://p.oceansaver.in/ajax/progress.php?id={jid}").decode())
        except Exception:
            continue
        if p.get("download_url"):
            print(p["download_url"])
            sys.exit(0)
        if i % 5 == 0:
            print(f"progress={p.get('progress', 0)}", file=sys.stderr)
    print("timeout", file=sys.stderr)
    sys.exit(1)


if __name__ == "__main__":
    main()
