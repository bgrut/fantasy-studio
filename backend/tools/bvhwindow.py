"""Find the slice of a BVH trial that actually holds the motion.

The retargeter loops inside a window of the source clip. For a walk or a run
any window works, because those are cycles. For everything else the window
has to be chosen, and choosing it by eye is how you ship a jump that samples
its own landing. This reads the motion channels and reports, per clip:

  energy      per-frame joint movement, so an idle's quiet stretch is findable
  root height the hips channel, so a jump's take-off and landing are findable

Run:  python tools/bvhwindow.py [clip.bvh ...]     (default: every clip)
"""
from __future__ import annotations

import sys
from pathlib import Path

MOCAP = Path(__file__).resolve().parent.parent / "assets" / "mocap" / "cmu"


def read_bvh(p: Path):
    txt = p.read_text(encoding="utf-8", errors="ignore").splitlines()
    i = 0
    root_chan_ofs, chan_count, yidx = None, 0, None
    while i < len(txt):
        ln = txt[i].strip()
        if ln.startswith("CHANNELS"):
            parts = ln.split()
            n = int(parts[1]); names = parts[2:2 + n]
            if root_chan_ofs is None:            # first CHANNELS = the ROOT
                root_chan_ofs = chan_count
                if "Yposition" in names:
                    yidx = chan_count + names.index("Yposition")
            chan_count += n
        if ln.startswith("MOTION"):
            break
        i += 1
    nframes, ftime = 0, 1 / 120
    while i < len(txt):
        ln = txt[i].strip()
        if ln.startswith("Frames:"):
            nframes = int(ln.split(":")[1])
        elif ln.startswith("Frame Time:"):
            ftime = float(ln.split(":")[1]); i += 1; break
        i += 1
    rows = []
    for ln in txt[i:]:
        ln = ln.strip()
        if not ln:
            continue
        try:
            rows.append([float(v) for v in ln.split()])
        except ValueError:
            continue
    return rows, ftime, yidx


def analyse(p: Path):
    rows, ftime, yidx = read_bvh(p)
    if not rows:
        print(f"{p.name}: unreadable"); return
    n = len(rows)
    energy = [0.0] * n
    for i in range(1, n):
        a, b = rows[i - 1], rows[i]
        m = min(len(a), len(b))
        energy[i] = sum(abs(a[k] - b[k]) for k in range(m)) / max(m, 1)
    ys = [r[yidx] for r in rows] if (yidx is not None and yidx < len(rows[0])) else None

    print(f"\n{p.name}: {n} frames @ {1/ftime:.0f}fps  ({n*ftime:.1f}s)")
    B = 12                                    # report in twelfths
    for bi in range(B):
        s, e = int(n * bi / B), int(n * (bi + 1) / B)
        if e <= s:
            continue
        em = sum(energy[s:e]) / (e - s)
        bar = "#" * min(28, int(em * 3))
        extra = ""
        if ys:
            seg = ys[s:e]
            extra = f"  rootY {min(seg):7.2f}..{max(seg):7.2f}"
        print(f"  {bi/B:4.2f}-{(bi+1)/B:4.2f}  energy {em:6.2f} {bar:<28}{extra}")
    if ys:
        pk = max(range(n), key=lambda k: ys[k])
        print(f"  peak rootY at frame {pk} ({pk/n:.3f} of the clip), value {ys[pk]:.2f}")
    quiet = min(range(0, max(1, n - n // 8)),
                key=lambda s: sum(energy[s:s + n // 8]))
    print(f"  quietest 1/8 window starts at {quiet/n:.3f}")


def main() -> int:
    args = sys.argv[1:]
    files = [MOCAP / a for a in args] if args else sorted(MOCAP.glob("*.bvh"))
    for f in files:
        if f.exists():
            analyse(f)
        else:
            print(f"{f.name}: missing")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
