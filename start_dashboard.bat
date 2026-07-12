@echo off
rem Tu khoi dong Bambu Dashboard khi dang nhap Windows (Task Scheduler goi file nay).
rem Log ghi ra dashboard.log de xem loi khi can.
cd /d d:\15.BambuStudio
set PYTHONIOENCODING=utf-8
python bambu_web.py >> dashboard.log 2>&1
