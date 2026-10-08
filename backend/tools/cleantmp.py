"""Clear the headless-browser profiles the shot tools leave in %TEMP%.

    python backend/tools/cleantmp.py            # profiles older than an hour
    python backend/tools/cleantmp.py --all      # every one not in use

Puppeteer makes a fresh Chrome profile for every run and removes it when the
browser closes cleanly; a run that is killed or times out leaves it behind,
about 56 MB each. On 2026-10-07 768 of them (43 GB) filled the disk mid-session
and every tool failed at once. The gate runs this at its start.
"""
import os, shutil, sys, tempfile, time
cut = 0 if "--all" in sys.argv else time.time() - 3600
root = tempfile.gettempdir()
n = freed = 0
for d in os.listdir(root):
    if not d.startswith("puppeteer_dev_chrome_profile-"):
        continue
    p = os.path.join(root, d)
    try:
        if os.path.getmtime(p) > cut:
            continue
        size = sum(os.path.getsize(os.path.join(a, f)) for a, _, fs in os.walk(p) for f in fs)
        shutil.rmtree(p)
        n += 1; freed += size
    except Exception:
        pass                                   # in use: a browser still has it open
print(f"cleantmp: removed {n} browser profiles, {freed / 1e9:.1f} GB")
