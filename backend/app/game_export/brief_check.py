"""Did the build make the game that was ASKED FOR?

The visual gate answers "did it render without errors". Every bug worth
fixing in the 2026-09-03 pass answered that question with a confident yes:
a red rock canyon carpeted in meadow grass rendered clean, a sailboat lying
on the seabed under seven metres of ocean rendered clean, and a prompt asking
for neon arcade art rendered clean in photoreal. Liveness is not the brief.

These checks compare FACTS reported by the running game against the spec that
asked for them. Each one exists because it already shipped broken once.
"""
from __future__ import annotations

# the ground photo each landform must be standing on — mirrors ARCH_TEX in
# the runtime. Keep the two in step: they answer the same question.
ARCH_TEX = {"canyon": "rock", "mesa": "rock", "peaks": "stone",
            "dunes": "sand", "basin": "soil", "archipelago": "sand"}


def check_brief(spec, facts: dict) -> list[str]:
    """Return human-readable complaints; empty means the build matches."""
    out: list[str] = []
    if not isinstance(facts, dict):
        return out

    arch = getattr(spec.world, "archetype", "plain") or "plain"
    mode = spec.player.mode or "walk"

    # ── the spec reached the runtime at all ──────────────────────────────
    if facts.get("archetype") not in (None, arch):
        out.append(f"landform: asked for {arch}, the game built "
                   f"{facts['archetype']}")
    if facts.get("style") not in (None, spec.style):
        out.append(f"art direction: asked for {spec.style}, the game built "
                   f"{facts['style']}")

    # ── the ground is made of what the landform says ─────────────────────
    # A canyon standing on grass.jpg is the single bug that survived three
    # fixes, because nothing ever asked the running game what it was
    # standing on.
    want = ARCH_TEX.get(arch)
    tex = facts.get("ground_tex")
    if want and tex and not tex.lower().startswith(want):
        out.append(f"ground: a {arch} should stand on {want}, the game built "
                   f"{tex}")

    # ── a hull floats, a swimmer is wet ──────────────────────────────────
    depth = facts.get("depth_below_water")
    if depth is not None:
        if facts.get("buoyant"):
            if abs(depth) > 0.6:
                out.append(f"the boat is not on the waterline: {depth:+.2f}m "
                           f"(negative is above the water, positive is under)")
        elif mode == "swim" and depth < 0:
            out.append(f"the swimmer is out of the water: {-depth:.2f}m above "
                       f"the surface")

    # ── the player is standing up ────────────────────────────────────────
    # Only walk mode is held to this: a car and a boat are legitimately wider
    # than they are tall. And within walk mode the rule SPLITS, for the same
    # reason it splits in assetmeta.py -- a biped must be TALLEST, but "play
    # as a wolf" is an ordinary prompt and a wolf is supposed to be longer
    # than it is tall. What a four-legged player must not be is flat. The
    # joint count separates them: bipeds carry ~19-20 here, quadrupeds 12.
    dims = facts.get("player_dims")
    if dims and len(dims) == 3 and mode == "walk":
        bones = facts.get("player_bones") or 0
        biped = bones >= 15 or bones == 0      # unrigged players read as biped
        tallest = max(dims) or 1e-6
        down = (dims[1] < max(dims[0], dims[2]) * 0.9 if biped
                else dims[1] / tallest < 0.35)
        if down:
            out.append(f"the player is lying down: {dims[0]:.2f} x "
                       f"{dims[1]:.2f} x {dims[2]:.2f} (w x h x d)"
                       f"{'' if biped else ' — and a quadruped that flat has fallen over'}")
    return out
