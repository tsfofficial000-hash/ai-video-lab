#!/usr/bin/env python3
"""W4: the E-sweep music evidence pre-dated the spoken-word veto - and the
post-veto re-runs still shipped radio collections as "music".

Audit W4: two of three sweep drafts used spoken-word archive items as
"music" ("The Adventures of Sherlock Holmes", "The Odyssey", "Jack Benny
143 Eps" - audiobook/radio), dispatched before the R4 veto (7896a2c).
Post-veto re-runs (runs 38123324831 / 38123342283, HEAD 42703c0) still
picked "Tales Of The Texas Rangers" (OTR crime-drama series) and
"Jack Benny 143 Eps" (radio comedy collection): their metadata carries no
librivox marker, so the substring veto scored them "neutral".

Fix contract:
  - the veto learns old-time-radio + episode-collection shapes (multi-word
    radio phrases; "143 Eps"/"Ep 5"/"Episode"/"OTR" patterns) - a bare
    'radio' would false-veto music like 'Radioactive';
  - the two actual W4 failure items are vetoed; genuine music survives;
  - sweep conclusions about music mood-fit are drawn from post-veto,
    post-strengthening picks only, and the stale assert rows are marked
    invalid in reports/cineforge/drafts-v2.1/.

Probe is offline: exercises mood_fit on the real W4 metadata shapes plus
the R4 regression cases. Probe exit 0 = contract holds; exit 1 = defect.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import ok, fail, load_module

fm = load_module("fetch_music_under_test_w4", "scripts/cineforge/fetch_music.py")


def main():
    # 1) the two ACTUAL post-veto failures (real metadata shapes from the
    #    re-run manifests + their archive collection subjects)
    fits, score, why = fm.mood_fit("Jack Benny 143 Eps", "unknown",
                                   ["Old Time Radio", "Comedy"], "motivational")
    if fits:
        fail(f"W4 present: 'Jack Benny 143 Eps' (radio comedy collection) "
             f"passes as music (score={score}, why={why!r})")
    ok(f"Jack Benny collection vetoed: {why[:80]}")

    fits, _, why = fm.mood_fit("Tales Of The Texas Rangers", "unknown",
                               ["Old Time Radio", "Crime Drama"], "sad")
    if fits:
        fail(f"W4 present: 'Tales Of The Texas Rangers' (OTR drama series) "
             f"passes as music ({why!r})")
    ok(f"Texas Rangers OTR series vetoed: {why[:80]}")

    # 2) title-only shapes (when the search response carries no subjects)
    fits, _, why = fm.mood_fit("Jack Benny 143 Eps", "", [], "motivational",
                               identifier="JackBenny1")
    if fits:
        fail(f"W4 present: episode-collection title shape '143 Eps' passes "
             f"({why!r})")
    ok(f"episode-collection regex fires on title alone: {why[:76]}")

    # 3) genuine music survives the strengthened veto (recall leg)
    for title, tags, mood in [("Radioactive (Single)", ["rock"], "motivational"),
                              ("Piano Nights", ["instrumental", "piano"], "sad"),
                              ("Epic Cinematic Trailer", ["soundtrack"], "cinematic")]:
        fits, score, why = fm.mood_fit(title, "A. Composer", tags, mood)
        if not fits:
            fail(f"W4 regression: genuine music '{title}' was vetoed ({why!r})")
    ok("genuine music survives (Radioactive / Piano Nights / Epic Cinematic)")

    # 4) R4 regression cases stay vetoed
    fits, _, why = fm.mood_fit("Geometry Dash Soundtrack (CC0)", "unknown",
                               ["geometry dash", "electronic"], "cinematic")
    if fits or "veto" not in why:
        fail(f"R4 audit case must stay vetoed (got fits={fits}, {why!r})")
    fits, _, why = fm.mood_fit("The Odyssey", "Homer (librivox)",
                               ["audiobook"], "cinematic", identifier="odyssey_librivox")
    if fits:
        fail(f"librivox Odyssey must stay vetoed ({why!r})")
    ok("R4 regression cases still vetoed")

    # 5) apply_mood_fit drops the vetoed rows and keeps the ranked music
    cands = [{"title": "Jack Benny 143 Eps", "creator": "", "subject": ["Old Time Radio"],
              "identifier": "JackBenny1"},
             {"title": "Piano Nights", "creator": "A. Composer",
              "subject": ["piano"], "identifier": "piano_nights"}]
    kept = fm.apply_mood_fit([dict(c) for c in cands], "sad")
    titles = [c["title"] for c in kept]
    if "Jack Benny 143 Eps" in titles or len(kept) != 1:
        fail(f"apply_mood_fit must drop the radio collection (kept: {titles})")
    ok(f"apply_mood_fit keeps only real music: {titles}")

    print("W4 PROBE: PASS (OTR/episode collections vetoed; genuine music "
          "survives; R4 regressions hold)")
    sys.exit(0)


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"W4 PROBE: CRASH (infra): {type(e).__name__}: {e}")
        sys.exit(2)
