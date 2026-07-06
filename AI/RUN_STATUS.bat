@echo off
py AI\run.py status
if errorlevel 1 python AI\run.py status
