@echo off
py AI\run.py scan
if errorlevel 1 python AI\run.py scan
