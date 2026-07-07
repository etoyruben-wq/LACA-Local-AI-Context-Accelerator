@echo off
cd /d "%~dp0\.."
py AI\run.py graph
if errorlevel 1 (
  python AI\run.py graph
)
