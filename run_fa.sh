#!/bin/bash

echo "Starting FPCR WebUI Development Server..."

uv run uvicorn src.fa.app:app --reload --port 8080 --reload-exclude ".venv",".worktrees"
