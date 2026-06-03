"""
All-in-one installer to finish InstantMesh setup.

What it does (in order):
  1. Load MSVC x64 env vars (from vcvars64.bat) into this Python process
  2. Detect CUDA 12.8 toolkit; if missing, download + install silently
  3. Set CUDA_HOME / CUDA_PATH to v12.8 (must match PyTorch)
  4. Set DISTUTILS_USE_SDK=1 so PyTorch's build skips re-activating MSVC
  5. pip install nvdiffrast (compiles from source, ~5-10 min)
  6. Download InstantMesh checkpoint
  7. Run final diagnostic

Run from inside your venv:
    .\venv\Scripts\Activate.ps1
    python scripts\finish_install.py
"""

import os
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parent.parent

VCVARS = Path("C:/Program Files (x86)/Microsoft Visual Studio/2022/BuildTools/VC/Auxiliary/Build/vcvars64.bat")
CUDA_ROOT = Path("C:/Program Files/NVIDIA GPU Computing Toolkit/CUDA")
CUDA_12_8 = CUDA_ROOT / "v12.8"
CUDA_INSTALLER_URL = "https://developer.download.nvidia.com/compute/cuda/12.8.0/network_installers/cuda_12.8.0_windows_network.exe"


def log(msg, color=None):
    """Print a section header. Color is one of: green, red, yellow, cyan."""
    codes = {"green": "32", "red": "31", "yellow": "33", "cyan": "36"}
    if color and sys.stdout.isatty():
        print(f"\033[{codes[color]}m{msg}\033[0m")
    else:
        print(msg)


def section(title):
    print()
    log("=" * 64, "cyan")
    log(f"  {title}", "cyan")
    log("=" * 64, "cyan")


def fatal(msg):
    log(f"ERROR: {msg}", "red")
    sys.exit(1)


def run(cmd, check=True, env=None, capture=False):
    """Run a subprocess command. Returns CompletedProcess."""
    if isinstance(cmd, str):
        printable = cmd
        shell = True
    else:
        printable = " ".join(str(c) for c in cmd)
        shell = False
    print(f"  $ {printable}")
    return subprocess.run(cmd, check=check, env=env, shell=shell,
                          capture_output=capture, text=capture)


def load_msvc_env():
    """Capture vcvars64.bat env vars into this Python process."""
    section("1. Load MSVC x64 environment")
    if not VCVARS.exists():
        fatal(f"VS Build Tools missing: {VCVARS}\n"
              f"  Install with: scripts\\install_vs_buildtools.ps1")
    # Run vcvars64.bat and dump env
    cmd = f'cmd.exe /c "\"{VCVARS}\" && set"'
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if result.returncode != 0:
        fatal(f"vcvars64.bat failed: {result.stderr}")
    new_count = 0
    for line in result.stdout.splitlines():
        m = re.match(r"^([^=]+)=(.*)$", line)
        if m:
            k, v = m.group(1), m.group(2)
            if os.environ.get(k) != v:
                os.environ[k] = v
                new_count += 1
    log(f"  MSVC env loaded ({new_count} vars updated)", "green")


CUDA_COMPONENTS = [
    "nvcc_12.8",
    "cudart_12.8",
    "thrust_12.8",
    "visual_studio_integration_12.8",
    # Libraries PyTorch + nvdiffrast pull in via headers (cusparse.h, cublas_v2.h, etc.)
    "cusparse_12.8",
    "cusparse_dev_12.8",
    "cublas_12.8",
    "cublas_dev_12.8",
    "cusolver_12.8",
    "cusolver_dev_12.8",
    "curand_12.8",
    "curand_dev_12.8",
    "cufft_12.8",
    "cufft_dev_12.8",
    "nvrtc_12.8",
    "nvrtc_dev_12.8",
    "nvtx_12.8",
    "cuda_profiler_api_12.8",
    "cuda_cccl_12.8",
]


def _cuda_components_complete(cuda_home: Path) -> bool:
    """Check whether key headers/libs PyTorch needs are present."""
    must_have = [
        cuda_home / "include" / "cusparse.h",
        cuda_home / "include" / "cublas_v2.h",
        cuda_home / "include" / "cusolver_common.h",
        cuda_home / "include" / "curand.h",
        cuda_home / "include" / "nvrtc.h",
        cuda_home / "bin" / "nvcc.exe",
    ]
    missing = [p for p in must_have if not p.exists()]
    if missing:
        for p in missing:
            log(f"  Missing: {p}", "yellow")
        return False
    return True


def ensure_cuda_12_8():
    """Locate CUDA 12.8, downloading + installing if missing or incomplete."""
    section("2. CUDA 12.8 toolkit (must match PyTorch's cu128 build)")
    if CUDA_12_8.exists() and _cuda_components_complete(CUDA_12_8):
        log(f"  Found (complete): {CUDA_12_8}", "green")
        return CUDA_12_8

    if CUDA_12_8.exists():
        log(f"  CUDA 12.8 present but missing components — re-running installer to add them.", "yellow")
    else:
        log(f"  Not installed. Downloading network installer...", "yellow")
    installer = Path(tempfile.gettempdir()) / "cuda_12.8_network.exe"
    if not installer.exists():
        print(f"  $ download {CUDA_INSTALLER_URL}")
        with urllib.request.urlopen(CUDA_INSTALLER_URL) as resp, open(installer, "wb") as f:
            shutil.copyfileobj(resp, f)
    print(f"  Downloaded: {installer} ({installer.stat().st_size / 1024 / 1024:.1f} MB)")

    log("  Running silent install (will take 5-10 min)...", "yellow")
    log("  ** Windows UAC will prompt for admin permission — accept it **", "yellow")
    # CUDA installer requires admin. Use PowerShell Start-Process -Verb RunAs
    # to trigger UAC and wait for the install to complete.
    install_args = "-s " + " ".join(CUDA_COMPONENTS)
    ps_cmd = (
        f"$p = Start-Process -FilePath '{installer}' "
        f"-ArgumentList '{install_args}' "
        f"-Verb RunAs -Wait -PassThru; exit $p.ExitCode"
    )
    result = subprocess.run(["powershell", "-NoProfile", "-Command", ps_cmd])
    if result.returncode != 0 or not CUDA_12_8.exists():
        fatal(f"CUDA 12.8 install failed (exit {result.returncode}). Manual download:\n  {CUDA_INSTALLER_URL}")
    if not _cuda_components_complete(CUDA_12_8):
        fatal("CUDA 12.8 installer finished but key headers still missing. "
              "Try running the installer manually with 'Custom' and selecting all CUDA libraries.")
    log(f"  Installed: {CUDA_12_8}", "green")
    return CUDA_12_8


def set_cuda_env(cuda_home):
    section("3. Configure CUDA env vars")
    os.environ["CUDA_HOME"] = str(cuda_home)
    os.environ["CUDA_PATH"] = str(cuda_home)
    os.environ["PATH"] = f"{cuda_home}\\bin;{cuda_home}\\libnvvp;{os.environ.get('PATH', '')}"
    # Verify nvcc
    nvcc = cuda_home / "bin" / "nvcc.exe"
    if not nvcc.exists():
        fatal(f"nvcc not at expected path: {nvcc}")
    result = subprocess.run([str(nvcc), "--version"], capture_output=True, text=True)
    if "Cuda compilation tools" not in result.stdout:
        log(f"  WARNING: nvcc output unexpected: {result.stdout}", "yellow")
    else:
        log("  nvcc OK", "green")


def install_nvdiffrast():
    section("4. nvdiffrast (5-10 min compile)")
    # PyTorch's build_ext wants this when VC env is already active
    os.environ["DISTUTILS_USE_SDK"] = "1"
    os.environ["CXX"] = "cl.exe"
    pip = [sys.executable, "-m", "pip", "install", "--no-build-isolation",
           "git+https://github.com/NVlabs/nvdiffrast.git"]
    result = subprocess.run(pip)
    if result.returncode != 0:
        fatal("nvdiffrast install failed. See output above.")
    # Verify
    verify = subprocess.run([sys.executable, "-c", "import nvdiffrast; print('OK')"],
                            capture_output=True, text=True)
    if verify.returncode != 0 or "OK" not in verify.stdout:
        fatal(f"nvdiffrast installed but won't import:\n{verify.stderr}")
    log("  nvdiffrast OK", "green")


def download_instantmesh_weights():
    section("5. InstantMesh weights")
    downloader = BACKEND_ROOT / "scripts" / "download_diffusion_models.py"
    result = subprocess.run([sys.executable, str(downloader), "--only", "instantmesh"])
    if result.returncode != 0:
        log("  Weights download had issues but continuing — diagnostic will confirm", "yellow")


def run_diagnostic():
    section("6. Final diagnostic")
    checker = BACKEND_ROOT / "scripts" / "check_instantmesh.py"
    result = subprocess.run([sys.executable, str(checker)])
    return result.returncode == 0


def main():
    if not os.environ.get("VIRTUAL_ENV"):
        fatal("No venv active. Run .\\venv\\Scripts\\Activate.ps1 first.")

    try:
        load_msvc_env()
        cuda_home = ensure_cuda_12_8()
        set_cuda_env(cuda_home)
        install_nvdiffrast()
        download_instantmesh_weights()
        ok = run_diagnostic()
    except KeyboardInterrupt:
        log("\nInterrupted.", "yellow")
        sys.exit(130)

    print()
    log("=" * 64, "green")
    if ok:
        log("  DONE. Run a test render:", "green")
        log("    python scripts\\render_from_prompt.py 'a brown dog' --no-render", "green")
    else:
        log("  PARTIAL. Diagnostic showed failures — check above.", "yellow")
    log("=" * 64, "green")


if __name__ == "__main__":
    main()
