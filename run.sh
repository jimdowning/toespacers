#!/usr/bin/env bash
# Runs any script in this project's venv with LD_LIBRARY_PATH set so
# build123d's OCCT backend can find libGL. Usage: ./run.sh generate.py ...
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"

EXTRA_LIB=""
[ -d /home/linuxbrew/.linuxbrew/lib ] && EXTRA_LIB=/home/linuxbrew/.linuxbrew/lib

LD_LIBRARY_PATH="${EXTRA_LIB}${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}" ./venv/bin/python "$@"
