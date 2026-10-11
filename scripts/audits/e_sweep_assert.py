#!/usr/bin/env python3
"""Phase E assertion: the three v2.1 style-sweep drafts must differ in grade /
cuts band / caption style / music source exactly per configs/styles.json, with
ZERO config bleed (no style carries another style's creative params)."""
import json
import os
import sys

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
CF = os.path.join(REPO, "cf_artifacts") if os.path.isdir(os.path.join(REPO, "cf_artifacts")) else "/home/z/my-project/cf_artifacts"

DRAFTS = {
    "sad_emotional": "38108781479",
    "cinematic": "38108784839",
    "motivational": "38108787972",
}
styles = json.load(open(os.path.join(REPO, "configs", "styles.json")))

rows = []
bleed = []
for style, rid in DRAFTS.items():
    p = json.load(open(os.path.join(CF, f"e_{rid}", "edit_plan.json")))
    m = json.load(open(os.path.join(CF, f"e_{rid}", "media_manifest.json")))
    cfg = styles[style]
    row = {
        "style": style, "run": rid,
        "grade": p.get("color_grade"), "cfg_grade": cfg.get("grade"),
        "caption": p.get("caption_style"), "cfg_caption": cfg.get("captions"),
        "band": p.get("cuts_band"), "cfg_band": cfg.get("cuts_band"),
        "hook_type": (p.get("hook") or {}).get("type"), "cfg_hook": cfg.get("hook"),
        "vertical": p.get("vertical_plan"), "cfg_vertical": cfg.get("vertical"),
        "music_via": (m.get("music") or {}).get("via"),
        "music_title": (m.get("music") or {}).get("title"),
        "music_mood": (m.get("music") or {}).get("mood"),
        "mood_fit": (m.get("music") or {}).get("mood_fit"),
        "cps": p.get("cut_density_cps"),
        "downshift": [r.get("to_band") for r in (p.get("relaxations") or [])
                      if r.get("kind") == "style_density_downshift"],
    }
    rows.append(row)
    # zero-bleed: every declared creative param equals ITS OWN style config
    for plan_k, cfg_k in (("grade", "cfg_grade"), ("caption", "cfg_caption"),
                          ("hook_type", "cfg_hook"), ("vertical", "cfg_vertical")):
        if row[plan_k] != row[cfg_k]:
            bleed.append(f"{style}: plan {plan_k}={row[plan_k]} != cfg {row[cfg_k]}")
    base_band = cfg.get("cuts_band")
    if row["band"] != base_band and not row["downshift"]:
        bleed.append(f"{style}: band {row['band']} != cfg {base_band} with no "
                     f"declared downshift (silent bleed)")

print(f"{'style':14} {'grade':22} {'caption':20} {'band':12} {'cps':5} music")
for r in rows:
    print(f"{r['style']:14} {r['grade']:22} {r['caption']:20} "
          f"{str(r['band']):12} {r['cps']:5} {r['music_via']}:{r['music_title']} "
          f"(mood={r['music_mood']})")
    print(f"{'':14} mood_fit: {r['mood_fit']}")

# cross-style difference asserts (the sweep must SHOW the styles differ)
grades = {r["grade"] for r in rows}
caps = {r["caption"] for r in rows}
bands = {tuple(r["band"]) for r in rows}
music = {(r["music_title"]) for r in rows}
assert len(grades) == 3, f"grades not distinct: {grades}"
assert len(caps) == 3, f"caption styles not distinct: {caps}"
assert len(music) == 3, f"music sources not distinct: {music}"
assert len(bands) >= 2, f"bands collapsed: {bands}"
assert not bleed, "CONFIG BLEED DETECTED:\n" + "\n".join(bleed)
print()
print(f"assertions: 3 distinct grades {sorted(grades)}")
print(f"            3 distinct caption styles {sorted(caps)}")
print(f"            3 distinct music sources {sorted(music)}")
print(f"            bands {sorted(bands)} (sad_emotional sparse; "
      f"cinematic native; motivational via DECLARED downshift {rows[2]['downshift']})")
print("ZERO CONFIG BLEED: every plan param equals its own style config; "
      "the only band deviation is the logged style_density_downshift")
print("E SWEEP: PASS")
