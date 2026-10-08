#!/usr/bin/env python3
"""Invidious instance hunt + download. Runs ON the runner (clean DNS/IP vs sandbox).
Queries live registry + fallback list, parallel-probes /api/v1/videos/{id}?local=true,
downloads first usable hit (proxied via instance), muxes to mp4.
Usage: instance_hunt.py <video_id> <dest.mp4> [--timeout 240]
Writes reports/acquisition_report.json"""
import argparse
import json
import os
import re
import subprocess
import sys
import time
import concurrent.futures as cf
import urllib.request

UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) Gecko/20100101 Firefox/132.0",
      "Accept": "application/json"}
REGISTRY = "https://api.invidious.io/instances.json?sort_by=health"
FALLBACK = [
    "https://iv.ggtyler.dev", "https://invidious.materialio.us", "https://inv.nadeko.net",
    "https://yewtu.be", "https://invidious.nerdvpn.de", "https://invidious.f5.si",
    "https://iv.melmac.space", "https://invidious.privacyredirect.com",
    "https://invidious.jing.rocks", "https://inv.tux.pizza", "https://yt.artemislena.eu",
    "https://invidious.reallyaweso.me", "https://invidious.dhusch.de", "https://inv.zzls.xyz",
    "https://invidious.lunivers.trade", "https://invidious.polaris.direct",
]


def get(url, timeout=12):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "replace")


def instances():
    bases = []
    try:
        rows = json.loads(get(REGISTRY, 12))
        for _, meta in rows:
            if meta.get("type") == "https":
                bases.append(meta.get("uri"))
    except Exception as e:
        print(f"registry unavailable: {e}", flush=True)
    seen, out = set(), []
    for b in bases + FALLBACK:
        if b and b not in seen:
            seen.add(b)
            out.append(b)
    return out


def probe(base, vid):
    try:
        d = json.loads(get(f"{base}/api/v1/videos/{vid}?local=true", 14))
        if "error" in d:
            return (base, None, f"api:{str(d['error'])[:60]}")
        adaptive = d.get("adaptiveFormats") or []
        def h(f):
            m = re.match(r"(\d+)x", f.get("resolution") or "")
            return int(m.group(1)) if m else 0
        v = sorted([f for f in adaptive if f.get("type", "").startswith("video/mp4") and h(f) >= 720],
                   key=h, reverse=True)
        a = [f for f in adaptive if f.get("type", "").startswith("audio/mp4")]
        if v and a:
            return (base, {"title": d.get("title"), "dur": d.get("lengthSeconds"),
                           "v_url": v[0]["url"], "v_h": h(v[0]), "a_url": a[0]["url"]}, None)
        return (base, None, f"no-mp4-pairs (n={len(adaptive)})")
    except Exception as e:
        return (base, None, f"{type(e).__name__}: {str(e)[:60]}")


def download(url, dest, timeout=300):
    req = urllib.request.Request(url, headers={"User-Agent": UA["User-Agent"]})
    with urllib.request.urlopen(req, timeout=timeout) as r, open(dest, "wb") as f:
        while True:
            chunk = r.read(1 << 18)
            if not chunk:
                break
            f.write(chunk)
    return os.path.getsize(dest)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("video_id")
    ap.add_argument("dest")
    ap.add_argument("--timeout", type=int, default=240)
    ap.add_argument("--min-height", type=int, default=720)
    a = ap.parse_args()

    t0 = time.time()
    bases = instances()
    print(f"hunting {len(bases)} instances for {a.video_id}", flush=True)
    hit = None
    diag = []
    with cf.ThreadPoolExecutor(max_workers=10) as ex:
        futs = {ex.submit(probe, b, a.video_id): b for b in bases}
        for f in cf.as_completed(futs, timeout=a.timeout):
            base, res, err = f.result()
            diag.append({"base": base, "ok": bool(res), "err": err})
            if res:
                print(f"HIT {base} h={res['v_h']} title={str(res['title'])[:40]!r}", flush=True)
                hit = (base, res)
                break
            else:
                print(f"miss {base}: {err}", flush=True)

    os.makedirs("reports", exist_ok=True)
    json.dump({"instances_tried": len(diag), "hits": [hit[0]] if hit else [],
               "diagnostics": diag, "elapsed_s": round(time.time() - t0, 1)},
              open("reports/acquisition_report.json", "w"), indent=1)

    if not hit:
        print("NO INSTANCE HIT", flush=True)
        sys.exit(1)

    base, res = hit
    tmp_v, tmp_a = "/tmp/_v.mp4", "/tmp/_a.m4a"
    print(f"downloading v({res['v_h']}p)+a via {base}", flush=True)
    download(res["v_url"], tmp_v)
    download(res["a_url"], tmp_a)
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", tmp_v, "-i", tmp_a,
                    "-c", "copy", "-movflags", "+faststart", a.dest], check=True)
    dur = subprocess.check_output(["ffprobe", "-v", "error", "-show_entries",
                                   "format=duration", "-of", "csv=p=0", a.dest]).decode().strip()
    print(f"OK dur={dur}s via={base}", flush=True)


if __name__ == "__main__":
    main()
