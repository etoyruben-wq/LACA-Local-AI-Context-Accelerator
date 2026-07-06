@echo off
py AI\run.py result
if errorlevel 1 python AI\run.py result
