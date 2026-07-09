@echo off
chcp 65001 >nul
title Bambu A1 - Web Dashboard
REM Chay web dashboard theo doi may in. Dien thoai mo: http://<IP-PC>:8787
echo Dang khoi dong dashboard tren cong 8787...
echo Dien thoai (cung Wi-Fi/LAN) mo trinh duyet:  http://192.168.1.6:8787
echo Tren PC:  http://localhost:8787
echo (Dong cua so nay = tat dashboard)
echo.
python "%~dp0bambu_web.py" 8787
pause
