#!/usr/bin/env python3
"""E3: mood music always synthetic.

Audit: all FreePD candidates HTTP 404 (site restructured) - the synth pad is
the only path that ever fires, silently.

Fix contract:
  - >= 2 new rights-clean sources behind the existing verify+manifest mechanics:
    (a) Internet Archive CC items (advancedsearch licenseurl:*creativecommons*,
        direct /download/ MP3s), (b) incompetech CC-BY direct MP3s with
        attribution rendered in report AND on-screen outro credit
  - synth kept as last resort, ONLY with a logged egress-failure reason
  - manifest entry carries via/attribution/credit; gate clause: music_via != synth
    whenever egress works

Probe is offline + fast: verifies the source ladder exists (3 kinds), builds
valid archive/incompetech candidate URLs, and checks the synth-fallback writer
records via + egress failures. On HEAD the new contracts are absent -> FAILS.
"""
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import ok, fail, load_module


def main():
    try:
        fm = load_module("fetch_music_under_test", "scripts/cineforge/fetch_music.py")
    except Exception as e:
        fail(f"fetch_music.py unimportable: {e}")

    # 1) a declared source ladder with >= 3 kinds (freepd + 2 new)
    if not hasattr(fm, "SOURCE_LADDER"):
        fail("E3 contract missing: fetch_music.SOURCE_LADDER not declared - "
             "there is no source ladder beyond FreePD+synth")
    ladder = fm.SOURCE_LADDER
    kinds = {s.get("kind") for s in ladder}
    if "freepd" not in kinds:
        fail(f"ladder lost the freepd source: {kinds}")
    for needed in ("archive_cc", "incompetech_ccb"):
        if needed not in kinds:
            fail(f"E3 contract missing: source kind '{needed}' not in ladder {sorted(kinds)}")
    ok(f"source ladder declares {sorted(kinds)}")

    # 2) incompetech candidates: direct MP3 URLs, CC-BY metadata attached
    inc = [s for s in ladder if s.get("kind") == "incompetech_ccb"]
    if len(inc) < 2:
        fail(f"need >= 2 incompetech CC-BY candidates, got {len(inc)}")
    for s in inc:
        u = s.get("url", "")
        if not u.startswith("https://incompetech.com/") or not u.endswith(".mp3"):
            fail(f"incompetech candidate is not a direct incompetech .mp3 URL: {u}")
        if "CC BY" not in (s.get("license") or ""):
            fail(f"incompetech candidate missing CC BY license: {s}")
    ok(f"{len(inc)} incompetech CC-BY candidates with direct MP3 URLs")

    # 3) archive.org source: query builder + download URL construction
    arch = [s for s in ladder if s.get("kind") == "archive_cc"]
    if not arch:
        fail("ladder has no archive_cc source")
    a0 = arch[0]
    if not hasattr(fm, "archive_search"):
        fail("E3 contract missing: fetch_music.archive_search (advancedsearch "
             "licenseurl:*creativecommons*) not implemented")
    try:
        q = fm.archive_search("cinematic")
    except Exception as e:
        fail(f"archive_search('cinematic') crashed: {type(e).__name__}: {e}")
    if not isinstance(q, str) or "creativecommons" not in q:
        fail(f"archive_search must filter licenseurl:*creativecommons* - got {q!r}")
    if not hasattr(fm, "archive_download_url"):
        fail("E3 contract missing: archive_download_url(identifier, filename)")
    du = fm.archive_download_url("some_cc_item", "track%20one.mp3")
    if "archive.org/download/some_cc_item/" not in du:
        fail(f"archive_download_url malformed: {du!r}")
    ok("archive.org CC search + direct download URL mechanics present")

    # 4) synth last-resort MUST log via + egress failures (offline test)
    with tempfile.TemporaryDirectory() as td:
        dest = os.path.join(td, "synth.mp3")
        manifest = os.path.join(td, "media_manifest.json")
        try:
            entry = fm.write_synth_entry(dest, manifest, seconds=6,
                                         failures=["freepd: HTTP 404 on all candidates",
                                                   "archive_cc: search unreachable",
                                                   "incompetech_ccb: HTTP 404"],
                                         egress_ok=True)
        except TypeError:
            fail("write_synth_entry signature missing/changed - synth fallback does not "
                 "carry egress-failure logging (E3 contract)")
        except Exception as e:
            fail(f"write_synth_entry crashed: {type(e).__name__}: {e}")
        if not os.path.isfile(dest) or os.path.getsize(dest) < 1000:
            fail("synth pad did not produce audio")
        got = json.load(open(manifest)).get("music") or {}
        if got.get("via") != "synth_fallback":
            fail(f"synth entry must declare via='synth_fallback', got {got.get('via')!r}")
        if not got.get("egress_failures") or len(got["egress_failures"]) < 3:
            fail("synth entry must log the per-source egress failures")
        if "egress_ok" not in got:
            fail("synth entry must record whether network egress worked")
        ok("synth fallback logs via + egress_failures + egress_ok (gate clause ready)")

    # 5) real-music entries must carry attribution fields (offline shape check)
    if not hasattr(fm, "entry_for_download"):
        fail("E3 contract missing: entry_for_download() must stamp via/license/credit")
    e = fm.entry_for_download("incompetech_ccb", "Cipher.mp3",
                              "https://incompetech.com/music/royalty-free/mp3-royaltyfree/Cipher.mp3")
    if not e.get("attribution_required") or "CC BY" not in (e.get("license") or ""):
        fail(f"incompetech entry must be attribution-required CC BY: {e}")
    if "Kevin MacLeod" not in (e.get("credit") or ""):
        fail(f"CC-BY entry must carry a rendered credit line: {e.get('credit')!r}")
    ok("CC-BY entries carry attribution_required + on-screen credit line")

    print("E3 PROBE: PASS (defect fixed)")


if __name__ == "__main__":
    main()
