@echo off
chcp 65001 >nul
REM === CHAY FILE NAY BANG QUYEN ADMIN (chuot phai > Run as administrator) ===
REM Mo cong 8787 de dien thoai truy cap web dashboard qua LAN. Chi can chay 1 lan.
netsh advfirewall firewall add rule name="Bambu Web Dashboard 8787" dir=in action=allow protocol=TCP localport=8787
echo.
echo Neu thay "Ok." o tren la da mo cong thanh cong.
pause
