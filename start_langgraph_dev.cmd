@echo off
cd /d "%~dp0"
set "PYTHONUTF8=1"
set "PYTHONPATH=D:\my_project\Intelligent Customer Service\src;D:\my_project\Intelligent Customer Service\components\common_core\src;D:\my_project\Intelligent Customer Service\components\retrieve_skill\src;D:\my_project\Intelligent Customer Service\components\nl2sql_skill\src"
set "LANGGRAPH_CMD="
if exist "D:\my_env\langgraph_env\Scripts\langgraph.exe" set "LANGGRAPH_CMD=D:\my_env\langgraph_env\Scripts\langgraph.exe"
if not defined LANGGRAPH_CMD set "LANGGRAPH_CMD=langgraph"
echo Using: %LANGGRAPH_CMD%
echo Starting LangGraph Studio/API on http://127.0.0.1:2024 ...
"%LANGGRAPH_CMD%" dev --allow-blocking
echo.
echo LangGraph dev stopped.
pause
