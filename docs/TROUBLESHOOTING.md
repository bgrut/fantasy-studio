# Troubleshooting

Common issues and fixes, organized by category. If your issue isn't here, open a [bug report](https://github.com/bgrut/fantasy-studio/issues/new?template=bug_report.md) with the pipeline trace log attached.

> Pro tip: most render issues can be diagnosed by grepping the pipeline trace at `outputs/blender_render_<timestamp>/pipeline_trace.log` for the relevant `[CATEGORY]` marker.

---

## Setup issues

### Ollama not reachable

**Symptom**: Backend logs show `[LLM] Ollama unreachable`. Renders fall back to deterministic director (works, but less creative).

**Likely cause**: Ollama service not running, or running on a non-default port.

**Fix:**
1. Open a terminal and run `ollama serve`. If it errors with "address already in use", the service is running — see step 3.
2. Check the system tray for the Ollama icon.
3. Test: `curl http://localhost:11434` should return `Ollama is running`.
4. Restart Ollama from system tray → Quit → relaunch.

**If that doesn't work**: confirm Windows Firewall isn't blocking `ollama.exe`. Check Event Viewer for a startup error.

---

### Blender executable not found

**Symptom**: `[RENDER] Blender executable not found at expected paths`.

**Likely cause**: Blender installed to a non-default location, or version too old.

**Fix:**
1. Confirm Blender 5.1+ is installed at `C:\Program Files\Blender Foundation\Blender 5.1\blender.exe`
2. Or set `BLENDER_EXE` environment variable to your actual path:
   ```powershell
   $env:BLENDER_EXE = "D:\Apps\Blender\blender.exe"
   ```
3. Restart the backend.

**If that doesn't work**: check `_resolve_blender_exe()` in `tools/downloads_ingestor.py` — it checks Blender 5.1, 4.2, and a generic fallback path.

---

### Python venv won't activate

**Symptom**: `.\venv\Scripts\Activate.ps1` errors with "running scripts is disabled on this system".

**Likely cause**: PowerShell ExecutionPolicy is set to Restricted (Windows default).

**Fix** (run PowerShell as admin once):
```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

---

### npm install fails with native build errors

**Symptom**: `node-gyp` errors mentioning Visual Studio or Python.

**Likely cause**: Some optional native dependencies need Windows build tools.

**Fix:**
1. Install Windows Build Tools: `npm install --global windows-build-tools` (once, as admin)
2. Re-run `npm install`
3. If a single package fails, try `npm install --ignore-scripts` and confirm the failing package isn't critical

---

### Port 8000 (or 5173) already in use

**Symptom**: `[Errno 48] Address already in use` on backend startup, or `Port 5173 is in use, trying another one...` on frontend.

**Likely cause**: A previous instance is still running, or another app grabbed the port.

**Fix (Windows):**
```powershell
# Find what's holding the port
netstat -ano | findstr :8000
# Kill by PID
taskkill /PID <pid> /F
```

---

## Render issues

### CUDA out of memory

**Symptom**: Cycles tier renders abort with `CUDA error: out of memory`.

**Likely cause**: Scene geometry + textures exceed GPU VRAM. Common with environments + heavy hero meshes (Ferrari at 113 MB, etc.).

**Fix:**
1. Drop to Quick Preview tier (Eevee, much lower VRAM)
2. Close other GPU apps (Chrome, OBS, games)
3. In `app/services/asset_post_filter.py`, reduce hero mesh budget if persistent
4. Switch to CPU rendering if you must (slower but VRAM-unbounded)

---

### Render hangs at "RENDER_START" with no progress

**Symptom**: Backend logs `[PIPELINE] +X.XXXs RENDER_START` then nothing for minutes.

**Likely cause**: Cycles is compiling shaders for the first time, or hit a node-tree edge case.

**Fix:**
1. Wait 2–5 minutes — first Cycles render of any session compiles GPU kernels
2. If it's been 10+ minutes, check Task Manager → blender.exe should be at high GPU/CPU usage
3. Kill the Blender process; the backend will recover. Try again
4. If reproducible, paste the manifest at `outputs/manifests/manifest_<ts>.json` into a bug report

---

### Output is blank / black frames

**Symptom**: MP4 plays but every frame is black.

**Likely cause**: Lighting failure — no lights in scene, or all lights aimed away from hero.

**Fix:**
1. Check `[LIGHTING]` and `[LIGHT_FIX]` lines in pipeline_trace.log
2. Look for `[LIGHT_GUARANTEE] lights=N total_energy=W` — total_energy < 1000 is suspicious
3. Try a different recipe (force via a different prompt phrasing)

---

### Wrong asset picked by matcher

**Symptom**: Prompted for "elephant", got rhinoceros.

**Likely cause**: Subject normalization or scoring threshold issue.

**Fix:**
1. Check `[MATCHER] picked=… runner_up=…` in the log — confirms what scored what
2. If the matcher is right but the *render* shows the wrong thing, see "Duplicate cars in render" below
3. Manually override via the cast panel "Change cast" button

---

### Duplicate cars / dual heroes in render (V1.4.1.1 LOD twin)

**Symptom**: Two of the same vehicle appear in the render, one correctly placed, one oversized.

**Likely cause**: The source `.blend` ships with two complete LOD copies under sibling Sketchfab_model parents. The V1.4.1.1 `[LOD_CLEANUP]` pass should handle this.

**Fix:**
1. Confirm the `[LOD_CLEANUP]` line appears in pipeline_trace.log
2. Look for `[LOD_CLEANUP] hid N LOD alternates` — if N is 0 but you still see duplicates, file a bug with the trace log
3. Check `app/data/vehicle_lod_audit.json` — if the asset is `unknown`, it may be a new failure mode

---

### Frame drops / stutters in MP4

**Symptom**: MP4 has visible jumps every few frames.

**Likely cause**: ffmpeg encoding hiccup, or render saved a corrupted PNG mid-pipeline.

**Fix:**
1. Check `outputs/blender_render_<ts>/` for missing `frame_NNNN.png` files
2. If any are missing, the render aborted partway. Pipeline log will show why
3. Re-render the same prompt — most flake-class renders succeed on retry

---

## Asset issues

### Auto-fetched asset is low quality / wrong subject

**Symptom**: Library doesn't have what you asked for; Objaverse fallback returned a placeholder cube or unrelated mesh.

**Likely cause**: Objaverse search ranking favored a wrong tag match.

**Fix:**
1. Use the cast panel "Change cast" to manually pick from the curated library
2. If your subject genuinely isn't in the library, add it via the watcher: drop a `.glb`/`.zip` into `Downloads/` with `tools/downloads_ingestor.py watch` running

---

### Asset orientation wrong (lying on its side, upside down)

**Symptom**: Hero is rotated wrong on import.

**Likely cause**: Source file authored with non-standard axes; healer didn't catch it on ingest.

**Fix (one-time per asset):**
1. In `app/data/library.json`, find the entry by id
2. Add `"import_rotation_xyz": [180, 0, 0]` (try `[90,0,0]`, `[180,0,0]`, `[0,0,180]`)
3. Save and re-render — `[ASSET_ORIENT_OVERRIDE]` log line confirms the override fired

This is the same pattern V1.3.6 used for the BMW orientations.

---

### Asset scale wrong (too small / too large)

**Symptom**: Hero diagonal way off from real-world size.

**Likely cause**: Source file authored at non-standard scale; healer captured the wrong scale class.

**Fix:**
1. Check `[FORCE_FIX]` lines in pipeline_trace.log for the actual size at render time
2. If hero diag < 0.2m or > 50m, HERO_VERIFY will abort. Fix: edit `library.json` to set `scale_class` correctly (`tiny` / `small` / `medium` / `large` / `huge`)
3. After V1.4.1, the floor is 0.20× target — vehicles in character envs render at authored size now

---

### Asset thumbnail missing / broken

**Symptom**: Cast panel shows a placeholder block instead of a thumbnail.

**Likely cause**: Thumbnail wasn't generated, or asset file path doesn't resolve.

**Fix:**
1. Run `python scripts/generate_thumbnails.py` (regenerates missing thumbs)
2. If that fails, the asset file path is broken — check `library.json` entry's `path` field exists on disk

---

## Quality issues

### Splotchy hero placement (hero floating or buried)

**Symptom**: Hero is mid-air or partially underground.

**Likely cause**: Raycast missed top-facing surface (V1.3.5 added multi-hit raycast for this).

**Fix:**
1. Check `[HERO_PLACE] method=raycast_multihit` line — if `0 ray hits`, the env doesn't have a top surface at hero XY
2. Re-render with a different scene plan (different recipe might place hero differently)

---

### Environment morphed / scaled wrong

**Symptom**: Desert dunes look 5× too big or too small.

**Likely cause**: Env scale clamped (intentional safety) when raw target was extreme.

**Fix:**
1. Check `[ENVIRONMENT] scale clamped: raw=X.XX -> Y.YY` line
2. If clamping is happening, the env asset's authored scale is far from its target. Edit `library.json` for that env entry to set `scale_class` more accurately

---

### Lighting too dark / too bright

**Symptom**: Render is mostly black, or completely blown out.

**Likely cause**: HDRI strength + sun + 3-point lights collide.

**Fix:**
1. Check `[LIGHT_FIX]` lines for `total_energy=NNN` — typical good range is 5,000–25,000 W
2. Pick a different `lighting` preset via the scene controls
3. If consistently wrong for a specific recipe, that's a recipe bug — file an issue

---

### Camera framing bad (subject cut off, too small)

**Symptom**: Hero outside the frame, or filling 5% of it.

**Likely cause**: HERO_VERIFY's `fill_ok` check might have warned but not aborted, or camera director's distance solver picked an extreme value.

**Fix:**
1. Check `[CAMERA_DIRECTOR] subject_fills=N%` — target is 35–70%
2. If the subject is very flat/long, the director's bbox heuristic may struggle. Use a more cinematic recipe (`hero_desert_epic`) or refine via natural language: "wider shot" / "closer in"

---

## Performance issues

### Renders take > 5 minutes for Quick Preview

**Symptom**: Eevee Quick Preview at 720p × 96 frames takes 5+ minutes (expected: ~30s).

**Likely cause**: GPU not being used, or too many lights/effects.

**Fix:**
1. In Blender preferences, confirm Cycles + Eevee both have GPU compute enabled
2. Check `[OPTIMIZER]` lines — meshes/lights count should be reasonable (< 200 meshes, < 15 lights)
3. Drop other GPU apps

---

### Asset download taking forever (Objaverse fallback)

**Symptom**: First-time prompts for an out-of-library subject take 30+ minutes.

**Likely cause**: Objaverse downloads are large and rate-limited.

**Fix:**
1. Check `[OBJAVERSE]` log lines for download progress
2. Consider pre-fetching: search Sketchfab/Poly Haven for the asset, drop into `Downloads/`, let the watcher ingest it once

---

### Frontend lag when browsing library

**Symptom**: Cast panel "Change cast" is slow with 316 assets.

**Likely cause**: All thumbnails loading at once.

**Fix:**
1. Use the category filter to narrow scope
2. If reproducible, file a bug — virtualization is on the V1.5 backlog

---

### Backend memory keeps growing

**Symptom**: After 10+ renders, backend RAM use climbs steadily.

**Likely cause**: Asset cache or render artifact retention.

**Fix:**
1. Restart the backend periodically (workaround)
2. Clear `outputs/` and `assets/cache/` if storage is the concern (regenerable)

---

## Frontend issues

### Cast panel content cut off

**Symptom**: Bottom of cast panel hidden on smaller laptops.

**Likely cause**: Pre-V1.4.3 viewport sizing bug.

**Fix:** Update to V1.4.3+. If still happening, file a bug with screenshot + viewport dimensions.

---

### Library browser slow to load

**Symptom**: "Change cast" takes 5+ seconds to render the grid.

**Likely cause**: Large library + thumbnail decode on main thread.

**Fix:** Filter by category before scrolling; thumbnails are 256×256 PNG and decode lazily.

---

### Scene controls don't affect output

**Symptom**: Change lighting/camera/duration in UI, but render output ignores it.

**Likely cause**: Scene controls weren't propagated to the manifest, or recipe layer overrode them.

**Fix:**
1. Inspect the manifest at `outputs/manifests/manifest_<ts>.json` to confirm the controls are present
2. If they're there but ignored, that's a recipe-precedence bug — file an issue

---

### Video player not playing

**Symptom**: Render completes, MP4 download works, but inline player is blank.

**Likely cause**: MP4 codec mismatch with browser, or autoplay blocked.

**Fix:**
1. Click play manually (browsers block autoplay)
2. Try downloading the MP4 and playing in VLC to confirm the file is valid
3. If valid but browser refuses, the encoding bitrate may be too high — file a bug with the OS/browser

---

## Output issues

### MP4 won't open in some apps

**Symptom**: MP4 plays in Chrome but not in Premiere/Resolve/iMovie.

**Likely cause**: ffmpeg's default H.264 profile is browser-friendly but some NLEs prefer high-profile encoding.

**Fix:** Re-encode in your NLE on import, or use the PNG sequence export instead and import as image sequence.

---

### .blend file won't open / appears corrupted

**Symptom**: Blender errors when opening the `.blend` from the render output.

**Likely cause**: Render aborted mid-save, or zstd compression compatibility issue.

**Fix:**
1. Confirm Blender version is 5.1+ (zstd-compressed blends require it)
2. If the file is < 1 MB, the render aborted before save completed — re-render

---

### GIF output too large

**Symptom**: Animated GIF is 50+ MB, won't upload to social.

**Likely cause**: 12-second renders at full resolution are inherently large as GIF.

**Fix:** Use the MP4 instead (10× smaller for the same content); most platforms accept short MP4 in GIF placeholders.

---

### PNG sequence missing frames

**Symptom**: Frames 0001–0150 present, then 0152, 0153, … (152 missing).

**Likely cause**: Cycles abandoned a frame on a transient GPU error.

**Fix:** Re-render. If reproducible, file a bug with the trace log.

---

## Network issues

### Objaverse timeouts

**Symptom**: `[OBJAVERSE] download timeout` repeated.

**Likely cause**: Objaverse CDN intermittent issues; common during high-traffic periods.

**Fix:** Retry, or pre-ingest the asset manually (download from Objaverse browser, drop into `Downloads/`).

---

### "Sketchfab returned 401 Unauthorized" or "API key invalid"

**Likely cause**: Missing or incorrect Sketchfab API token.

**Fix:**
1. Verify `.env` file exists in `blender-studio-backend/`
2. Verify it contains `SKETCHFAB_API_TOKEN=` followed by your token (no quotes, no spaces around `=`)
3. Restart the backend after creating/editing `.env`
4. Confirm the token is valid at <https://sketchfab.com/settings/password> (check API token section)

**If that doesn't work**: generate a new token from Sketchfab settings and try again. Old tokens can expire. As a workaround pre-V1.0, set the token as a Windows env var instead of via `.env`:
```powershell
[Environment]::SetEnvironmentVariable("SKETCHFAB_API_TOKEN", "your-token", "User")
```
Restart your terminal after setting.

---

### "[SKETCHFAB] skipped (no SKETCHFAB_API_TOKEN)" in pipeline log

**Likely cause**: No Sketchfab token configured. Not actually an error — the fetcher is gracefully no-op'ing.

**Fix:** Follow the [Sketchfab API key setup in INSTALL.md](../INSTALL.md). If you don't need Sketchfab fallback (your curated library covers your prompts), you can ignore this line entirely.

---

### Sketchfab rate limits

**Symptom**: `[SKETCHFAB] 429 Too Many Requests`.

**Likely cause**: Anonymous Sketchfab API rate limit hit.

**Fix:** Wait 1 hour; or sign in to Sketchfab and configure an API key if you're hitting this often.

---

### Poly Haven connection failures

**Symptom**: HDRIs fail to download.

**Likely cause**: Poly Haven CDN (rare).

**Fix:** Retry; or download the HDRI manually and drop into `assets/hdri/`.

---

## Still stuck?

- **GitHub Discussions** — design questions, "is this a bug?"
- **GitHub Issues** — confirmed bugs and feature requests
- **Discord** — coming soon for launch
- **TikTok / YouTube** — DM works for non-technical questions

When opening an issue, **always include the pipeline trace log**. It's the single biggest accelerator.
