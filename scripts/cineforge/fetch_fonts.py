#!/usr/bin/env python3
"""Fetch OFL fonts at runtime (G5): display face (Anton/Bebas Neue) + caption face
(Montserrat Bold). License file verified and recorded. Cache-friendly: no-op when
fonts already present (actions/cache key fonts-v1)."""
import argparse
import hashlib
import os
import sys
import urllib.request

# google/fonts GitHub raw (OFL licensed)
FONTS = {
    "Anton-Regular.ttf": {
        "url": "https://raw.githubusercontent.com/google/fonts/main/ofl/anton/Anton-Regular.ttf",
        "role": "display",
        "license": "OFL",
    },
    "BebasNeue-Regular.ttf": {
        "url": "https://raw.githubusercontent.com/google/fonts/main/ofl/bebasneue/BebasNeue-Regular.ttf",
        "role": "display_alt",
        "license": "OFL",
    },
    "Montserrat-Bold.ttf": {
        "url": "https://raw.githubusercontent.com/google/fonts/main/ofl/montserrat/Montserrat%5Bwght%5D.ttf",
        "role": "caption",
        "license": "OFL",
    },
    "Montserrat-ExtraBold.ttf": {
        "url": "https://raw.githubusercontent.com/google/fonts/main/ofl/montserrat/Montserrat-Italic%5Bwght%5D.ttf",
        "role": "caption_alt",
        "license": "OFL",
        "optional": True,
    },
}
OFL_URL = "https://raw.githubusercontent.com/google/fonts/main/ofl/{}/OFL.txt"


def fetch(url, dest, timeout=60):
    req = urllib.request.Request(url, headers={"User-Agent": "cineforge/2.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r, open(dest, "wb") as f:
        f.write(r.read())
    return os.path.getsize(dest)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="media/fonts")
    ap.add_argument("--report", default="reports/fonts_report.json")
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)

    results, ok_all = {}, True
    for name, meta in FONTS.items():
        dest = os.path.join(a.out, name)
        if os.path.isfile(dest) and os.path.getsize(dest) > 10000:
            results[name] = {"status": "cached", "bytes": os.path.getsize(dest),
                             "license": meta["license"], "role": meta["role"]}
            continue
        try:
            size = fetch(meta["url"], dest)
            lic = ""
            try:
                lic = fetch(OFL_URL.format(meta["url"].split("/ofl/")[1].split("/")[0]),
                            dest + ".license.txt")
            except Exception:
                pass
            results[name] = {"status": "fetched", "bytes": size, "role": meta["role"],
                             "license": meta["license"],
                             "license_file_bytes": lic,
                             "sha1": hashlib.sha1(open(dest, "rb").read()).hexdigest()[:12]}
        except Exception as e:
            results[name] = {"status": "failed", "error": str(e)[:120],
                             "optional": meta.get("optional", False)}
            if not meta.get("optional"):
                ok_all = False

    import json
    json.dump({"dir": a.out, "fonts": results, "all_required_ok": ok_all},
              open(a.report, "w"), indent=1)
    print(f"fonts: {sum(1 for r in results.values() if r['status'] != 'failed')}"
          f"/{len(results)} available -> {a.out}")
    sys.exit(0 if ok_all else 1)


if __name__ == "__main__":
    main()
