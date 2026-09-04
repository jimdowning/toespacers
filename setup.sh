#!/usr/bin/env bash
# One-time setup: creates a local venv with everything generate.py needs.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"

python3 -m venv venv
./venv/bin/pip install -q -r requirements.txt

# build123d (via its OCP/OCCT backend) needs libGL at runtime. On a minimal
# Linux install (WSL, a container, a headless box) this is often missing;
# `run.sh` below points LD_LIBRARY_PATH at Homebrew's copy if you have one.
if ! ldconfig -p 2>/dev/null | grep -q libGL.so.1 && [ ! -e /home/linuxbrew/.linuxbrew/lib/libGL.so.1 ]; then
  if command -v brew >/dev/null; then
    echo "Installing mesa (provides libGL) via brew..."
    brew install mesa
  else
    echo "NOTE: libGL.so.1 not found and no brew available. If generate.py"
    echo "fails with an OCP/libGL import error, install a Mesa/OpenGL"
    echo "runtime package for your distro (e.g. 'sudo apt install libgl1')."
  fi
fi

echo "Setup complete. Use ./run.sh generate.py config.json output to build the model."
