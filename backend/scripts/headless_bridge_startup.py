"""
Headless bridge startup — runs INSIDE Blender via:

    blender --background --python scripts/headless_bridge_startup.py

What it does:
    1. Enables the fantasy_studio_bridge addon (which auto-starts the socket server)
    2. Drives the main-thread op queue drain in a manual loop, because in
       --background mode Blender has no UI event loop and bpy.app.timers
       may not fire reliably.
    3. Blocks until Ctrl-C, keeping Blender alive to receive bridge ops.

After running this, point the orchestrator at 127.0.0.1:9876 just like
interactive mode — same protocol, same handlers.
"""

import sys
import os
import time


def main():
    print("[headless_bridge] starting…")

    # Force autostart on (the addon checks this env var)
    os.environ["FANTASY_STUDIO_BRIDGE_AUTOSTART"] = "1"

    # Allow port override from env
    port = int(os.environ.get("FANTASY_STUDIO_BRIDGE_PORT", "9876"))

    import addon_utils
    import bpy  # noqa: F401

    # Enable the addon. This triggers register() which starts the socket server.
    addon_name = "fantasy_studio_bridge"
    try:
        addon_utils.enable(addon_name, default_set=True, persistent=True)
        print(f"[headless_bridge] addon '{addon_name}' enabled")
    except Exception as e:
        print(f"[headless_bridge] FAILED to enable addon: {e}")
        print(f"[headless_bridge] is it installed under <blender>/scripts/addons/?")
        sys.exit(1)

    # Import the bridge_server module so we can manually drive the drain
    from fantasy_studio_bridge import bridge_server  # type: ignore

    print(f"[headless_bridge] listening on 127.0.0.1:{port}")
    print(f"[headless_bridge] Ctrl-C to shut down")

    # In --background mode, bpy.app.timers may not fire. Drive the drain loop
    # manually at ~30 Hz from the main thread.
    try:
        while True:
            bridge_server._drain_op_queue()
            time.sleep(0.033)
    except KeyboardInterrupt:
        print("\n[headless_bridge] shutting down…")
        bridge_server.stop()
        print("[headless_bridge] stopped cleanly")


if __name__ == "__main__":
    main()
