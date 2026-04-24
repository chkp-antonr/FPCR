#!/bin/bash
# Wrapper script to run pytest with correct PYTHONPATH

cd "$(dirname "$0")"
PYTHONPATH="src:$PYTHONPATH" uv run pytest "$@"
