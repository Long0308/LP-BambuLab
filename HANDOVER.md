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

3. **Upload file lên máy qua LAN** — XONG. `filament_ftp.upload_file()` (FTPS `STOR` lên gốc `/`)
   + route `POST /api/upload?name=` (nhận **raw bytes**, KHÔNG multipart — đơn giản hơn nhiều)
   + nút đẩy file kèm progress bar (XHR `upload.onprogress`) trên `/files`.
   Chốt chặn: chỉ `.3mf`, cắt về `basename` (chặn path traversal), ≤300 MB, dùng chung
   `THUMB_LOCK` để không tải/đẩy FTP song song.
   Đã test 4 case chặn (txt / thiếu tên / rỗng / traversal) → đều HTTP 400.
4. **Tmp file trùng tên** — XONG: `_tmp_3mf()` dùng `tempfile.mkstemp` thay tên cố định.

5. **Slice server-side tích hợp luồng upload** (2026-07-11 chiều). Upload phân luồng:
   file đã slice → STOR thẳng; file dự án thô → `slicer_cli.slice_3mf()` (Bambu Studio CLI
   headless, ~17s) chạy nền → STOR kết quả `.gcode.3mf`. UI poll `/api/upstatus` 3s, hiện
   thời gian in + gam + số lớp. Skill mới: `.claude/skills/bambu-slice/SKILL.md` (quirk CLI
   `-13/-3/-5`, fix treo `unwrap()`, lộ trình HTTPS production: Tailscale > Caddy+auth).
6. **2 bug đã vá**: upload treo 100% (`storbinary` bỏ `unwrap()` — Bambu không trả
   close_notify); nhận diện "đã slice" bằng nội dung zip thay vì đuôi tên.
7. **Tối ưu makep.3mf bằng phân tích Hub**: 12h13m → **9h47m (−20%)**, 438.6g → 402.2g.
   Thủ phạm: Variable Layer Height (TB 0.134mm = +280 lớp ẩn) + tốc độ vượt trần lưu lượng
   (233 > 190 mm/s thật của PLA Lite 16mm³/s). Bài học xoay model: −45° cho overhang 0.59%
   nhưng bám bàn = 0 cm² (đứng cạnh dao) → KHÔNG dùng, giữ tư thế gốc + support.

## Còn dở (ưu tiên phiên sau)
1. **USER TEST luồng upload+slice**: đẩy 1 file dự án thô trên `/files` → xem tự slice
   → xuất hiện `<tên>.gcode.3mf` trong danh sách. (AI không tự STOR — user bấm.)
2. **Test LIVE lệnh in** `cmd_project_file` (BETA). Nghi ngờ payload `url`: `file:///sdcard/...`
   có thể phải là `/mnt/sdcard/...` hoặc cần `ams_mapping`. Chỉ test khi máy RẢNH.
3. **Production/HTTPS** (user muốn ra ngoài WiFi): làm theo skill bambu-slice mục 4 —
   Tailscale trước, muốn public thì thêm auth token cho route POST + Caddy.
4. Cache thumb theo `basename`, không hết hạn → file trùng tên đổi nội dung hiện ảnh cũ (phụ).
5. AppData Bambu/Orca đã xoá sạch 2026-07-11 (352MB) do slicer crash; nếu bản cài mới vẫn
   crash → nghi driver GPU (cả 2 slicer cùng chết 0xC0000005).

## Chạy
```
python bambu_web.py     # rồi mở http://<IP-máy-tính>:8787 trên điện thoại (cùng WiFi)
```
Healthz `False` ngay sau khởi động là do MQTT connect ~5–11s, không phải lỗi.
