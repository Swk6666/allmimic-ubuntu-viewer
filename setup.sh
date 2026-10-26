#!/usr/bin/env bash
set -euo pipefail
VIEWER_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
cd "$VIEWER_ROOT"
export TMPDIR="$VIEWER_ROOT/tmp"
export UV_CACHE_DIR="${UV_CACHE_DIR:-$VIEWER_ROOT/cache/uv}"
export UV_PYTHON_INSTALL_DIR="$VIEWER_ROOT/runtime/python"
export UV_PYTHON_BIN_DIR="$VIEWER_ROOT/runtime/bin"
export XDG_CACHE_HOME="$VIEWER_ROOT/cache"
export XDG_CONFIG_HOME="$VIEWER_ROOT/config"
export XDG_DATA_HOME="$VIEWER_ROOT/share"
export XDG_STATE_HOME="$VIEWER_ROOT/state"
export PYTHONPYCACHEPREFIX="$VIEWER_ROOT/cache/pycache"
export PYTHONNOUSERSITE=1
mkdir -p "$TMPDIR" "$VIEWER_ROOT/runtime/bin"
if [[ ! -x "$VIEWER_ROOT/runtime/bin/uv" ]]; then
    if command -v curl >/dev/null 2>&1; then
        curl -LsSf https://astral.sh/uv/install.sh -o "$TMPDIR/uv-installer.sh"
    elif command -v wget >/dev/null 2>&1; then
        wget -q https://astral.sh/uv/install.sh -O "$TMPDIR/uv-installer.sh"
    else
        python3 - "$TMPDIR/uv-installer.sh" <<'PY'
import sys, urllib.request
urllib.request.urlretrieve('https://astral.sh/uv/install.sh', sys.argv[1])
PY
    fi
    UV_UNMANAGED_INSTALL="$VIEWER_ROOT/runtime/bin" sh "$TMPDIR/uv-installer.sh"
fi
UV="$VIEWER_ROOT/runtime/bin/uv"
TORCH_BACKEND="${TORCH_BACKEND:-cu130}"
"$UV" --no-config python install 3.11
if [[ ! -x "$VIEWER_ROOT/.venv/bin/python" ]]; then
    "$UV" --no-config venv --python 3.11 "$VIEWER_ROOT/.venv"
fi
TORCH_LOCAL_WHEEL="$VIEWER_ROOT/dependencies/torch-2.14.1-cp311-cp311-manylinux_2_28_x86_64.whl"
if [[ "$TORCH_BACKEND" == "cu130" && -f "$TORCH_LOCAL_WHEEL" ]]; then
    "$UV" --no-config pip install --python "$VIEWER_ROOT/.venv/bin/python" \
        "$TORCH_LOCAL_WHEEL" 'nvidia-nvjitlink==13.0.88' \
        --torch-backend "$TORCH_BACKEND" --index-url https://pypi.org/simple
else
    "$UV" --no-config pip install --python "$VIEWER_ROOT/.venv/bin/python" \
        'torch==2.14.1' --torch-backend "$TORCH_BACKEND" --index-url https://pypi.org/simple
fi
"$UV" --no-config pip install --python "$VIEWER_ROOT/.venv/bin/python" \
    -r requirements-viewer.txt --index-url https://pypi.org/simple
"$UV" --no-config pip check --python "$VIEWER_ROOT/.venv/bin/python"
bash run.sh --headless --seconds 2
printf '\nReady. Start the viewer and motion selector with: bash run.sh --loop\n'
