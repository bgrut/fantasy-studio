"""
Fantasy Studio Bridge — Blender addon

Long-lived socket server inside Blender. Accepts JSON-encoded ops from the
Studio orchestrator (Python side, runs out-of-process), dispatches them to
bpy, returns structured results.

Architecture mirrors blender-mcp (Siddharth Ahuja): TCP socket, length-
prefixed JSON, dispatcher table. The difference: this addon's command set
is curated for Fantasy Studio's pipeline (asset library, templates,
HERO_VERIFY) rather than generic Blender ops.

Install:
    1. Copy this folder to <blender-user-scripts>/addons/fantasy_studio_bridge/
       (or symlink during dev), OR set BLENDER_USER_SCRIPTS env var to
       fantasy-studio/backend/blender_addons/ and Blender finds it.
    2. Edit > Preferences > Add-ons > enable "Fantasy Studio Bridge"
    3. Bridge auto-starts on enable; status visible in N-panel > Studio.

Protocol:
    Each TCP message = 4-byte big-endian length prefix + UTF-8 JSON payload.

    Request:  {"id": "<uuid>", "op": "<op_name>", "params": {...}}
    Response: {"id": "<uuid>", "ok": true,  "result": <any>}
              {"id": "<uuid>", "ok": false, "error": "<msg>", "trace": "..."}

Port: 9876 (override via FANTASY_STUDIO_BRIDGE_PORT env var)
Host: 127.0.0.1 only — never bind public.
"""

bl_info = {
    "name": "Fantasy Studio Bridge",
    "author": "FantasyLab.ai",
    "version": (0, 1, 0),
    "blender": (3, 0, 0),
    "location": "View3D > Sidebar > Studio",
    "description": "Socket bridge exposing curated bpy ops to the Studio orchestrator.",
    "category": "Development",
}

import bpy
from bpy.props import IntProperty, BoolProperty, StringProperty
from . import bridge_server


# ───────────────────────────────────────────────────────────────────────
# Operators — start/stop the bridge
# ───────────────────────────────────────────────────────────────────────

class STUDIO_OT_bridge_start(bpy.types.Operator):
    bl_idname = "studio.bridge_start"
    bl_label = "Start Bridge"
    bl_description = "Start the Studio socket bridge"

    def execute(self, context):
        port = context.scene.studio_bridge_port
        ok, msg = bridge_server.start(port=port)
        if ok:
            context.scene.studio_bridge_running = True
            self.report({'INFO'}, f"Studio bridge listening on 127.0.0.1:{port}")
        else:
            self.report({'ERROR'}, f"Bridge failed to start: {msg}")
        return {'FINISHED'}


class STUDIO_OT_bridge_stop(bpy.types.Operator):
    bl_idname = "studio.bridge_stop"
    bl_label = "Stop Bridge"
    bl_description = "Stop the Studio socket bridge"

    def execute(self, context):
        bridge_server.stop()
        context.scene.studio_bridge_running = False
        self.report({'INFO'}, "Studio bridge stopped")
        return {'FINISHED'}


# ───────────────────────────────────────────────────────────────────────
# N-panel UI — minimal status + manual start/stop
# ───────────────────────────────────────────────────────────────────────

class STUDIO_PT_bridge_panel(bpy.types.Panel):
    bl_label = "Studio Bridge"
    bl_idname = "STUDIO_PT_bridge"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Studio"

    def draw(self, context):
        layout = self.layout
        scene = context.scene

        row = layout.row()
        row.prop(scene, "studio_bridge_port", text="Port")

        row = layout.row()
        if scene.studio_bridge_running:
            row.label(text="● Running", icon='REC')
            layout.operator("studio.bridge_stop", icon='PAUSE')
        else:
            row.label(text="○ Stopped", icon='RADIOBUT_OFF')
            layout.operator("studio.bridge_start", icon='PLAY')

        layout.separator()
        layout.label(text="Connects to:", icon='URL')
        box = layout.box()
        box.label(text=f"127.0.0.1:{scene.studio_bridge_port}")
        box.label(text="(localhost only)")


# ───────────────────────────────────────────────────────────────────────
# Registration
# ───────────────────────────────────────────────────────────────────────

CLASSES = (
    STUDIO_OT_bridge_start,
    STUDIO_OT_bridge_stop,
    STUDIO_PT_bridge_panel,
)


def register():
    bpy.types.Scene.studio_bridge_port = IntProperty(
        name="Port",
        default=9876,
        min=1024,
        max=65535,
    )
    bpy.types.Scene.studio_bridge_running = BoolProperty(
        name="Bridge Running",
        default=False,
    )
    for cls in CLASSES:
        bpy.utils.register_class(cls)

    # Auto-start unless user disabled via env var
    import os
    if os.environ.get("FANTASY_STUDIO_BRIDGE_AUTOSTART", "1") == "1":
        port = int(os.environ.get("FANTASY_STUDIO_BRIDGE_PORT", "9876"))
        ok, msg = bridge_server.start(port=port)
        if ok:
            print(f"[studio_bridge] Auto-started on 127.0.0.1:{port}")
        else:
            print(f"[studio_bridge] Auto-start FAILED: {msg}")


def unregister():
    bridge_server.stop()
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
    del bpy.types.Scene.studio_bridge_port
    del bpy.types.Scene.studio_bridge_running


if __name__ == "__main__":
    register()
