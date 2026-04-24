@echo off
echo Starting FPCR WebUI Development Server...

set PYTHONPATH=src
uv run uvicorn src.fa.app:app --port 8080 --log-level debug --reload-dir src --reload-exclude ".venv" --reload-exclude ".worktrees" %*
