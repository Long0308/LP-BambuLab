@echo off
chcp 65001 >nul
REM === Keo-tha 1 file .3mf / .gcode.3mf / .gcode vao file .bat nay de phan tich ===
if "%~1"=="" (
  echo.
  echo   Keo-tha 1 file in [.3mf / .gcode.3mf / .gcode] len file .bat nay.
  echo.
  pause
  exit /b
)
python "%~dp0analyze_print.py" "%~1"
echo.
pause
