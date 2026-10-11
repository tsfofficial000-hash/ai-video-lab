# MEDIA_LICENSES.md

| Asset | Source | License | Safe for Shorts | Attribution required |
|---|---|---|---|---|
| Source video (user URL) | provided by user | user responsibility — verify before publishing | depends on source | depends on source |
| Source video (no URL / `source-v1` cache) | Blender Foundation — Sintel trailer (durian.blender.org) | CC-BY 4.0 | yes | yes — credit "Blender Foundation" (recorded in media_manifest.json + source_video entry) |
| Music (mood-based, rung 2) | FreePD.com | CC0 / public domain dedication | yes | no |
| Music (rung 3 — E3 ladder) | Internet Archive CC items (`archive.org/advancedsearch` filtered `licenseurl:*creativecommons*`, `-collection:librivoxaudio`; NC/ND candidates skipped; mood-keyword screen + 1-line `mood_fit` rationale logged per pick) | CC0 or CC-BY per item `licenseurl` | yes (CC0), yes with credit (CC-BY) | no (CC0) / yes (CC-BY — credit burned as on-screen outro line AND recorded in media_manifest.json) |
| Music (rung 4 — E3 ladder) | incompetech.com direct MP3s, Kevin MacLeod | CC BY 4.0 | yes | **yes — credit string `Music: <title> - Kevin MacLeod (incompetech.com), Licensed under CC BY 4.0` burned in the outro + manifest; shipped in v2.1: "Healing"** |
| Music (rung 5 — last resort only) | generated in-pipeline (ffmpeg synthesis) | none — original | yes | no — permitted only with a logged egress-failure reason (gate G6 goes RED otherwise) |
| Fonts | Anton, Bebas Neue, Montserrat (fetch_fonts.py, cached in media/fonts) | SIL Open Font License 1.1 | yes | no (OFL: no attribution required; license files cached per font) |
| Fallback fonts | DejaVu (fonts-dejavu-core) | Bitstream Vera license (free) | yes | no |
| Test footage (experiments) | Blender open movies (Sintel etc.) | CC-BY | yes (attribution in reports) | yes |

Rules enforced by pipeline:
- `fetch_music.py` walks a declared source ladder — user URL → FreePD CC0 → Internet Archive CC (mood-screened: genre-veto + keyword rank + spoken-word veto incl. the archive identifier; NC/ND filtered by `licenseurl`) → incompetech CC-BY → synth pad. Every candidate is ffprobe-verified (decodable audio, ≥ 20 s) before use.
- `media_manifest.json` records title / url / license / license_url / attribution / credit / via / mood / mood_fit for every acquired asset; gate G10 fails the run if any manifested asset lacks a license.
- CC-BY music triggers an on-screen outro credit line (captions.py) in addition to the manifest record.
- Music mood fit is screened, not guaranteed: the 1-line `mood_fit` rationale in the manifest states WHY each pick was accepted (keyword hit, neutral metadata, or curated fallback) so a mood-blind pick is always visible in evidence.
- Generated outputs (montage edits) are derivative works of the source video; distribution responsibility stays with the source owner.
- Zero paid APIs, zero watermarked assets, zero popular copyrighted music (FREE-ONLY mandate).
