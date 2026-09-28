@echo off
rem Khoi dong Bambu Hub server (bambu_web.py, cong 8787).
rem Tu dong khoi dong lai neu process bi thoat (Sleep day / dut mang / crash).
rem Da chay roi thi thoat ngay — khong mo 2 instance trung lap.
cd /d %~dp0

powershell -NoProfile -Command "if (Get-NetTCPConnection -LocalPort 8787 -State Listen -ErrorAction SilentlyContinue) {exit 1} else {exit 0}"
if errorlevel 1 exit /b 0

:run_loop
echo [%date% %time%] Khoi dong Bambu Hub server... >> server.log
python -u bambu_web.py >> server.log 2>&1
echo [%date% %time%] Bambu Hub dung (exitcode %errorlevel%), tu dong khoi dong lai sau 3s... >> server.log
timeout /t 3 /nobreak >nul
goto run_loop