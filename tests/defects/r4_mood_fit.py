#!/usr/bin/env python3
"""R4: mood-blind music selection.

Audit: via=archive_cc returned a CC0 geometry-dash track for mood=cinematic -
license-safe but mood-blind (the advancedsearch OR matched on 'soundtrack').

Fix contract:
  - archive candidates are screened by a mood-keyword heuristic (veto
    genre-contradicting items outright, rank positive keyword hits first);
  - a 1-line mood-fit rationale is logged into media_manifest.json;
  - synth stays a fallback for egress failure only (unchanged E3 contract).

Probe is offline + fast: exercises mood_fit() and apply_mood_fit() on the
audit's actual failure case plus ranking/manifest plumbing.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import ok, fail, load_module

fm = load_module("fetch_music_under_test_r4", "scripts/cineforge/fetch_music.py")


def main():
    # 1) the audit's exact failure: geometry-dash item for cinematic
    fits, score, why = fm.mood_fit("Geometry Dash Soundtrack (CC0)", "unknown",
                                   ["geometry dash", "electronic"], "cinematic")
    if fits:
        fail(f"R4 present: geometry-dash item passes the cinematic mood screen "
             f"(score={score}, why={why!r})")
    if "veto" not in why:
        fail(f"veto rationale must say 'vetoed' (got {why!r})")
    ok(f"audit case vetoed: {why}")

    # 2) a true cinematic match ranks positive
    fits, score, why = fm.mood_fit("Cinematic Orchestral Score", "A. Composer",
                                   ["cinematic", "orchestral", "film"], "cinematic")
    if not fits or score <= 0 or "keyword" not in why:
        fail(f"true mood match must pass with a keyword rationale "
             f"(fits={fits}, score={score}, why={why!r})")
    ok(f"true match ranked: score={score}, {why}")

    # 3) neutral metadata survives (recall) but ranks below hits
    fits_n, score_n, why_n = fm.mood_fit("Sunset Waltz", "B. Author", [],
                                         "cinematic")
    if not fits_n or score_n != 0:
        fail(f"neutral item must pass with score 0 (got {fits_n}, {score_n})")
    ok(f"neutral survives for recall: {why_n}")

    # 4) the pipeline function: vetoed dropped, hits first, rationale attached
    cands = [
        {"identifier": "neutral-item", "title": "Sunset Waltz", "creator": "x",
         "subject": []},
        {"identifier": "geo-item", "title": "Geometry Dash OST", "creator": "y",
         "subject": ["game"]},
        {"identifier": "score-item", "title": "Epic Orchestral Trailer Score",
         "creator": "z", "subject": ["cinematic"]},
    ]
    ranked = fm.apply_mood_fit(cands, "cinematic")
    ids = [c["identifier"] for c in ranked]
    if "geo-item" in ids:
        fail(f"apply_mood_fit kept the vetoed geometry item: {ids}")
    if not ids or ids[0] != "score-item":
        fail(f"keyword hit must rank first (got {ids})")
    if not all(c.get("mood_fit") for c in ranked):
        fail("every ranked candidate must carry a mood_fit rationale")
    ok(f"ranked {ids} with rationales attached")

    # 5) the manifest entry carries the rationale (E3 entry plumbing)
    e = fm.entry_for_download("archive_cc", "Epic Score", "https://x/y.mp3",
                              license_="CC0 (public domain, archive.org licenseurl)",
                              creator="z", license_url="https://l/1",
                              mood_fit="mood keyword hit ['cinematic'] (mood=cinematic)")
    if not e.get("mood_fit"):
        fail("entry_for_download dropped the mood_fit rationale - "
             "media_manifest.json would stay mood-blind")
    ok(f"manifest entry carries mood_fit: {e['mood_fit']}")

    # 6) every declared mood has a family and a veto list (no silent families)
    for mood in fm.ARCHIVE_QUERIES:
        fam = fm.MOOD_FAMILY.get(mood)
        if not fam or not fm.MOOD_VETO.get(fam):
            fail(f"mood '{mood}' has no family/veto mapping - mood screen silent")
    ok(f"all {len(fm.ARCHIVE_QUERIES)} moods mapped to veto families")

    # 7) ship-run lesson: spoken-word (librivox audiobooks) is not music for
    #    ANY mood - vetoed via the identifier even with a neutral title
    fits, score, why = fm.mood_fit("The Odyssey", "LibriVox volunteers", [],
                                   "cinematic", identifier="odyssey_butler_librivox")
    if fits:
        fail(f"spoken-word hardening present: a librivox audiobook passed the "
             f"music screen (why={why!r})")
    if "spoken-word" not in why:
        fail(f"spoken-word veto rationale must say 'spoken-word' (got {why!r})")
    ok(f"librivox audiobook vetoed: {why}")

    print("R4 PROBE: PASS (mood screen + rationale in the manifest)")


if __name__ == "__main__":
    main()
