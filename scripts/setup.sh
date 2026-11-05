#!/bin/bash
# One-time setup. Needs internet. Installs llama.cpp, a private Python, and the saved wheels,
# then makes the data folder and your region file. Safe to re-run.
# Usage: ./lifeboat setup [data-dir]     data-dir: where archives and extra models go (default: ./data)
set -euo pipefail
cd "$(dirname "$0")/.."
ROOT="$PWD"
LLAMA_TAG=b12061
say() { printf '\033[1mLifeboat setup:\033[0m %s\n' "$*"; }

# Platform: one portable main. Mac runs the Metal binary, Linux/NVIDIA builds
# llama.cpp from source with CUDA (scripts/build-llama-cuda.sh).
PLATFORM="$(uname -s)-$(uname -m)"
case "$PLATFORM" in
  Darwin-arm64) ;;
  Linux-aarch64|Linux-x86_64) ;;
  *) say "Lifeboat runs on an Apple Silicon Mac or Linux with NVIDIA (Jetson / x86). This machine is $PLATFORM."; exit 1 ;;
esac

if [ "${PLATFORM%%-*}" = "Darwin" ]; then
  command -v uv >/dev/null || { say "Install uv first: brew install uv"; exit 1; }
else
  command -v uv >/dev/null || { say "Install uv first: curl -LsSf https://astral.sh/uv/install.sh | sh"; exit 1; }
fi

# 1. llama.cpp (pinned release)
if [ ! -x bin/llama-server ]; then
  if [ "${PLATFORM%%-*}" = "Darwin" ]; then
    say "Downloading llama.cpp $LLAMA_TAG (macOS Metal build)..."
    mkdir -p bin/llama
    curl -fL --progress-bar -o bin/llama.tgz \
      "https://github.com/ggml-org/llama.cpp/releases/download/$LLAMA_TAG/llama-$LLAMA_TAG-bin-macos-arm64.tar.gz"
    tar -xzf bin/llama.tgz -C bin/llama && rm bin/llama.tgz
    xattr -dr com.apple.quarantine bin/llama 2>/dev/null || true
    ln -sf "llama/llama-$LLAMA_TAG/llama-server" bin/llama-server
  else
    say "Building llama.cpp $LLAMA_TAG with CUDA (slow first build, then reused)..."
    scripts/build-llama-cuda.sh
  fi
fi

# 2. Python 3.12 inside the project, and wheels saved so ./lifeboat can rebuild the venv offline
say "Installing Python 3.12 and packages..."
uv python install 3.12 --install-dir runtime/python --no-bin
BASE=$(ls -d runtime/python/cpython-3.12*/bin/python3.12 | head -1)
[ -x .venv/bin/python ] || "$BASE" -m venv .venv
mkdir -p vendor/wheels
.venv/bin/python -m pip download -q -d vendor/wheels -r requirements.txt
.venv/bin/python -m pip install -q --no-index --find-links vendor/wheels -r requirements.txt

# 3. Folders. 'data' can point at an external drive to keep the internal disk free.
if [ ! -e data ]; then
  if [ -n "${1:-}" ]; then mkdir -p "$1"; ln -s "$1" data; else mkdir data; fi
fi
mkdir -p data/library/zim data/library/pdf data/models models index logs print
[ -e library ] || ln -s data/library library

# 4. Region
if [ ! -f region.json ]; then
  cp regions/los-angeles.json region.json
  say "Wrote region.json from the Los Angeles example. Edit it for your area (see regions/README.md)."
fi

if [ "${PLATFORM%%-*}" = "Darwin" ]; then
  command -v aria2c >/dev/null || say "Tip: 'brew install aria2' makes archive downloads much faster."
else
  command -v aria2c >/dev/null || say "Tip: 'sudo apt install aria2' makes archive downloads much faster."
fi
say "Done. Next: ./lifeboat fetch   then ./lifeboat index   then ./lifeboat start"
