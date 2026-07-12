@echo off
rem Khoi dong Bambu Hub server (bambu_web.py, cong 8787).
rem Duoc goi boi Task Scheduler luc logon (qua Start-BambuHub-Hidden.vbs de an cua so),
rem hoac chay tay khi can. Da chay roi thi thoat ngay — khong mo 2 instance.
cd /d %~dp0
powershell -NoProfile -Command "if (Get-CimInstance Win32_Process -Filter \"Name like 'python%%'\" | Where-Object {$_.CommandLine -match 'bambu_web'}) {exit 1} else {exit 0}"
if errorlevel 1 exit /b 0
python bambu_web.py >> server.log 2>&1