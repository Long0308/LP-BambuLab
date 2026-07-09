@echo off
chcp 65001 >nul
REM Xem trang thai may in Bambu A1 qua LAN (doc IP/serial/code tu .mcp.json).
REM Hoac chay:  Trang-Thai-May-In.bat <IP> <SERIAL> <ACCESS_CODE>
python "%~dp0bambu_status.py" %*
echo.
pause
