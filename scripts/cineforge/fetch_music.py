#!/usr/bin/env python3
"""Mood-based royalty-free music acquisition (defect E3: real music, not synth).

Source ladder (first verified success wins):
  1. user URL (--url)            - rights checked by the caller
  2. FreePD CC0                  - configs/music_moods.json "moods"
  3. Internet Archive CC items   - advancedsearch licenseurl:*creativecommons*,
                                   direct /download/ MP3s (NC/ND filtered out)
  4. incompetech CC-BY 4.0       - direct MP3s, Kevin MacLeod; attribution is
                                   rendered in the report AND as a 1-line
                                   on-screen outro credit
  5. synth pad                   - LAST RESORT only, and only with the full
                                   egress-failure log recorded in the manifest
                                   (gate G6: music_via != synth whenever
                                   network egress works)

Every successful download is ffprobe-verified (decodable audio, >= 20 s) and
recorded in media_manifest.json with license + attribution + via.
"""
import argparse
import json
import os
import subprocess
import urllib.parse
import urllib.request

UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) Gecko/20100101 Firefox/132.0"}
FREEPD = "https://freepd.com/music/"
INCOMPETECH = "https://incompetech.com/music/royalty-free/mp3-royaltyfree/"

# Declared source ladder (E3 contract; e3 probe asserts this shape).
SOURCE_LADDER = [
    {"kind": "freepd", "license": "CC0 (FreePD.com, Kevin MacLeod et al.)",
     "candidates_from": "configs/music_moods.json moods.<mood>"},
    {"kind": "archive_cc", "license": "CC0 / CC-BY (archive.org licenseurl filter)",
     "query_from": "configs/music_moods.json archive_queries.<mood>"},
    {"kind": "incompetech_ccb", "license": "CC BY 4.0 (incompetech.com, Kevin MacLeod)",
     "url": INCOMPETECH + "Cipher.mp3"},
    {"kind": "incompetech_ccb", "license": "CC BY 4.0 (incompetech.com, Kevin MacLeod)",
     "url": INCOMPETECH + "Healing.mp3"},
    {"kind": "incompetech_ccb", "license": "CC BY 4.0 (incompetech.com, Kevin MacLeod)",
     "url": INCOMPETECH + "Meditation%20Impromptu%2002.mp3"},
    {"kind": "incompetech_ccb", "license": "CC BY 4.0 (incompetech.com, Kevin MacLeod)",
     "url": INCOMPETECH + "Frost%20Waltz.mp3"},
    {"kind": "synth_fallback", "license": "generated in-pipeline (no third-party rights)",
     "requires": "logged egress/source failures"},
]

ARCHIVE_QUERIES = {
    "cinematic": "(cinematic OR soundtrack OR orchestral)",
    "sad": "(sad OR melancholy OR piano instrumental)",
    "emotional": "(emotional OR touching OR piano)",
    "dark": "(dark ambient OR tension)",
    "motivational": "(upbeat OR energetic instrumental)",
    "epic": "(epic OR trailer music)",
    "lofi": "(lofi OR chillhop)",
    "chill": "(chill OR relaxed instrumental)",
    "ambient": "(ambient OR drone)",
    "phonk": "(phonk OR trap instrumental)",
    "horror": "(horror OR suspense)",
}

# R4: license-safe is not mood-safe. A CC0 geometry-dash track matched the
# cinematic advancedsearch query via the fuzzy OR - so archive results are
# screened TWICE: veto keywords kill genre-contradicting items outright,
# positive keywords rank true mood matches first. Pure tag/title heuristic
# (archive metadata carries subjects, not BPM).
MOOD_FAMILY = {
    "cinematic": "score", "epic": "score", "dark": "score", "horror": "score",
    "sad": "sad", "emotional": "sad",
    "motivational": "hype", "phonk": "hype",
    "lofi": "calm", "chill": "calm", "ambient": "calm",
}
MOOD_VETO = {
    "score": ["geometry dash", "geometry", "game", "arcade", "chiptune",
              "8bit", "8-bit", "8 bit", "bitpop", "dubstep", "edm",
              "electronic dance", "house", "techno", "phonk", "trap",
              "jumpstyle", "hyperpop", "hardstyle", "nightcore"],
    "sad": ["dubstep", "edm", "metal", "hardcore", "screamo", "phonk",
            "trap", "workout", "party", "club", "geometry dash", "game",
            "arcade", "chiptune"],
    "hype": ["sleep", "lullaby", "meditation", "whale sounds", "asmr"],
    "calm": ["dubstep", "edm", "metal", "hardcore", "screamo", "aggressive",
             "phonk", "drum and bass", "jungle", "workout", "hype",
             "geometry dash", "game", "arcade", "chiptune"],
}


def _mood_keywords(mood):
    kws = {mood.lower()}
    for tok in (ARCHIVE_QUERIES.get(mood) or "").replace("(", " ") \
            .replace(")", " ").replace("OR", " ").split(","):
        t = tok.strip().lower()
        if t:
            kws.add(t)
    return sorted(kws)


def mood_fit(title, creator, tags, mood):
    """R4 heuristic: (fits, rank_score, 1-line rationale).
    veto keyword anywhere -> reject; else rank by positive keyword hits;
    neutral metadata still passes (ranked below hits) so recall survives."""
    tag_list = tags if isinstance(tags, list) else ([tags] if tags else [])
    text = " ".join([str(title or ""), str(creator or ""),
                     " ".join(str(t) for t in tag_list)]).lower()
    fam = MOOD_FAMILY.get((mood or "").lower(), "score")
    for kw in MOOD_VETO.get(fam, []):
        if kw in text:
            return False, 0, (f"vetoed: '{kw}' in title/creator/tags "
                              f"contradicts mood '{mood}'")
    hits = [kw for kw in _mood_keywords(mood) if kw in text]
    if hits:
        return True, 2 + len(hits), (f"mood keyword hit {hits[:3]} in "
                                     f"title/creator/tags (mood={mood})")
    return True, 0, f"neutral metadata - no mood contradiction for '{mood}'"


def apply_mood_fit(cands, mood):
    """R4: filter + rank archive candidates in place (search order = download
    rank, so the sort must be stable); attaches a mood_fit rationale to each
    surviving candidate for the media_manifest.json entry."""
    kept = []
    for c in cands:
        fits, score, why = mood_fit(c.get("title"), c.get("creator"),
                                    c.get("subject"), mood)
        if not fits:
            continue
        c = dict(c, mood_fit=why, mood_score=score)
        kept.append(c)
    kept.sort(key=lambda c: -c["mood_score"])   # stable: keeps download rank
    return kept


def dl(url, dest, timeout=120):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r, open(dest, "wb") as f:
        while True:
            chunk = r.read(1 << 16)
            if not chunk:
                break
            f.write(chunk)
    return os.path.getsize(dest)


def probe_ok(path):
    try:
        d = json.loads(subprocess.check_output(
            ["ffprobe", "-v", "error", "-print_format", "json", "-show_format", path]).decode())
        return float(d["format"]["duration"]) > 20
    except Exception:
        return False


def _has_audio(path):
    try:
        out = subprocess.run(["ffprobe", "-v", "error", "-show_entries",
                              "stream=codec_type", "-of", "csv=p=0", path],
                             capture_output=True, text=True).stdout
        return "audio" in out
    except Exception:
        return False


def _heal_container(path):
    """Re-mux/re-encode via forced mp3 demuxer when the container confuses probes."""
    fixed = path + ".fixed.mp3"
    r = subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "mp3", "-i", path,
                        "-c:a", "libmp3lame", "-b:a", "128k", fixed],
                       capture_output=True, text=True)
    if r.returncode == 0 and _has_audio(fixed):
        os.replace(fixed, path)
        return True
    if os.path.isfile(fixed):
        os.remove(fixed)
    return False


def _egress_ok(timeout=10):
    """Cheap positive egress probe against the fonts host (proven reachable in
    runners). Used to justify a synth fallback honestly: egress OK + synth =
    every real source is broken (gate G6 goes RED); egress dead + synth =
    acceptable with the logged reason."""
    try:
        req = urllib.request.Request(
            "https://raw.githubusercontent.com/google/fonts/main/ofl/anton/OFL.txt",
            headers=UA)
        with urllib.request.urlopen(req, timeout=timeout) as r:
            r.read(64)
        return True
    except Exception:
        return False


def synth_pad(dest, seconds=180):
    """Fallback: CC0-equivalent generated ambient pad (no third-party rights)."""
    seconds = max(4, int(seconds))
    fade_out_st = max(0.0, seconds - 8)
    fade_out_d = min(6.0, max(1.0, seconds / 2.0))
    cmd = ["ffmpeg", "-v", "error", "-y",
           "-f", "lavfi", "-i", "sine=frequency=110:duration=%d" % seconds,
           "-f", "lavfi", "-i", "sine=frequency=165.2:duration=%d" % seconds,
           "-f", "lavfi", "-i", "anoisesrc=color=brown:amplitude=0.04:duration=%d" % seconds,
           "-filter_complex",
           "[0:a]volume=0.35[a0];[1:a]volume=0.22[a1];[2:a]lowpass=f=400,volume=0.18[a2];"
           "[a0][a1][a2]amix=inputs=3:duration=longest,tremolo=f=0.15:d=0.4,"
           "afade=t=in:d=1,afade=t=out:st=%.3f:d=%.3f,aformat=channel_layouts=stereo"
           % (fade_out_st, fade_out_d),
           "-c:a", "libmp3lame", "-b:a", "128k", dest]
    subprocess.run(cmd, check=True)


def write_synth_entry(dest, manifest, seconds=180, failures=None, egress_ok=False):
    """Last-resort synth WITH the honest failure log (E3/G6 contract)."""
    synth_pad(dest, seconds=seconds)
    if not _has_audio(dest):
        if not _heal_container(dest):
            raise SystemExit("synth pad produced no decodable audio")
    entry = {"license": "generated in-pipeline (no third-party rights)",
             "title": "generated_ambient_pad.mp3", "url": None,
             "via": "synth_fallback", "mood": None,
             "attribution_required": False, "safe_for_shorts": True,
             "bytes": os.path.getsize(dest),
             "egress_ok": bool(egress_ok),
             "egress_failures": list(failures or [])}
    _write(manifest, "music", entry)
    return entry


def entry_for_download(kind, title, url, license_=None, creator=None, license_url=None,
                       mood_fit=None):
    """Manifest entry for a verified real-music download (E3 + R4 contract)."""
    if kind == "incompetech_ccb":
        entry = {"license": "CC BY 4.0 (incompetech.com, Kevin MacLeod)",
                 "attribution_required": True,
                 "credit": f"Music: {title} - Kevin MacLeod (incompetech.com), "
                           f"Licensed under CC BY 4.0"}
    elif kind == "archive_cc":
        entry = {"license": license_ or "CC (archive.org licenseurl)",
                 "attribution_required": "CC0" not in (license_ or ""),
                 "credit": (f"{title} - {creator} ({license_url})" if creator
                            else f"{title} ({license_url})")}
    elif kind == "freepd":
        entry = {"license": "CC0 (FreePD.com, Kevin MacLeod et al.)",
                 "attribution_required": False, "credit": None}
    else:
        entry = {"license": license_ or "user-provided (verify rights before publishing)",
                 "attribution_required": False, "credit": None}
    entry.update({"via": kind, "title": title, "url": url, "safe_for_shorts": True,
                  "mood": None})
    if license_url:
        entry["license_url"] = license_url
    if mood_fit:
        entry["mood_fit"] = mood_fit
    return entry


def archive_search(mood):
    """advancedsearch query string filtered to Creative-Commons-licensed audio."""
    kw = ARCHIVE_QUERIES.get(mood, "(instrumental OR soundtrack)")
    return ("https://archive.org/advancedsearch.php?q=licenseurl%3A%2Acreativecommons%2A"
            "+AND+mediatype%3Aaudio+AND+"
            + urllib.parse.quote(kw) +
            "&fl%5B%5D=identifier&fl%5B%5D=title&fl%5B%5D=creator&fl%5B%5D=licenseurl"
            "&sort%5B%5D=downloads+desc&rows=8&output=json")


def archive_download_url(identifier, filename):
    return f"https://archive.org/download/{urllib.parse.quote(identifier)}/{filename}"


def _license_from_archive_url(lu):
    """Rights-clean filter: CC0/CC-BY only. NC/ND candidates are skipped
    (NC breaks monetized shorts; ND forbids editing)."""
    lu = (lu or "").lower()
    if "zero" in lu or "publicdomain" in lu:
        return "CC0 (public domain, archive.org licenseurl)"
    if "/by/" in lu or lu.endswith("/by") or "by-4" in lu or "by/4" in lu:
        return "CC BY (archive.org licenseurl)"
    return None   # NC / ND / unknown -> skip


def _archive_candidates(mood, failures):
    """[{"identifier","title","creator","licenseurl","file"}] verified metadata,
    mood-screened and ranked (R4: veto + keyword rank, rationale attached)."""
    q = archive_search(mood)
    try:
        req = urllib.request.Request(q, headers=UA)
        with urllib.request.urlopen(req, timeout=45) as r:
            docs = json.load(r).get("response", {}).get("docs", [])
    except Exception as e:
        failures.append(f"archive_cc: search failed: {type(e).__name__}")
        return []
    out = []
    for d in docs[:8]:
        lu = d.get("licenseurl") or ""
        lic = _license_from_archive_url(lu)
        if not lic:
            continue
        ident = d.get("identifier")
        try:
            req = urllib.request.Request(f"https://archive.org/metadata/{ident}", headers=UA)
            with urllib.request.urlopen(req, timeout=45) as r:
                md = json.load(r)
        except Exception as e:
            failures.append(f"archive_cc: metadata {ident}: {type(e).__name__}")
            continue
        files = [f for f in md.get("files", [])
                 if (f.get("name") or "").lower().endswith(".mp3")
                 and int(float(f.get("size") or 0)) > 300_000]
        if not files:
            continue
        subj = md.get("metadata", {}).get("subject") or []
        out.append({"identifier": ident, "file": files[0]["name"],
                    "title": md.get("metadata", {}).get("title") or ident,
                    "creator": md.get("metadata", {}).get("creator") or "unknown",
                    "subject": subj if isinstance(subj, list) else [str(subj)],
                    "licenseurl": lu, "license": lic})
    # R4: veto + rank by mood fit BEFORE any download is attempted
    ranked = apply_mood_fit(out, mood)
    for c in out:
        if c["identifier"] not in {k["identifier"] for k in ranked}:
            failures.append(f"archive_cc: {c['identifier']}: mood-vetoed "
                            f"({mood_fit(c.get('title'), c.get('creator'), c.get('subject'), mood)[2]})")
    return ranked


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mood", default="cinematic")
    ap.add_argument("--url", default=None, help="user-provided music URL overrides mood")
    ap.add_argument("--out", default="media/music.mp3")
    ap.add_argument("--manifest", default="reports/media_manifest.json")
    a = ap.parse_args()

    os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
    failures = []
    egress = _egress_ok()

    if a.url:
        try:
            sz = dl(a.url, a.out)
            ok = probe_ok(a.out)
            entry = entry_for_download("user_url", os.path.basename(a.url), a.url)
            entry.update({"safe_for_shorts": ok, "bytes": sz})
            if ok:
                print(json.dumps({"status": "ok", **entry}))
                _write(a.manifest, "music", entry)
                return
            failures.append("user_url: probe failed")
        except Exception as e:
            failures.append(f"user_url: {type(e).__name__}")
            print(f"user url failed: {e}", flush=True)

    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    cfg = json.load(open(os.path.join(repo_root, "configs", "music_moods.json")))

    # 2) FreePD CC0
    for name in cfg["moods"].get(a.mood, cfg["moods"]["cinematic"]):
        url = FREEPD + name.replace(" ", "%20")
        try:
            sz = dl(url, a.out)
            if probe_ok(a.out):
                entry = entry_for_download("freepd", name, url)
                entry.update({"mood": a.mood, "bytes": sz,
                              "mood_fit": f"curated mood list for '{a.mood}' "
                                          f"(configs/music_moods.json)"})
                print(json.dumps({"status": "ok", **entry}))
                _write(a.manifest, "music", entry)
                return
            failures.append(f"freepd: {name}: probe failed")
        except Exception as e:
            failures.append(f"freepd: {name}: {type(e).__name__}")
            print(f"candidate failed: {name}: {type(e).__name__}", flush=True)

    # 3) Internet Archive CC items (R4: mood-screened + ranked)
    for cand in _archive_candidates(a.mood, failures):
        url = archive_download_url(cand["identifier"], urllib.parse.quote(cand["file"]))
        try:
            sz = dl(url, a.out)
            if probe_ok(a.out):
                entry = entry_for_download("archive_cc", cand["title"], url,
                                           license_=cand["license"],
                                           creator=cand["creator"],
                                           license_url=cand["licenseurl"],
                                           mood_fit=cand.get("mood_fit"))
                entry.update({"mood": a.mood, "bytes": sz, "identifier": cand["identifier"]})
                print(json.dumps({"status": "ok", **entry}))
                _write(a.manifest, "music", entry)
                return
            failures.append(f"archive_cc: {cand['identifier']}: probe failed")
        except Exception as e:
            failures.append(f"archive_cc: {cand['identifier']}: {type(e).__name__}")

    # 4) incompetech CC-BY direct MP3s
    for src in [s for s in SOURCE_LADDER if s["kind"] == "incompetech_ccb"]:
        url = src["url"]
        name = urllib.parse.unquote(url.rsplit("/", 1)[-1]).replace(".mp3", "")
        try:
            sz = dl(url, a.out)
            if probe_ok(a.out):
                entry = entry_for_download("incompetech_ccb", name, url)
                entry.update({"mood": a.mood, "bytes": sz,
                              "mood_fit": f"curated CC-BY fallback list "
                                          f"(declared mood '{a.mood}'; "
                                          f"no per-item fit metadata)"})
                print(json.dumps({"status": "ok", **entry}))
                _write(a.manifest, "music", entry)
                return
            failures.append(f"incompetech_ccb: {name}: probe failed")
        except Exception as e:
            failures.append(f"incompetech_ccb: {name}: {type(e).__name__}")
            print(f"candidate failed: {name}: {type(e).__name__}", flush=True)

    # 5) synth - last resort, with the honest failure log (G6 reads this)
    print(f"all music sources failed (egress_ok={egress}); failures:", flush=True)
    for f_ in failures:
        print(f"  - {f_}", flush=True)
    entry = write_synth_entry(a.out, a.manifest, seconds=180,
                              failures=failures, egress_ok=egress)
    entry["mood"] = a.mood
    entry["mood_fit"] = "n/a - synth fallback after logged egress/source failures"
    _write(a.manifest, "music", entry)
    print(json.dumps({"status": "ok", **entry}))


def _write(manifest, key, val):
    data = {}
    if os.path.isfile(manifest):
        try:
            data = json.load(open(manifest))
        except Exception:
            pass
    data[key] = val
    os.makedirs(os.path.dirname(manifest) or ".", exist_ok=True)
    json.dump(data, open(manifest, "w"), indent=1)


if __name__ == "__main__":
    main()
