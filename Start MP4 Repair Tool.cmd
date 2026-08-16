@echo off
setlocal
cd /d "%~dp0"
python repair_mp4.py gui
if errorlevel 1 pause

