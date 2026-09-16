#!/usr/bin/env bash
# One-click start: pipeline (background) + Streamlit dashboard (foreground).
# Usage: bash run_all.sh   (activate your virtualenv first)
set -e
cd "$(dirname "$0")"

echo "Starting pipeline (app.main)..."
python -m app.main --run-seconds 0 &
MAIN_PID=$!

echo "Starting dashboard on http://localhost:8501 ..."
streamlit run app/web.py --server.port 8501

echo "Stopping pipeline (PID=$MAIN_PID)..."
kill "$MAIN_PID"
