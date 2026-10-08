#!/usr/bin/env python3
"""Fetch video title via YouTube oEmbed (no API key, works from datacenter IPs).
Falls back to 'MONTAGE' on any failure."""
import json
import sys
import urllib.parse
import urllib.request

url = sys.argv[1] if len(sys.argv) > 1 else "https://youtu.be/YAFUyPp_238"
try:
    ep = ("https://www.youtube.com/oembed?url=" +
          urllib.parse.quote(url, safe="") + "&format=json")
    req = urllib.request.Request(ep, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=12) as r:
        print(json.loads(r.read().decode()).get("title", "MONTAGE"))
except Exception:
    print("MONTAGE")
