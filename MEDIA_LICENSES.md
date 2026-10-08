# MEDIA_LICENSES.md

| Asset | Source | License | Safe for Shorts | Attribution required |
|---|---|---|---|---|
| Source video (user URL) | provided by user | user responsibility — verify before publishing | depends on source | depends on source |
| Source video (no URL) | Blender Foundation — Big Buck Bunny | CC-BY 3.0 | yes | yes (credit "Blender Foundation") |
| Music (mood-based) | FreePD.com | CC0 / public domain dedication | yes | no |
| Music (fallback) | generated in-pipeline (ffmpeg synthesis) | none — original | yes | no |
| Fonts | DejaVu (fonts-dejavu-core) | Bitstream Vera license (free) | yes | no |
| Test footage (experiments) | Blender open movies (Sintel etc.) | CC-BY | yes (attribution in reports) | yes |

Rules enforced by pipeline:
- `fetch_music.py` only downloads from FreePD (CC0) or a user-supplied URL; never popular copyrighted music.
- `media_manifest.json` records title/url/license/attribution for every acquired asset.
- Generated outputs (montage edits) are derivative works of the source video; distribution responsibility stays with the source owner.
