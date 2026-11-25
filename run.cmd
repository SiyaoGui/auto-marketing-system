@echo off
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" -m engine.cli %*
) else (
  python -m engine.cli %*
)
