from __future__ import annotations

"""
camera_motion.py
================
Reusable camera motion helpers.

These are *standalone* functions that can be applied to any camera object.
They do NOT create the camera -- they animate an existing one.

Usage:
    from ..scene.camera_motion import orbit_camera, push_in_camera, subtle_handheld_noise

    orbit_camera(cam, center=(0, 5, 0.75), radius=6.0, ...)
    push_in_camera(cam, ...)
    subtle_handheld_noise(cam, ...)
"""

from math import radians, sin, cos, pi


def orbit_camera(
    cam,
    center: tuple = (0, 0, 0),
    radius: float = 6.0,
    start_angle_deg: float = -90,
    sweep_deg: float = 45,
    height: float = 1.5,
    height_delta: float = -0.15,
    frame_start: int = 1,
    frame_end: int = 240,
) -> None:
    """
    Animate camera in a partial orbit arc around ``center``.

    Parameters
    ----------
    center          World-space point the orbit circles around.
    radius          Distance from center.
    start_angle_deg Starting angle (0 = +X axis, 90 = +Y axis).
    sweep_deg       How many degrees to sweep over the animation.
    height          Camera Z at frame_start.
    height_delta    Change in camera Z over the animation (negative = dip).
    """
    cx, cy, cz = center
    a0 = radians(start_angle_deg)
    a1 = radians(start_angle_deg + sweep_deg)

    # Frame 1 position
    cam.location = (
        cx + radius * cos(a0),
        cy + radius * sin(a0),
        cz + height,
    )
    cam.keyframe_insert(data_path="location", frame=frame_start)

    # Frame end position
    cam.location = (
        cx + radius * cos(a1),
        cy + radius * sin(a1),
        cz + height + height_delta,
    )
    cam.keyframe_insert(data_path="location", frame=frame_end)

    # Reset to start for frame 1
    cam.location = (
        cx + radius * cos(a0),
        cy + radius * sin(a0),
        cz + height,
    )


def push_in_camera(
    cam,
    dx: float = 0.0,
    dy: float = 3.0,
    dz: float = -0.2,
    frame_start: int = 1,
    frame_end: int = 240,
) -> None:
    """
    Simple linear push-in from camera's current position.
    dx/dy/dz are added to the current location at frame_end.
    """
    start = cam.location.copy()
    cam.keyframe_insert(data_path="location", frame=frame_start)
    cam.location = (start.x + dx, start.y + dy, start.z + dz)
    cam.keyframe_insert(data_path="location", frame=frame_end)
    cam.location = start  # reset for frame 1


def crane_up_camera(
    cam,
    dz: float = 1.5,
    dy: float = 2.0,
    frame_start: int = 1,
    frame_end: int = 240,
) -> None:
    """
    Crane move: camera lifts up while optionally pushing forward.
    Creates a reveal-from-below effect.
    """
    start = cam.location.copy()
    cam.keyframe_insert(data_path="location", frame=frame_start)
    cam.location = (start.x, start.y + dy, start.z + dz)
    cam.keyframe_insert(data_path="location", frame=frame_end)
    cam.location = start


def subtle_handheld_noise(
    cam,
    amplitude: float = 0.015,
    frequency: float = 2.5,
    frame_start: int = 1,
    frame_end: int = 240,
    fps: int = 24,
) -> None:
    """
    Add subtle handheld-style noise to camera position via keyframes.

    Uses sine waves at different frequencies per axis to simulate organic
    camera sway.  The amplitude is deliberately very small -- this is
    *perceived* handheld, not shaky-cam.

    NOTE: This should be called AFTER the main camera motion is set up,
    as it adds keyframes at regular intervals that blend with existing
    motion.
    """
    try:
        base = cam.location.copy()
        step = max(1, fps // 6)  # ~4 keyframes per second

        for frame in range(frame_start, frame_end + 1, step):
            t = (frame - frame_start) / max(1, fps)
            # Different frequency per axis for organic feel
            nx = amplitude * sin(2 * pi * frequency * t * 1.0)
            ny = amplitude * sin(2 * pi * frequency * t * 0.7 + 1.3)
            nz = amplitude * sin(2 * pi * frequency * t * 1.3 + 2.7) * 0.6

            cam.location = (base.x + nx, base.y + ny, base.z + nz)
            cam.keyframe_insert(data_path="location", frame=frame)

        # Ensure we end where we started (smooth loop)
        cam.location = base
        cam.keyframe_insert(data_path="location", frame=frame_end)
        cam.location = base

        print(f"[CAMERA] handheld noise applied | amp={amplitude} freq={frequency}", flush=True)
    except Exception as e:
        print(f"[CAMERA] handheld noise failed: {e}", flush=True)
