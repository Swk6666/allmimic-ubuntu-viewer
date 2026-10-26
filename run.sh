#!/usr/bin/env bash
set -euo pipefail
VIEWER_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
export PYTHONNOUSERSITE=1
export PYTHONPYCACHEPREFIX="$VIEWER_ROOT/cache/pycache"
export PYTHONPATH="$VIEWER_ROOT"
export XDG_CACHE_HOME="$VIEWER_ROOT/cache"
export TMPDIR="$VIEWER_ROOT/tmp"
mkdir -p "$TMPDIR"
cd "$VIEWER_ROOT"
exec "$VIEWER_ROOT/.venv/bin/python" play.py "$@"
