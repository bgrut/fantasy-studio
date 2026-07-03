@echo off
call "C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools\VC\Auxiliary\Build\vcvars64.bat"
set CUDA_HOME=C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v12.8
set PATH=%CUDA_HOME%\bin;%PATH%
set TORCH_CUDA_ARCH_LIST=12.0
set DISTUTILS_USE_SDK=1
set B=C:\Users\bgrut\Desktop\FantasyAI\fantasy-studio\backend
set PY=%B%\venv_trellis\Scripts\python.exe
echo === FlexGEMM (patched) ===
%PY% -m pip install "%B%\vendor\_trellis_ext\FlexGEMM" --no-build-isolation
echo === o-voxel (patched) ===
%PY% -m pip install "%B%\vendor\TRELLIS.2\o-voxel" --no-build-isolation
echo === verify ===
%PY% -c "import nvdiffrast, cumesh, flex_gemm, o_voxel; print('ALL EXT OK')"
