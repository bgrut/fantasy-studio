"""
Tools package — every tool registers itself with the registry on import.

To add a new tool: create a new module under tools/, define handlers,
call registry.register_fn(...) at module top-level. Then add your
module to the imports below.
"""


def register_all_tools() -> None:
    """Idempotent — import every tools module so they register themselves."""
    # Order doesn't matter, but grouped by phase for readability:

    # Phase 1: wrap existing backend ops
    from . import scene_state  # noqa: F401
    from . import assets  # noqa: F401
    from . import asset_io  # noqa: F401  (Phase 17 import/save)
    from . import camera  # noqa: F401
    from . import lighting  # noqa: F401
    from . import materials  # noqa: F401

    # Phase 2: generative gap fillers
    from . import primitives  # noqa: F401
    from . import modifiers  # noqa: F401
    from . import animation  # noqa: F401
    from . import render  # noqa: F401

    # Phase 7: video output (ffmpeg wrap)
    from . import video  # noqa: F401

    # Phase 3: templates
    from . import templates  # noqa: F401

    # Phase 4: verifier loop
    from . import verify  # noqa: F401

    # Escape hatch
    from . import execute  # noqa: F401
