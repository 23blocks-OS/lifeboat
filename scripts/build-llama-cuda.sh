#!/bin/bash
# Build llama.cpp with CUDA for Linux/NVIDIA (Jetson ARM64 or x86_64).
# Run by scripts/setup.sh on Linux, or directly: ./scripts/build-llama-cuda.sh
# Needs: git, cmake, a CUDA toolkit (nvcc). The first build is slow (30-60+ min
# on the Jetson); the binary in bin/ is reused afterwards. NOT run in the
# sandbox — there is no NVIDIA GPU here.
set -euo pipefail
cd "$(dirname "$0")/.."
ROOT="$PWD"
LLAMA_TAG=b12061   # keep in sync with scripts/setup.sh
say() { printf '\033[1mllama.cpp CUDA build:\033[0m %s\n' "$*"; }

[ -x bin/llama-server ] && { say "bin/llama-server already exists. Nothing to build."; exit 0; }
command -v git >/dev/null || { say "Install git first (sudo apt install git)."; exit 1; }
command -v cmake >/dev/null || { say "Install cmake first (sudo apt install cmake)."; exit 1; }
[ -x /usr/local/cuda/bin/nvcc ] && export PATH="/usr/local/cuda/bin:$PATH"
command -v nvcc >/dev/null || { say "No CUDA toolkit found (nvcc missing). Install the JetPack CUDA toolkit first."; exit 1; }

if [ ! -d build/llama.cpp ]; then
  say "Cloning llama.cpp $LLAMA_TAG..."
  mkdir -p build
  git clone --depth 1 --branch "$LLAMA_TAG" https://github.com/ggml-org/llama.cpp build/llama.cpp
fi

# JOBS caps the parallel build: a full-parallel nvcc build can run an 8 GB
# Jetson out of memory. Override with JOBS=8 on a bigger machine.
JOBS="${JOBS:-4}"
say "Configuring (GGML_CUDA=ON) and building llama-server with $JOBS jobs..."
cmake -S build/llama.cpp -B build/llama.cpp/build \
  -DGGML_CUDA=ON -DCMAKE_BUILD_TYPE=Release
cmake --build build/llama.cpp/build --target llama-server -j "$JOBS"
mkdir -p bin
cp build/llama.cpp/build/bin/llama-server bin/llama-server
say "Done: bin/llama-server"
