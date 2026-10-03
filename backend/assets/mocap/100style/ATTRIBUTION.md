# 100STYLE motion: attribution and licence

The `.bvh` files in this directory are taken unmodified from the **100STYLE
dataset** by Ian Mason, Sebastian Starke and Taku Komura (University of
Edinburgh), published at https://www.ianxmason.com/100style/ and archived on
Zenodo (record 8127870, doi:10.5281/zenodo.8127870).

Licence: **Creative Commons Attribution 4.0 International (CC BY 4.0)**,
https://creativecommons.org/licenses/by/4.0/. Commercial use is allowed with
credit. Every exported game carries the credit line in its LICENSES.md (see
`app/game_export/web_exporter.py`), with a note that the motion was retargeted
and trimmed.

Only the curated takes live here; the full 1.5 GB download stays in
`../_100style_src/` (ignored by git).

| File | Take | Used for |
|---|---|---|
| Neutral_ID.bvh | Neutral style, standing idle (60 fps) | `idle`, window 0.30-0.72 (the still standing stretch, measured: knees 2 deg, trunk 1 deg) |

Capture notes: Xsens suit, 60 fps, Y up, centimetres. Joint names are
Hips, Chest..Chest4, Neck, Head, Left/RightCollar, Left/RightShoulder (upper
arm), Left/RightElbow (forearm), Left/RightWrist, Left/RightHip (thigh),
Left/RightKnee, Left/RightAnkle, Left/RightToe; `retarget_rot.py` maps them.
