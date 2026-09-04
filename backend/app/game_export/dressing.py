"""Shared world-dressing (Phase 26, shared-enhancement rule).

ONE prop library (assets/props/*.glb — ours, commercial-safe) and ONE
per-setting recipe, consumed by BOTH backends:
  - game:  `game_scatter()` -> ScatterSpec dicts for the web exporter
  - video: `build_video_dressing()` -> scatters the same GLBs into the Blender
    scene as background dressing, so video parks/gardens stop being bare planes.

Video placement is a RING (8..18 m) around the hero: adds depth without
walking a tree between the tracking camera and the subject. Gated FS_DRESS;
never raises — a failed dressing pass costs nothing.
"""
from __future__ import annotations

import json
import zlib
import random
from pathlib import Path

PROPS_DIR = Path(__file__).resolve().parents[2] / "assets" / "props"

# setting keyword -> [(prop, game_count, video_count), ...]
# Game counts are DENSE (quality pack: the runtime instances them — hundreds
# of props at 60fps); video counts stay Blender-shot-sized.
_RECIPES = {
    # QUALITY PACK 2: mixed tree SPECIES (oak/pine/birch + bush understory) —
    # a forest is no longer 260 copies of one tree.
    "park":        [("tree_oak", 60, 6), ("tree_birch", 35, 3), ("bush", 30, 3),
                    ("flowers", 26, 3), ("stump", 6, 1),
                    ("rock", 25, 3), ("lamp", 10, 2)],
    "garden":      [("tree_birch", 30, 4), ("bush", 36, 4), ("rock", 20, 3),
                    ("flowers", 44, 4), ("mushroom", 8, 1)],
    "forest":      [("tree_pine", 110, 8), ("tree_oak", 90, 5), ("tree_birch", 55, 3),
                    ("stump", 14, 2), ("log", 12, 2), ("mushroom", 18, 2), ("flowers", 20, 2),
                    ("bush", 50, 3), ("rock", 40, 4)],
    "meadow":      [("tree_oak", 14, 2), ("tree_birch", 14, 2), ("bush", 26, 3),
                    ("flowers", 40, 4), ("log", 5, 1),
                    ("rock", 30, 4)],
    "countryside": [("tree_oak", 40, 4), ("tree_pine", 20, 2), ("bush", 26, 3),
                    ("flowers", 22, 3), ("stump", 8, 1), ("log", 6, 1),
                    ("rock", 26, 3)],
    "field":       [("tree_oak", 14, 2), ("bush", 20, 3), ("rock", 22, 3)],
    "grass":       [("tree_oak", 26, 3), ("tree_birch", 14, 2), ("bush", 20, 2),
                    ("rock", 22, 3)],
    "backyard":    [("tree_oak", 10, 2), ("bush", 12, 2), ("rock", 8, 2), ("lamp", 4, 1)],
    "city":        [("building", 70, 8), ("lamp", 26, 4), ("tree_oak", 12, 2), ("bush", 10, 1)],
    "street":      [("building", 70, 8), ("lamp", 26, 4), ("tree_oak", 12, 2), ("bush", 10, 1)],
    "town":        [("building", 40, 6), ("lamp", 16, 3), ("tree_oak", 16, 3), ("bush", 12, 2)],
    # setting classes beyond the park family (2026-07-05): every world word the
    # extractor knows gets a recipe — no more empty sand planes
    "mountain":    [("rock", 90, 6), ("tree_pine", 80, 5), ("bush", 18, 2)],
    "alpine":      [("rock", 90, 6), ("tree_pine", 80, 5), ("bush", 18, 2)],
    "canyon":      [("rock", 110, 8), ("bush", 16, 2)],
    "desert":      [("rock", 55, 5), ("bush", 14, 2)],
    "beach":       [("rock", 30, 4), ("bush", 10, 2)],
    "swamp":       [("tree_oak", 60, 5), ("bush", 50, 4), ("rock", 20, 3)],
    "volcano":     [("rock", 120, 8)],
    "arctic":      [("rock", 60, 5), ("tree_pine", 30, 3)],
    "hills":       [("tree_oak", 40, 4), ("tree_birch", 20, 2), ("bush", 26, 3), ("rock", 30, 3)],
    # water worlds: rocky seabed / shoreline (the water plane itself is
    # rendered by the runtime from world.water_level)
    "ocean":       [("rock", 70, 5)],
    "underwater":  [("rock", 70, 5)],
    "lake":        [("rock", 40, 4), ("tree_pine", 30, 3), ("bush", 16, 2)],
    "river":       [("rock", 50, 4), ("tree_oak", 30, 3), ("bush", 20, 2)],
    # alien + built worlds (2026-07-06 breadth pass): rocks carry mars/moon
    # (tint comes from ground_color + sky palette); castle/ruins get a stone
    # yard feel — lamps read as braziers at dusk
    "mars":        [("rock", 130, 8)],
    "moon":        [("rock", 100, 7)],
    "castle":      [("castle", 1, 0), ("rock", 30, 4), ("lamp", 14, 3), ("tree_oak", 10, 2), ("bush", 12, 2)],
    "ruins":       [("rock", 80, 6), ("bush", 24, 3), ("tree_oak", 12, 2)],
    "cave":        [("rock", 140, 9)],
    "jungle":      [("tree_oak", 120, 7), ("bush", 90, 5), ("rock", 30, 3)],
}

_NO_GRASS = {"city", "street", "town", "desert", "dune", "beach", "volcano",
             "arctic", "canyon", "ocean", "underwater",
             "mars", "moon", "cave"}   # airless/barren worlds grow no grass


def wants_grass(setting: str | None, weather: str = "none") -> bool:
    s = (setting or "").lower()
    if weather == "snow":
        return False
    return not any(k in s for k in _NO_GRASS)


def recipe_for(setting: str | None):
    s = (setting or "").lower()
    for key, rec in _RECIPES.items():
        if key in s:
            return rec
    return None


# THE LANDFORM DRESSES ITSELF, AND NO TWO WORLDS THE SAME (2026-09-04).
# Two problems, one table. Recipes keyed only off the world NAME, so a gorge
# and a dune sea got the same oak/birch/bush/flowers/rock mix; and the whole
# product owned TEN nature meshes, so an identical mix of an already tiny
# library was most of why every world looked like the last one.
#
# The library is now the Kenney Nature Kit (CC0, commercial use explicit):
# 329 low-poly models — 61 trees, 56 cliffs, 60 rocks and stones, plus cactus,
# crops, tents, campfires and fences. Low-poly matters: these are scattered by
# the hundred as instances, and photoscanned props would cost the frame.
#
# Each entry is (POOL, count, video_count, scale). POOL is a list of
# interchangeable assets and the WORLD SEED picks one, so two canyons built
# from the same recipe still differ in which rock and which cliff they are
# made of. Scale is in the entry because kits are authored at their own unit
# size — a Kenney tree is 1.43 units tall, which is a shrub at our scale of 1.
_T_BROAD = ["k_tree_default", "k_tree_detailed", "k_tree_blocks", "k_tree_oak"]
_T_DARK = ["k_tree_default_dark", "k_tree_detailed_dark", "k_tree_blocks_dark"]
_T_FALL = ["k_tree_default_fall", "k_tree_detailed_fall", "k_tree_blocks_fall"]
_T_CONE = ["k_tree_cone", "k_tree_cone_dark", "k_tree_thin", "k_tree_tall"]
_ROCK_L = ["k_rock_largeA", "k_rock_largeB", "k_rock_largeC", "k_rock_largeD",
           "k_rock_largeE", "k_rock_largeF"]
_ROCK_S = ["k_rock_smallA", "k_rock_smallB", "k_rock_smallC", "k_rock_smallD"]
_STONE_L = ["k_stone_largeA", "k_stone_largeB", "k_stone_largeC", "k_stone_largeD"]
_STONE_F = ["k_stone_smallFlatA", "k_stone_smallFlatB", "k_rock_smallFlatA"]
_CLIFF_R = ["k_cliff_blockHalf_rock", "k_cliff_blockQuarter_rock",
            "k_cliff_blockDiagonal_rock", "k_cliff_blockCave_rock"]
_CLIFF_S = ["k_cliff_blockHalf_stone", "k_cliff_blockQuarter_stone",
            "k_cliff_blockDiagonal_stone"]
_BUSH = ["k_plant_bush", "k_plant_bushDetailed", "k_plant_bushLarge",
         "k_plant_bushTriangle"]
_FLOWER = ["k_flower_redA", "k_flower_purpleA", "k_flower_yellowA",
           "k_flower_redB", "k_flower_purpleC", "k_flower_yellowB"]
_GRASS = ["k_grass", "k_grass_large", "k_grass_leafs", "k_grass_leafsLarge"]
_MUSH = ["k_mushroom_red", "k_mushroom_tan", "k_mushroom_redGroup",
         "k_mushroom_tanTall"]
_STUMP = ["k_stump_old", "k_stump_oldTall", "k_stump_round", "k_stump_square"]
_LOG = ["k_log", "k_log_large", "k_log_stack"]
_CACTUS = ["k_cactus_tall", "k_cactus_short"]
_CROP = ["k_crops_cornStageD", "k_crops_wheatStageD", "k_crop_pumpkin",
         "k_crops_bambooStageB"]

_ARCH_RECIPES = {
    # a gorge is rock and dead wood — no canopy at all
    "canyon": [(_CLIFF_R, 34, 4, 6.0), (_ROCK_L, 46, 5, 2.4),
               (_ROCK_S, 40, 4, 1.6), (_STUMP, 12, 2, 2.0),
               (_CACTUS, 14, 2, 3.0)],
    # stepped stone country: flatter debris, paler stone, sparse succulents
    "mesa": [(_CLIFF_S, 30, 4, 6.0), (_STONE_L, 44, 5, 2.4),
             (_STONE_F, 36, 4, 1.6), (_CACTUS, 18, 2, 3.0)],
    # EMPTINESS IS A LOOK. A dune sea is mostly nothing, and we had never
    # once shipped a world that was allowed to be sparse.
    "dunes": [(_CACTUS, 16, 2, 3.0), (_STONE_F, 22, 3, 1.5),
              (_ROCK_S, 10, 1, 1.4)],
    # sheltered bowl: the lush one, with crops because someone farms here
    "basin": [(_T_BROAD, 26, 3, 4.5), (_BUSH, 40, 4, 2.2),
              (_FLOWER, 44, 4, 1.7), (_CROP, 20, 2, 2.2),
              (_MUSH, 16, 2, 1.6), (_ROCK_S, 18, 2, 1.5)],
    # alpine: conifers and boulders, and it gets DARKER trees
    "peaks": [(_T_CONE, 80, 7, 4.8), (_ROCK_L, 50, 5, 2.4),
              (_STONE_L, 34, 4, 2.2), (_STUMP, 12, 2, 2.0),
              (_LOG, 10, 1, 2.2)],
    # islands: low scrub and shore stone, few trees
    "archipelago": [(_T_BROAD, 18, 3, 4.2), (_BUSH, 30, 3, 2.2),
                    (_STONE_F, 34, 4, 1.6), (_GRASS, 30, 3, 2.2)],
    # the default: a mixed wood-edge meadow, seasonally variable
    "plain": [(_T_BROAD + _T_DARK + _T_FALL, 30, 4, 4.5), (_BUSH, 34, 4, 2.2),
              (_FLOWER, 40, 4, 1.7), (_GRASS, 26, 3, 2.2),
              (_MUSH, 12, 2, 1.6), (_ROCK_S, 22, 3, 1.5),
              (_LOG, 6, 1, 2.2)],
}


def game_scatter(setting: str | None, archetype: str | None = None,
                 seed: int = 0) -> list[dict]:
    """ScatterSpec dicts for GameSpec.world.scatter (empty if no recipe/props).

    A named landform outranks the setting keyword: "plain" keeps the old
    name-driven recipes, everything else dresses to its own ground.
    """
    rec = _ARCH_RECIPES.get((archetype or "plain").lower())
    if rec is None:
        legacy = recipe_for(setting)
        if not legacy:
            return []
        rec = [(p, n, v, 1.0) for p, n, v in legacy]
    rnd = random.Random(seed)
    out = []
    for entry in rec:
        pool, game_n, _v, scale = entry
        names = pool if isinstance(pool, list) else [pool]
        # the SEED decides which member of the pool this world is made of, so
        # two canyons off the same recipe are still different canyons
        pick = rnd.choice(names)
        glb = PROPS_DIR / f"{pick}.glb"
        if not glb.exists():
            cand = [n for n in names if (PROPS_DIR / f"{n}.glb").exists()]
            if not cand:
                continue
            pick = rnd.choice(cand)
            glb = PROPS_DIR / f"{pick}.glb"
        out.append({"asset": str(glb), "count": game_n,
                    "min_dist_m": 5.0, "scale_jitter": 0.3,
                    "scale": float(scale),
                    "collide": not pick.startswith(("k_flower", "k_grass",
                                                    "k_mushroom", "k_rock_small",
                                                    "k_stone_smallFlat"))})
    return out


_VIDEO_DRESS_CODE = r'''
import bpy, json, math, random
RECIPE=__RECIPE__; SEED=__SEED__; FIREFLIES=__FIREFLIES__
random.seed(SEED)
placed=0; kinds=[]
# night-scene atmosphere: tiny emissive motes hovering in the mid-ground —
# the video sibling of the game's glowing collectibles (shared-enhancement rule)
if FIREFLIES:
    fm=bpy.data.materials.new("FireflyMat"); fm.use_nodes=True
    _b=fm.node_tree.nodes.get("Principled BSDF")
    try:
        _b.inputs["Emission Color"].default_value=(1.0,0.85,0.35,1.0)
        _b.inputs["Emission Strength"].default_value=30.0
    except Exception: pass
    for i in range(FIREFLIES):
        ang=random.uniform(0,2*math.pi); dist=random.uniform(3.0,14.0)
        bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=1, radius=0.03,
            location=(math.cos(ang)*dist, math.sin(ang)*dist, random.uniform(0.8,2.4)))
        bpy.context.object.data.materials.append(fm)
        placed+=1
    kinds.append("fireflies:%d"%FIREFLIES)
for glb, count in RECIPE:
    pre=set(bpy.data.objects.keys())
    try:
        bpy.ops.import_scene.gltf(filepath=glb)
    except Exception:
        continue
    new=[bpy.data.objects[k] for k in bpy.data.objects.keys() if k not in pre]
    meshes=[o for o in new if o.type=="MESH"]
    if not meshes: continue
    # group the prop under one empty so we can duplicate it as a unit
    root=bpy.data.objects.new("PropRoot", None)
    bpy.context.scene.collection.objects.link(root)
    for o in meshes:
        o.parent=root
    def place(obj, ang, dist, s):
        obj.location=(math.cos(ang)*dist, math.sin(ang)*dist, 0.0)
        obj.rotation_euler=(0,0,random.uniform(0,6.283))
        obj.scale=(s,s,s)
    # TALL props (trees/lamps) go to a FAR ring (11-20m): tracking cameras sit
    # 4-8m from the hero, so nothing tall can end up at/behind the lens. LOW
    # props (rocks) may come closer (8-16m) — they can't block the frame.
    tall=("tree" in glb) or ("lamp" in glb)
    lo_d, hi_d = (11.0, 20.0) if tall else (8.0, 16.0)
    for i in range(count):
        ang=random.uniform(0,2*math.pi)
        dist=random.uniform(lo_d, hi_d)
        s=random.uniform(0.8,1.35)
        if i==0:
            place(root, ang, dist, s)
        else:
            dup=root.copy()
            bpy.context.scene.collection.objects.link(dup)
            for ch in root.children:
                c=ch.copy(); c.parent=dup      # linked mesh data — cheap instances
                bpy.context.scene.collection.objects.link(c)
            place(dup, ang, dist, s)
        placed+=1
    kinds.append(glb.split("/")[-1])
# Phase 32 flow-back: ONE oversized LANDMARK of the first prop kind — the
# video sibling of the game's scenic landmarks (same design language).
if RECIPE:
    glb0=RECIPE[0][0]
    root0=[o for o in bpy.data.objects if o.name.startswith("PropRoot")]
    if root0:
        lm=root0[0].copy(); bpy.context.scene.collection.objects.link(lm)
        for ch in root0[0].children:
            c=ch.copy(); c.parent=lm; bpy.context.scene.collection.objects.link(c)
        ang=random.uniform(0,2*math.pi); dist=random.uniform(14.0,18.0)
        s=random.uniform(2.2,2.8)
        lm.location=(math.cos(ang)*dist, math.sin(ang)*dist, 0.0)
        lm.scale=(s,s,s); lm.rotation_euler=(0,0,random.uniform(0,6.283))
        placed+=1; kinds.append("landmark")
bpy.context.view_layer.update()
__result__=json.dumps({"ok":True,"placed":placed,"kinds":kinds})
'''


def build_video_dressing(runner, setting: str | None, seed_key: str = "0",
                         mood: str = "", verbose: bool = False) -> bool:
    """Scatter the shared props into the CURRENT Blender scene (video side).
    Night moods over nature settings also get ambient fireflies. Returns True
    if anything was placed; never raises."""
    import os
    if os.environ.get("FS_DRESS", "1") == "0":
        return False
    rec = recipe_for(setting)
    if not rec:
        return False
    pairs = []
    for prop, _, video_n in rec:
        glb = PROPS_DIR / f"{prop}.glb"
        if glb.exists() and video_n > 0:
            pairs.append([str(glb).replace("\\", "/"), video_n])
    if not pairs:
        return False
    m = (mood or "").lower() + " " + (setting or "").lower()
    fireflies = 14 if any(w in m for w in ("night", "moonlight", "dusk", "twilight")) else 0
    seed = zlib.crc32(str(seed_key).encode()) % 100000
    try:
        code = (_VIDEO_DRESS_CODE
                .replace("__RECIPE__", json.dumps(pairs))
                .replace("__SEED__", str(seed))
                .replace("__FIREFLIES__", str(fireflies)))
        res = runner.run("dressing", "execute_python", {"code": code}, critical=False)
        raw = res.get("result") if isinstance(res, dict) else None
        info = json.loads(raw) if isinstance(raw, str) else (raw if isinstance(raw, dict) else None)
        ok = bool(info and info.get("ok") and info.get("placed"))
        if verbose and ok:
            print(f"[composer] dressing: {info.get('placed')} props "
                  f"({', '.join(info.get('kinds', []))}) for '{setting}'")
        return ok
    except Exception as e:
        if verbose:
            print(f"[composer] dressing skipped ({type(e).__name__}: {e})")
        return False
