@echo off
chcp 65001 >nul
REM === Tro ly ket noi may Bambu Lab A1 qua MCP (LAN) ===
python "%~dp0bambu_connect.py" %*
echo.
pause
