@echo off
call "C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools\VC\Auxiliary\Build\vcvars64.bat"
set CUDA_HOME=C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v12.8
set PATH=%CUDA_HOME%\bin;%PATH%
set TORCH_CUDA_ARCH_LIST=12.0
set DISTUTILS_USE_SDK=1
set B=C:\Users\bgrut\Desktop\FantasyAI\fantasy-studio\backend
set PY=%B%\venv_trellis\Scripts\python.exe
echo === basic deps ===
%PY% -m pip install -q imageio imageio-ffmpeg tqdm easydict opencv-python-headless ninja trimesh transformers pandas lpips zstandard kornia timm rembg onnxruntime
%PY% -m pip install -q "git+https://github.com/EasternJournalist/utils3d.git@9a4eb15e4021b67b12c460c7057d642626897ec8"
echo === nvdiffrast ===
%PY% -m pip install "%B%\vendor\_trellis_ext\nvdiffrast" --no-build-isolation
echo === CuMesh ===
%PY% -m pip install "%B%\vendor\_trellis_ext\CuMesh" --no-build-isolation
echo === FlexGEMM ===
%PY% -m pip install "%B%\vendor\_trellis_ext\FlexGEMM" --no-build-isolation
echo === o-voxel ===
%PY% -m pip install "%B%\vendor\TRELLIS.2\o-voxel" --no-build-isolation
echo === verify ===
%PY% -c "import nvdiffrast, o_voxel; print('EXT OK')"
