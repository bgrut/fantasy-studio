# HDRI Environment Maps

Drop `.hdr` or `.exr` files here for photoreal lighting. The orchestrator auto-loads them based on the scene's mood.

## Mood → filename mapping

| Mood | Expected filename |
|---|---|
| sunset, sunrise, dusk | `venice_sunset.hdr` |
| golden hour | `golden_gate_hills.hdr` |
| noon, daylight, dawn, bright | `kloppenheim_06.hdr` |
| night, moonlight, moody | `moonlit_golf.hdr` |
| studio | `studio_small_09.hdr` |

If a file is missing, the orchestrator falls back gracefully to the flat sky color preset.

## Where to download (free, CC0)

[Poly Haven HDRIs](https://polyhaven.com/hdris) — all CC0 licensed.

Recommended:
- https://polyhaven.com/a/venice_sunset
- https://polyhaven.com/a/golden_gate_hills
- https://polyhaven.com/a/kloppenheim_06
- https://polyhaven.com/a/moonlit_golf
- https://polyhaven.com/a/studio_small_09

Download the **2K resolution** version (smaller file, plenty for our render sizes). 4K+ is overkill and slows IO.

## Quick install (bash)

```bash
cd backend/assets/hdri
curl -L -o venice_sunset.hdr "https://dl.polyhaven.org/file/ph-assets/HDRIs/hdr/2k/venice_sunset_2k.hdr"
curl -L -o golden_gate_hills.hdr "https://dl.polyhaven.org/file/ph-assets/HDRIs/hdr/2k/golden_gate_hills_2k.hdr"
curl -L -o kloppenheim_06.hdr "https://dl.polyhaven.org/file/ph-assets/HDRIs/hdr/2k/kloppenheim_06_2k.hdr"
curl -L -o moonlit_golf.hdr "https://dl.polyhaven.org/file/ph-assets/HDRIs/hdr/2k/moonlit_golf_2k.hdr"
curl -L -o studio_small_09.hdr "https://dl.polyhaven.org/file/ph-assets/HDRIs/hdr/2k/studio_small_09_2k.hdr"
```

PowerShell equivalent:
```powershell
$base = "https://dl.polyhaven.org/file/ph-assets/HDRIs/hdr/2k"
Invoke-WebRequest "$base/venice_sunset_2k.hdr" -OutFile "venice_sunset.hdr"
Invoke-WebRequest "$base/golden_gate_hills_2k.hdr" -OutFile "golden_gate_hills.hdr"
Invoke-WebRequest "$base/kloppenheim_06_2k.hdr" -OutFile "kloppenheim_06.hdr"
Invoke-WebRequest "$base/moonlit_golf_2k.hdr" -OutFile "moonlit_golf.hdr"
Invoke-WebRequest "$base/studio_small_09_2k.hdr" -OutFile "studio_small_09.hdr"
```

Total download: ~25-40 MB. One-time setup.
