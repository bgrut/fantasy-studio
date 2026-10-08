"""Sharp backs and flanks for the library's people (2026-10-08).

scripts/_hd_front.py lays a character's reference photo on its front. The
chase camera mostly sees a hero from behind, and the back and the flanks were
still the coat: smooth, a vertex a few centimetres across. For each person:

1. scripts/_hd_views_render.py renders the coated rest pose straight-on from
   the back and both flanks, orthographic, the camera written to JSON;
2. each render is repainted photographically by SDXL img2img (strength
   ~0.62: real fabric, seams and folds, the silhouette kept), prompted with
   the person's own wardrobe and the side being seen;
3. _hd_front.py projects the reference photo on the front and the repaints on
   the rest (--extra), each through its known camera.

The coated original is kept in renders/_coat_backup_hdfront/.

    python tools/hd_views.py [name ...] [--strength 0.62]
"""
import hashlib
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

BK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BK))
LIB = BK / "assets" / "library"
CACHE = BK / "renders" / "_actor_cache"
BACKUP = BK / "renders" / "_coat_backup_hdfront"
RENDER = BK / "scripts" / "_hd_views_render.py"
FRONT = BK / "scripts" / "_hd_front.py"
VIEWS = {"front": "facing the camera, front view",
         "back": "seen from behind, back view, the back of the head",
         "left": "seen from the side, side view, profile",
         "right": "seen from the side, side view, profile"}
NEG = ("cartoon, illustration, painting, 3d render, cgi, plastic, smooth, blurry, low detail, deformed, extra limbs, "
       "extra arms, face on the back of the head, text, logo, watermark, nude, bare skin, underwear")


def wardrobe(kind: str) -> str:
    """The person's outfit from the reference generator's own table, longest name first."""
    src = (BK / "app" / "asset_gen" / "reference.py").read_text(encoding="utf-8")
    i = src.find("char_hints = {"); j = src.find("\n        }", i)
    table = dict(re.findall(r'^\s+"([a-z][a-z \-]*)":\s*"([^"]+)"', src[i:j], re.M))
    for key in sorted(table, key=len, reverse=True):
        if re.search(r"\b" + re.escape(key) + r"s?\b", kind.lower()):
            return table[key]
    return f"{kind}, fully clothed"


_PIPE = None


def pipe():
    global _PIPE
    if _PIPE is None:
        import torch
        from app.asset_gen.reference import _evict_llms
        _evict_llms()
        from diffusers import StableDiffusionXLImg2ImgPipeline, AutoencoderKL
        vae = AutoencoderKL.from_pretrained("madebyollin/sdxl-vae-fp16-fix", torch_dtype=torch.float16)
        _PIPE = StableDiffusionXLImg2ImgPipeline.from_pretrained(
            "stabilityai/stable-diffusion-xl-base-1.0", vae=vae, torch_dtype=torch.float16, variant="fp16",
            use_safetensors=True).to("cuda")
    return _PIPE


def repaint(src: Path, dst: Path, prompt: str, strength: float, seed: int = 42):
    import torch
    from PIL import Image
    img = Image.open(src).convert("RGB").resize((1024, 1024))
    g = torch.Generator("cuda").manual_seed(seed)
    out = pipe()(prompt=prompt, negative_prompt=NEG, image=img, strength=strength, guidance_scale=6.5,
                 num_inference_steps=36, generator=g).images[0]
    out.save(dst)


def upgrade(anim: Path, strength=0.62, verbose=True) -> str:
    from app.game_export.generate import BLENDER_EXE
    kind = anim.stem[:-len("_anim")].replace("_", " ")
    ref = CACHE / (hashlib.md5(kind.lower().encode("utf-8")).hexdigest()[:12] + "_ref.png")
    if not ref.exists():
        return "no reference"
    # a drawn hero stays drawn: the repaint asks for a photograph
    if kind.split()[0] in ("toon", "anime", "clay", "blocky"):
        return "stylised, left as it is"
    # the coated original, unless the character was made again since (a stale backup is another body)
    static = LIB / (anim.stem[:-len("_anim")] + ".glb")
    bk = BACKUP / anim.name
    fresh = bk.exists() and not (static.exists() and static.stat().st_mtime > bk.stat().st_mtime)
    coated = bk if fresh else anim
    if not fresh and bk.exists():
        bk.unlink()
    tmp = Path(tempfile.mkdtemp(prefix="hdv_"))
    try:
        r = subprocess.run([str(BLENDER_EXE), "--background", "--python", str(RENDER), "--", str(coated), str(tmp / "v"),
                            ",".join(VIEWS)], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=600)
        if not (tmp / "v.json").exists():
            return "render failed"
        outfit = wardrobe(kind)
        extras = []
        for v, phrase in VIEWS.items():
            prompt = (f"raw photograph, DSLR, of a real {outfit}, {phrase}, full body, standing with arms out, "
                      f"soft studio light, plain grey backdrop, sharp focus, detailed fabric texture, seams and folds")
            repaint(tmp / f"v_{v}.png", tmp / f"r_{v}.png", prompt, strength)
            extras += ["--extra", f"{tmp / f'r_{v}.png'}|{tmp / 'v.json'}|{v}"]
        out = anim.with_name(anim.stem + "_hdvtmp.glb")
        r = subprocess.run([str(BLENDER_EXE), "--background", "--python", str(FRONT), "--", str(coated), str(ref), str(out)] + extras,
                           capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=900)
        line = next((l for l in (r.stdout or "").splitlines() if l.startswith(("HDF ", "HDFAIL"))), "HDFAIL no result")
        if not line.startswith("HDF ") or not out.exists():
            out.unlink(missing_ok=True)
            return line
        BACKUP.mkdir(parents=True, exist_ok=True)
        if not (BACKUP / anim.name).exists():
            shutil.copy2(anim, BACKUP / anim.name)
        shutil.move(str(out), str(anim))
        keep = BK / "renders" / "_hd_views" / anim.stem
        keep.mkdir(parents=True, exist_ok=True)
        for f in tmp.glob("r_*.png"):
            shutil.copy2(f, keep / f.name)
        return line + " +views"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    st = float(sys.argv[sys.argv.index("--strength") + 1]) if "--strength" in sys.argv else 0.62
    if "--strength" in sys.argv:
        args = [a for a in args if a != sys.argv[sys.argv.index("--strength") + 1]]
    files = [LIB / f"{a.replace(' ', '_')}_anim.glb" for a in args] if args else sorted(
        f for f in LIB.glob("*_anim.glb") if (BACKUP / f.name).exists())
    for f in files:
        if not f.exists():
            print(f"{f.name}: missing", flush=True); continue
        try:
            print(f"{f.name}: {upgrade(f, st)}", flush=True)
        except Exception as e:
            print(f"{f.name}: error {type(e).__name__}: {e}", flush=True)


if __name__ == "__main__":
    main()
