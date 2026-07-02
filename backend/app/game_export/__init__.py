"""Phase 26 — game export.

Second output backend beside the video composer: the same scene/asset IR is
emitted as a PLAYABLE game (three.js web build first; Godot later). See
docs/game_engine_plan.md. Feature-gated FS_GAME. No composer.py edits — the
video pipeline cannot regress through this package.
"""
