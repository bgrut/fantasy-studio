"""Build a ControlNet depth template from a chosen clean reference image.

The OLD quadruped_depth.png literally depicted a 5-legged dog, so ControlNet
reproduced 5 legs on every generation. This derives a clean depth map (via MiDaS)
from a user-verified 4-legged dog and installs it as the new template, backing up
the old one.

Usage: python scripts/build_depth_template.py <source.png> <pattern>
       (pattern e.g. "quadruped")
"""
import sys
import shutil
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from PIL import Image  # noqa: E402
from app.refinement.refiner import _make_depth_map  # noqa: E402
from app.asset_gen.reference import POSE_TEMPLATES_DIR  # noqa: E402


def main():
    if len(sys.argv) < 3:
        print("usage: build_depth_template.py <source.png> <pattern>", file=sys.stderr)
        return 2
    src = Path(sys.argv[1]).resolve()
    pattern = sys.argv[2]
    if not src.exists():
        print(f"ERROR: source not found: {src}", file=sys.stderr)
        return 2

    dst = POSE_TEMPLATES_DIR / f"{pattern}_depth.png"
    if dst.exists():
        bak = dst.with_suffix(".png.bak")
        shutil.copy2(dst, bak)
        print(f"backed up old template → {bak.name}")

    img = Image.open(src).convert("RGB").resize((1024, 1024), Image.LANCZOS)
    depth, _ = _make_depth_map(img)
    depth = depth.resize((1024, 1024), Image.LANCZOS)
    depth.save(dst)
    print(f"[OK] new depth template written → {dst}  (from {src.name})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
