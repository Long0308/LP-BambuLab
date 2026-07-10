# HANDOVER — Bambu A1 LAN Dashboard

**Cập nhật:** 2026-07-11 · **Nhánh:** main · **Commit mới nhất:** `9cf49d2`

## Mục tiêu dự án
Dashboard xem/điều khiển máy in **Bambu Lab A1 + AMS Lite** qua **LAN**, mở bằng điện thoại.
**Nguyên tắc CỨNG:** mọi lệnh in/dừng do **người dùng bấm trên web**. AI KHÔNG có quyền ra lệnh
→ **KHÔNG BAO GIỜ** tạo `.mcp.json` (Claude Code tự nạp thành MCP = trao quyền điều khiển cho AI).

## Kiến trúc
- `bambu_web.py` — MQTT (TLS 8883, user `bblp`/access code) + HTTP server `0.0.0.0:8787`.
  Trang: `/` dashboard, `/info` phân tích G-code, `/files` duyệt file trong máy.
- `filament_ftp.py` — tải `.gcode.3mf` qua **FTPS implicit cổng 990** → bóc TỔNG GAM
  (hybrid `slice_info used_g`, chạy cho cả Bambu Studio + OrcaSlicer), ảnh model, thông số.
- `filament_store.py` — gam nhựa còn lại theo `tag_uid` RFID → `filament.local.json`.
- `printer_config.py` — nạp cấu hình, ưu tiên: args > env `BAMBU_*` > `.env` > `printer.local.json`.

## Bảo mật (giữ nguyên, kiểm mỗi lần push)
- **Gitignore** (đã xác nhận hoạt động): `.env`, `printer.local.json`, `filament.local.json`, `job_cache/`, `.mcp.json`.
- `.env` chứa access_code + serial thật → **không bao giờ commit**.
- Trước push: `git diff --cached | grep -E "0766fd90|104ba091|541bac4f|03900D650922452"` phải rỗng.

## Xong phiên này (commit 9cf49d2)
1. **Thumbnail trang /files**: route `/api/filethumb?path=` (lazy + cache `job_cache/<key>.png`,
   serial hoá qua `THUMB_LOCK`), `<img loading=lazy>` mỗi file `.gcode.3mf`.
2. **Config chống lỗi in** `Body14-PLAMatte-Decor-QUALITY-0.16-process.json` + `Body14-QUALITY-huong-dan.md`.
   Sinh ra sau khi soi bản in FAST 0.24 (ảnh thật): **lộ vân mặt cong + viền lỗ không đều**.
   Kết luận: model hữu cơ → lỗi do **layer height + WALL**, KHÔNG phải "mặt trên".
   Sửa: layer 0.24→0.16, wall 2→3, inner/outer sequence, outer_wall_speed 120, seam aligned.
   UI-only (không nhét preset được): Variable Layer Height + calib PA/Flow + Slow-down-for-overhangs.

## Còn dở (ưu tiên phiên sau)
1. **Upload/push file từ máy tính → máy in qua LAN** (user hỏi "còn upload từ bambo xuống như nào").
   Hướng: FTPS `STOR` lên `/` hoặc `/cache`, rồi có thể chọn in ngay trên /files. Cùng đường FTPS đang dùng.
2. **Test LIVE lệnh in** `cmd_project_file` (BETA, chưa chạy thật). Nghi ngờ payload `url`:
   `file:///sdcard/...` có thể phải là `/mnt/sdcard/...` hoặc cần `ams_mapping`. Chỉ test khi máy RẢNH.
3. **Bug tiềm ẩn** `filament_ftp.py`: `fetch_job` dùng tmp cố định `bambu_job.3mf`, `fetch_thumb_for`
   dùng `bambu_thumb.3mf` → nên đổi sang `tempfile.NamedTemporaryFile` (rủi ro thấp vì THUMB_LOCK
   đã serial hoá, nhưng nên vá).
4. Cache thumb theo `basename`, không hết hạn → file trùng tên đổi nội dung sẽ hiện ảnh cũ (phụ).

## Chạy
```
python bambu_web.py     # rồi mở http://<IP-máy-tính>:8787 trên điện thoại (cùng WiFi)
```
Healthz `False` ngay sau khởi động là do MQTT connect ~5–11s, không phải lỗi.
