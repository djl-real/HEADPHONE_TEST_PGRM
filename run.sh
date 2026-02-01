#!/bin/bash
# Launch program inside the local virtual environment

# Get directory of this script
DIR="$(cd "$(dirname "$0")" && pwd)"

export PATH="/home/dj/Dev/mimic1:$PATH"

# Activate virtual environment
source "$DIR/.venv/bin/activate"

# Run your program
python3 "$DIR/main_window.py"
