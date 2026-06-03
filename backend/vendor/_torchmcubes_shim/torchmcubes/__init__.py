"""
Drop-in replacement for the `torchmcubes` C++/CUDA extension.

Why this exists:
    The real `torchmcubes` requires CMake + nmake + a C++ compiler to build
    from source, which fails on Windows without Visual Studio Build Tools.
    TripoSR's isosurface.py does a hard `from torchmcubes import marching_cubes`
    with no fallback, so we provide one ourselves.

    This shim implements `marching_cubes(volume, threshold) -> (verts, faces)`
    using the pure-Python PyMCubes library (import name: mcubes). PyMCubes ships
    pre-built wheels on Windows, no compilation needed.

Performance:
    PyMCubes runs on CPU, so it's slower than the CUDA-accelerated original
    on very large volumes. For TripoSR's default 256³ grid, the difference
    is ~1-2 seconds per asset — completely fine for our pipeline.

Usage (automatic via sys.path):
    Insert backend/vendor/_torchmcubes_shim BEFORE backend/vendor/TripoSR in
    sys.path. Then `from torchmcubes import marching_cubes` picks up this
    module instead of failing.
"""

from __future__ import annotations

import numpy as np
import torch

try:
    import mcubes as _mcubes
except ImportError as e:
    raise ImportError(
        "torchmcubes shim requires pymcubes. Install with: pip install pymcubes"
    ) from e


def marching_cubes(volume, threshold: float = 0.0):
    """Extract a triangle mesh from a 3D scalar volume.

    Args:
        volume: torch.Tensor or numpy array of shape (D, H, W). The scalar
            field to surface-extract.
        threshold: float, the iso-value to extract.

    Returns:
        (vertices, faces) — both torch.Tensors.
            vertices: shape (N, 3), float32, grid-space coordinates
            faces:    shape (M, 3), int64, vertex indices per triangle

    Matches the signature of the real `torchmcubes.marching_cubes`.
    """
    if isinstance(volume, torch.Tensor):
        vol_np = volume.detach().cpu().numpy().astype(np.float32)
    else:
        vol_np = np.asarray(volume, dtype=np.float32)

    verts, faces = _mcubes.marching_cubes(vol_np, float(threshold))

    verts_t = torch.from_numpy(verts.astype(np.float32))
    faces_t = torch.from_numpy(faces.astype(np.int64))
    return verts_t, faces_t


# TripoSR's isosurface.py only imports `marching_cubes`, but expose any other
# symbols the real package has, just in case downstream code wants them.
__all__ = ["marching_cubes"]
