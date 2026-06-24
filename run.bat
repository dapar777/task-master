@echo off
REM Spuštění Task Master bez konzolového okna (pythonw)
cd /d "%~dp0"
start "" pythonw "%~dp0main.py"
