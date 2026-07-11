---
name: bambu-slice
description: Slice file .3mf bằng Bambu Studio CLI (headless) trên server — pipeline upload → tự slice → đẩy xuống máy in qua LAN, kèm hướng dẫn đưa lên production/HTTPS. Dùng khi cần slice không mở giao diện, tích hợp slice vào web, hoặc debug lỗi CLI slice.
---

# Bambu Slice — CLI headless + pipeline web

## 1. Lệnh CLI đã kiểm chứng (Bambu Studio 2.7.1, 2026-07-11)

```
bambu-studio.exe --slice 0 --export-3mf <TEN-FILE-TRAN> --outputdir <DIR> <input.3mf>
```

**Quirk bắt buộc nhớ** (mất nhiều giờ mới tìm ra):
- `--export-3mf` phải là **tên file trần** (không kèm đường dẫn) — nó tự ghi vào `--outputdir`.
  Đưa đường dẫn tuyệt đối vào → lỗi `-13 "Failed exporting 3mf files"`.
- Kết quả nằm ở `<outputdir>/result.json`: `return_code == 0` là OK; `-3` = không tìm thấy
  file input (thường do bash làm hỏng backslash → **gọi qua PowerShell** hoặc dùng
  `subprocess.run` list-args); `-5` = preset không parse được.
- `--load-settings <file.json>` với preset kiểu process-export **KHÔNG chạy** (`-5`).
  Cách đúng: **sửa thẳng `Metadata/project_settings.config` bên trong file .3mf** (là zip),
  vì file .3mf xuất từ Bambu/Orca luôn chứa sẵn toàn bộ config (~571 key).
- File input phải là **project .3mf có config nhúng**. Slice mất ~15-60s cho model thường.
- Exe không in gì ra console (app GUI) — đọc `result.json`, đừng chờ stdout.

## 2. Các module trong repo này

| File | Vai trò |
|---|---|
| `slicer_cli.py` | `find_exe()` (env `BAMBU_STUDIO_EXE` → ổ D/C), `slice_3mf(src, workdir)` → `(ok, path, stats)`, `stats_from_gcode3mf()` đọc thời gian in / lớp / gam từ header G-code |
| `bambu_web.py` | `POST /api/upload?name=` phân luồng: đã slice (`parse_is_sliced`) → FTPS STOR thẳng; chưa slice → thread nền `_slice_and_push` → STOR. `GET /api/upstatus` cho UI poll 3s |
| `filament_ftp.py` | `parse_is_sliced()` mở zip xem có `Metadata/plate_N.gcode` (KHÔNG đoán bằng đuôi tên — Bambu lưu file đã slice là `.3mf` thường trong /cache); `upload_file()` STOR với `storbinary` ghi đè **bỏ `conn.unwrap()`** (Bambu không trả `close_notify` → unwrap treo vĩnh viễn) |

Chỉnh config nhúng + tắt Variable Layer Height (thủ phạm cộng 48% số lớp âm thầm):
```python
# doc zip -> sua Metadata/project_settings.config (json) -> ghi zip moi
# BO entry Metadata/layer_heights_profile.txt  => tat Variable Layer Height
```
Trần tốc độ vật lý: `v_max = max_volumetric_speed / (layer_height × line_width)`
(PLA Lite 16 mm³/s @ 0.2×0.42 → 190 mm/s; đặt cao hơn chỉ là số ảo, máy tự hãm).

## 3. Nguyên tắc an toàn (BẤT BIẾN của dự án này)

- AI **không ra lệnh in**. Slice = tính toán thuần. STOR xuống SD = lưu trữ, được phép
  trong luồng upload do NGƯỜI DÙNG bấm. Lệnh in luôn là nút "In" người dùng bấm.
- Không bao giờ tạo `.mcp.json` (Claude Code tự nạp → trao quyền điều khiển máy in cho AI).
- Upload validate: chỉ `.3mf`, cắt `basename` chống traversal, cap 300 MB, 1 job slice/lần.

## 4. Đưa lên production / HTTPS ra ngoài WiFi

Server hiện là `http.server` cổng 8787 — đủ cho LAN tin cậy, **CHƯA đủ ra internet**.
Lộ trình khuyến nghị (thứ tự ưu tiên):

1. **Tailscale / WireGuard (khuyến nghị mạnh)** — cài Tailscale trên PC + điện thoại,
   truy cập `http://<ten-may>:8787` từ bất cứ đâu như đang ở nhà. **Không mở cổng
   router, không lộ máy in ra internet**, có HTTPS sẵn qua `tailscale serve`.
   Đây là lựa chọn đúng cho thiết bị điều khiển phần cứng.
2. **Caddy reverse proxy** (nếu buộc phải public): Caddy tự lo Let's Encrypt.
   `Caddyfile`: `in.example.com { reverse_proxy 127.0.0.1:8787 }`. BẮT BUỘC kèm:
   - Basic-auth hoặc forward-auth (Authelia) — server chưa có đăng nhập.
   - Rate-limit + fail2ban. KHÔNG forward cổng 990/8883 của máy in.
3. **Cứng hoá app trước khi public** (việc còn thiếu trong code):
   - Thêm token/session cho mọi route POST (hiện ai vào LAN cũng bấm được).
   - Chuyển `ThreadingHTTPServer` → `waitress`/`uvicorn` để chịu tải.
   - CSRF cho form, giới hạn kích thước request toàn cục.

## 5. Debug nhanh

| Triệu chứng | Nguyên nhân | Xử lý |
|---|---|---|
| result.json `-13` | `--export-3mf` có đường dẫn | Dùng tên trần + `--outputdir` |
| result.json `-3` | Path input hỏng (bash backslash) | PowerShell / subprocess list |
| result.json `-5` | `--load-settings` preset thiếu `type` | Sửa config nhúng trong .3mf |
| Upload treo 100% | `unwrap()` chờ close_notify | Đã vá trong `ImplicitFTP_TLS.storbinary` |
| FTP từ chối | Bambu Studio GUI đang giữ kết nối | Đóng Bambu Studio khi upload |
| Nút In khoá nhầm | Đoán slice bằng đuôi tên | Dùng `parse_is_sliced()` (mở zip) |
