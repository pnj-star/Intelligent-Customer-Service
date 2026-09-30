@echo off
cd /d "%~dp0"
set "PY_CMD="
if exist "D:\my_env\langgraph_env\Scripts\python.exe" set "PY_CMD=D:\my_env\langgraph_env\Scripts\python.exe"
if not defined PY_CMD if exist "D:\python\python.exe" set "PY_CMD=D:\python\python.exe"
if not defined PY_CMD set "PY_CMD=python"
echo Using: %PY_CMD%
echo Starting Customer Service MCP (streamable-http) on http://127.0.0.1:8001 ...
"%PY_CMD%" run_mcp.py --transport streamable-http --port 8001
echo.
echo MCP service stopped.
pause
