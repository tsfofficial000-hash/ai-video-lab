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


def probe(base, vid, min_height=720):
    try:
        d = json.loads(get(f"{base}/api/v1/videos/{vid}?local=true", 14))
        if "error" in d:
            return (base, None, f"api:{str(d['error'])[:60]}")
        adaptive = d.get("adaptiveFormats") or []
        muxed = d.get("formatStreams") or []

        def h(f):
            r = f.get("resolution") or ""
            m = re.match(r"(\d+)x", r)          # "1920x1080"
            if m:
                return int(m.group(1))
            m = re.match(r"(\d+)p", r)           # "1080p"
            if m:
                return int(m.group(1))
            m = re.match(r"(\d+)", r)            # bare "1080"
            return int(m.group(1)) if m else 0

        def key(f):
            return (1 if (f.get("type") or "").startswith("video/mp4") else 0, h(f))

        v = sorted([f for f in adaptive if (f.get("type", "").startswith("video/") and
                    h(f) >= min_height)], key=key, reverse=True)
        a_fmt = sorted([f for f in adaptive if f.get("type", "").startswith("audio/")],
                       key=lambda f: int(f.get("bitrate") or 0), reverse=True)
        mlist = sorted([f for f in muxed if h(f) >= min(min_height, 720)], key=h, reverse=True)
        if v and a_fmt:
            return (base, {"title": d.get("title"), "dur": d.get("lengthSeconds"),
                           "v_url": v[0]["url"], "v_h": h(v[0]),
                           "v_type": v[0].get("type", ""),
                           "a_url": a_fmt[0]["url"],
                           "a_type": a_fmt[0].get("type", ""),
                           "muxed_url": mlist[0]["url"] if mlist else None}, None)
        if mlist:
            return (base, {"title": d.get("title"), "dur": d.get("lengthSeconds"),
                           "v_url": None, "v_h": h(mlist[0]), "v_type": mlist[0].get("type", ""),
                           "a_url": None, "a_type": "",
                           "muxed_url": mlist[0]["url"]}, None)
        return (base, None, f"no-pairs (adaptive={len(adaptive)} muxed={len(muxed)} "
                            f"hs={[h(f) for f in adaptive[:6]]})")
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


def proxify(base, url):
    """Route raw googlevideo URLs through the instance proxy (add /videoplayback + local=true)."""
    if not url:
        return url
    if "googlevideo.com" in url and "videoplayback" in url:
        sep = "&" if "?" in url else "?"
        return f"{base}/videoplayback?{url.split('?', 1)[1]}{sep}local=true"
    if "local=true" not in url and base not in url and "videoplayback" in url:
        sep = "&" if "?" in url else "?"
        return f"{url}{sep}local=true"
    return url


def sh_download(url, dest, tries=3):
    """curl-based download with retries; returns size; raises on zero-byte."""
    for k in range(tries):
        r = subprocess.run(["curl", "-sL", "--max-time", "280", "--retry", "2",
                            "-H", f"User-Agent: {UA['User-Agent']}", "-o", dest, url],
                           capture_output=True)
        size = os.path.getsize(dest) if os.path.isfile(dest) else 0
        if r.returncode == 0 and size > 65536:
            return size
        print(f"  dl attempt {k+1} rc={r.returncode} size={size}", flush=True)
        time.sleep(2)
    return size


def probe_file(path):
    try:
        out = subprocess.check_output(["ffprobe", "-v", "error", "-print_format", "json",
                                       "-show_streams", path]).decode()
        d = json.loads(out)
        return any(s["codec_type"] == "video" for s in d["streams"])
    except Exception:
        return False


def try_instance(base, res, dest):
    """Download + mux for one instance; returns (ok, detail)."""
    tmp_v, tmp_a = "/tmp/_v.f", "/tmp/_a.f"
    ext = lambda t: (".mp4" if "mp4" in (t or "") else ".webm" if "webm" in (t or "") else ".m4a")
    for p in (tmp_v + ".mp4", tmp_v + ".webm", tmp_a + ".m4a", tmp_a + ".webm"):
        if os.path.isfile(p):
            os.remove(p)
    if res.get("muxed_url") and not res.get("v_url"):
        u = proxify(base, res["muxed_url"])
        sz = sh_download(u, tmp_v + ext(res["v_type"]))
        if probe_file(tmp_v + ext(res["v_type"])):
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", tmp_v + ext(res["v_type"]),
                            "-c", "copy", dest], check=True)
            return True, f"muxed-only {sz/1e6:.1f}MB"
        return False, f"muxed download invalid ({sz}B)"
    v_url = proxify(base, res["v_url"])
    a_url = proxify(base, res["a_url"])
    szv = sh_download(v_url, tmp_v + ext(res["v_type"]))
    sza = sh_download(a_url, tmp_a + ext(res["a_type"]))
    vf = tmp_v + ext(res["v_type"])
    af = tmp_a + ext(res["a_type"])
    if not probe_file(vf):
        # try the muxed fallback before giving up on this instance
        if res.get("muxed_url"):
            mu = proxify(base, res["muxed_url"])
            szm = sh_download(mu, tmp_v + ".mp4")
            if probe_file(tmp_v + ".mp4"):
                subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", tmp_v + ".mp4",
                                "-c", "copy", dest], check=True)
                return True, f"fallback-muxed {szm/1e6:.1f}MB (adaptive v invalid)"
        return False, f"v download invalid ({szv}B), a={sza}B"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", vf, "-i", af,
                    "-c", "copy", dest], check=True)
    return True, f"adaptive v={szv/1e6:.1f}MB a={sza/1e6:.1f}MB"


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
        futs = {ex.submit(probe, b, a.video_id, a.min_height): b for b in bases}
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

    # download loop: hit first, then re-probe remaining instances in diag order
    candidates = [d["base"] for d in diag]
    candidates = [hit[0]] + [b for b in candidates if b != hit[0]]
    for base in candidates:
        res = hit[1] if base == hit[0] else None
        if res is None:
            # re-probe this instance to get fresh signed URLs
            _, res, err = probe(base, a.video_id, a.min_height)
            if not res:
                print(f"skip {base} (re-probe failed: {err})", flush=True)
                continue
        print(f"downloading v({res['v_h']}p) via {base}", flush=True)
        try:
            ok, detail = try_instance(base, res, a.dest)
        except subprocess.CalledProcessError as e:
            ok, detail = False, f"mux failed: {e}"
        print(("OK " if ok else "fail ") + detail, flush=True)
        if ok and os.path.isfile(a.dest):
            dur = subprocess.check_output(["ffprobe", "-v", "error", "-show_entries",
                                           "format=duration", "-of", "csv=p=0", a.dest]).decode().strip()
            json.dump({"instances_tried": len(diag), "winner": base, "detail": detail},
                      open("reports/acquisition_report.json", "w"), indent=1)
            print(f"OK dur={dur}s via={base}", flush=True)
            sys.exit(0)
    json.dump({"instances_tried": len(diag), "winner": None,
               "diagnostics": diag}, open("reports/acquisition_report.json", "w"), indent=1)
    print("ALL DOWNLOADS FAILED", flush=True)
    sys.exit(1)


if __name__ == "__main__":
    main()
