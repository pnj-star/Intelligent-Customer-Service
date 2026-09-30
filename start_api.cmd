@echo off
cd /d "%~dp0"
set "PY_CMD="
if exist "D:\my_env\langgraph_env\Scripts\python.exe" set "PY_CMD=D:\my_env\langgraph_env\Scripts\python.exe"
if not defined PY_CMD if exist "D:\python\python.exe" set "PY_CMD=D:\python\python.exe"
if not defined PY_CMD set "PY_CMD=python"
echo Using: %PY_CMD%
echo Starting Customer Service API on http://127.0.0.1:8000 ...
"%PY_CMD%" run.py
echo.
echo API service stopped.
pause
