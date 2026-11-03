#!/bin/bash
# One-time setup. Needs internet. Installs llama.cpp, a private Python, and the saved wheels,
# then makes the data folder and your region file. Safe to re-run.
# Usage: ./lifeboat setup [data-dir]     data-dir: where archives and extra models go (default: ./data)
set -euo pipefail
cd "$(dirname "$0")/.."
ROOT="$PWD"
LLAMA_TAG=b12061
say() { printf '\033[1mLifeboat setup:\033[0m %s\n' "$*"; }

[ "$(uname -s)-$(uname -m)" = "Darwin-arm64" ] || { say "Lifeboat needs an Apple Silicon Mac."; exit 1; }
command -v uv >/dev/null || { say "Install uv first: brew install uv"; exit 1; }

# 1. llama.cpp (pinned release, Metal build)
if [ ! -x bin/llama-server ]; then
  say "Downloading llama.cpp $LLAMA_TAG..."
  mkdir -p bin/llama
  curl -fL --progress-bar -o bin/llama.tgz \
    "https://github.com/ggml-org/llama.cpp/releases/download/$LLAMA_TAG/llama-$LLAMA_TAG-bin-macos-arm64.tar.gz"
  tar -xzf bin/llama.tgz -C bin/llama && rm bin/llama.tgz
  xattr -dr com.apple.quarantine bin/llama 2>/dev/null || true
  ln -sf "llama/llama-$LLAMA_TAG/llama-server" bin/llama-server
fi

# 2. Python 3.12 inside the project, and wheels saved so ./lifeboat can rebuild the venv offline
say "Installing Python 3.12 and packages..."
uv python install 3.12 --install-dir runtime/python
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

command -v aria2c >/dev/null || say "Tip: 'brew install aria2' makes archive downloads much faster."
say "Done. Next: ./lifeboat fetch   then ./lifeboat index   then ./lifeboat start"
