#!/bin/zsh
# Starts the React version of the brewing calculator. Double-click in Finder, or run ./run_react.command
# Add --lan to make it reachable from your phone on home Wi-Fi.
# (The Streamlit version still starts with ./run.command.)
cd "$(dirname "$0")" || exit 1
PYTHON="$HOME/miniforge3/envs/brewing_calculator/bin/python"
if [[ ! -x "$PYTHON" ]]; then
  echo "Can't find the brewing_calculator conda environment. Create it with:"
  echo "  conda env create -f environment.yml"
  exit 1
fi
if ! "$PYTHON" -c "import starlette, uvicorn" 2>/dev/null; then
  echo "The React version needs two more packages. Install them with:"
  echo "  conda install -n brewing_calculator -c conda-forge starlette uvicorn"
  exit 1
fi
if [[ ! -f web/dist/index.html ]]; then
  echo "The React app hasn't been built (web/dist is missing). See web/README.md."
  exit 1
fi
HOST=127.0.0.1
[[ "$1" == "--lan" ]] && HOST=0.0.0.0
echo "Open http://localhost:8000   (Ctrl+C to stop)"
exec "$PYTHON" -m uvicorn api:app --host "$HOST" --port 8000
