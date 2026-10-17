@echo off
REM Run the data pipeline (used by Windows Task Scheduler)
REM %~dp0 = folder where this .bat file is located
cd /d "%~dp0"
"%~dp0venv\Scripts\python.exe" main.py