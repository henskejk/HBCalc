#!/bin/zsh
# Starts the brewing calculator. Double-click in Finder, or run ./run.command
# Add --lan to make it reachable from your phone on home Wi-Fi.
cd "$(dirname "$0")" || exit 1
STREAMLIT="$HOME/miniforge3/envs/brewing_calculator/bin/streamlit"
if [[ ! -x "$STREAMLIT" ]]; then
  echo "Can't find the brewing_calculator conda environment. Create it with:"
  echo "  conda env create -f environment.yml"
  exit 1
fi
if [[ "$1" == "--lan" ]]; then
  exec "$STREAMLIT" run app.py --server.address 0.0.0.0
fi
exec "$STREAMLIT" run app.py
