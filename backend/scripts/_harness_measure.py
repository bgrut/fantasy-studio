"""Morph metric — runs INSIDE headless Blender (quality harness, Phase 53).

Loads one animated character GLB, evaluates the skinned mesh at sampled frames
of every animation clip, and measures EDGE STRETCH: for each mesh edge,
|deformed_length - rest_length| / rest_length. Good skinning keeps local
rigidity except at joints; wrong-bone weights (the "morphing" defect) stretch
edges between verts bound to different limbs enormously — so p95 edge stretch
is the morph score. Lower = better.

Usage:
  blender --background --python _harness_measure.py -- <in.glb> <out.json>

Output JSON:
  {"ok": true, "clips": {"walk": {"p95": .., "p99": .., "max": .., "frac_gt50": ..}, ...},
   "morph_score": <max clip p95>, "verts": N, "edges": M}
"""
import sys
import json
import math

import bpy
import numpy as np


def main() -> None:
    argv = sys.argv[sys.argv.index("--") + 1:]
    glb_path, out_json = argv[0], argv[1]
    out = {"ok": False, "reason": ""}
    try:
        bpy.ops.wm.read_factory_settings(use_empty=True)
        bpy.ops.import_scene.gltf(filepath=glb_path)

        rigs = [o for o in bpy.data.objects if o.type == "ARMATURE"]
        if not rigs:
            raise RuntimeError("no armature in GLB (not an animated rig)")
        rig = rigs[0]
        meshes = [o for o in bpy.data.objects if o.type == "MESH"
                  and (o.find_armature() == rig
                       or any(m.type == "ARMATURE" and m.object == rig
                              for m in o.modifiers))]
        if not meshes:
            raise RuntimeError("no mesh bound to the armature")

        dg = bpy.context.evaluated_depsgraph_get()

        def eval_verts_edges(need_edges: bool):
            """Evaluated world-space verts (and edge index pairs on first call)
            for every bound mesh, concatenated."""
            all_v, all_e, base = [], [], 0
            for o in meshes:
                ev = o.evaluated_get(dg)
                me = ev.to_mesh()
                n = len(me.vertices)
                co = np.empty(n * 3, dtype=np.float64)
                me.vertices.foreach_get("co", co)
                co = co.reshape(n, 3)
                mw = np.array(ev.matrix_world, dtype=np.float64)
                co = co @ mw[:3, :3].T + mw[:3, 3]
                all_v.append(co)
                if need_edges:
                    m = len(me.edges)
                    ed = np.empty(m * 2, dtype=np.int64)
                    me.edges.foreach_get("vertices", ed)
                    all_e.append(ed.reshape(m, 2) + base)
                base += n
                ev.to_mesh_clear()
            V = np.concatenate(all_v, axis=0)
            E = np.concatenate(all_e, axis=0) if need_edges else None
            return V, E

        # ── rest pose: bind-state geometry + the edge list all frames share ──
        rig.data.pose_position = "REST"
        bpy.context.view_layer.update()
        dg.update()
        V0, E = eval_verts_edges(True)
        d0 = np.linalg.norm(V0[E[:, 0]] - V0[E[:, 1]], axis=1)
        good = d0 > 1e-9                      # ignore degenerate zero edges
        E, d0 = E[good], d0[good]

        # ── every imported clip: actions land in bpy.data.actions; NLA_TRACKS
        # exports come back as tracks on the rig. Evaluate each action solo. ──
        rig.data.pose_position = "POSE"
        if rig.animation_data is None:
            rig.animation_data_create()
        # unmute nothing by default — we drive via the active action slot
        for tr in rig.animation_data.nla_tracks:
            tr.mute = True

        clips = {}
        for act in bpy.data.actions:
            f0, f1 = act.frame_range
            if f1 - f0 < 2:                   # single-pose action — skip
                continue
            rig.animation_data.action = act
            try:                              # Blender 4.4+ slotted actions
                if act.slots:
                    rig.animation_data.action_slot = act.slots[0]
            except Exception:
                pass
            stretches = []
            for frac in (0.125, 0.375, 0.625, 0.875):   # mid-stride samples
                bpy.context.scene.frame_set(int(round(f0 + frac * (f1 - f0))))
                dg.update()
                V, _ = eval_verts_edges(False)
                d = np.linalg.norm(V[E[:, 0]] - V[E[:, 1]], axis=1)
                stretches.append(np.abs(d - d0) / d0)
            s = np.concatenate(stretches)
            clips[act.name] = {
                "p95": round(float(np.percentile(s, 95)), 4),
                "p99": round(float(np.percentile(s, 99)), 4),
                "max": round(float(s.max()), 4),
                "frac_gt50": round(float((s > 0.5).mean()), 5),
            }
        if not clips:
            raise RuntimeError("no multi-frame actions found in GLB")

        out = {
            "ok": True,
            "clips": clips,
            "morph_score": max(c["p95"] for c in clips.values()),
            "verts": int(V0.shape[0]),
            "edges": int(E.shape[0]),
        }
    except Exception as e:  # noqa: BLE001 — report, don't crash the harness
        out = {"ok": False, "reason": f"{type(e).__name__}: {e}"}
    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=1)
    print("[harness]", json.dumps(out)[:300])


main()
