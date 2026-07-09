# HANDOVER — Bambu Lab A1 Combo + AMS Lite · Bộ công cụ cấu hình & phân tích in

**Ngày:** 2026-07-08 · **Thư mục:** `d:\56.BambuStudio` · **Ngôn ngữ deliverable:** Tiếng Việt (tên setting giữ tiếng Anh)
**Nguồn dữ liệu:** đối chiếu qua **MCP Firecrawl** — wiki Bambu Lab, forum (Reddit/Bambu/FB), MakerWorld, OrcaSlicer wiki, và repo engine **FULU-Foundation/OrcaSlicer-bambulab** (lấy density/preset gốc).

---

## 1. TRẠNG THÁI: ✅ Đang chạy tốt (mọi file HTML/JS đã kiểm cú pháp OK)

### File chính (deliverable)
| File | Vai trò | Trạng thái |
|---|---|---|
| **`BambuLab-A1-Hub.html`** ⭐ | **App hợp nhất** (1 file offline): top bar 2 combobox **Nhựa** + **Mục tiêu** · 6 tab (Tổng quan / Thông số / Phân tích file / Quy trình / Tư vấn / Cải thiện Orca / Tài nguyên) | DONE, ~90 KB |
| `BambuLab-A1-Operator-Manual.html` | Sổ tay vận hành light theme, mục ①–⑪ (clone giao diện, quy trình 9 bước, PLA/PETG/Matte/Lite, first-layer, Order of walls, warping) | DONE |
| `BambuLab-A1-Form-Mau-ThongSo.html` | Form mẫu thông số (cột "Của bạn" điền tay) | DONE |
| `BambuLab-A1-Combo-AMS-TechTransfer.html` | Infographic 3D isometric (dark theme) — bản đầu tiên | DONE (giữ tham khảo) |

### Tool Python
| File | Chức năng | Trạng thái |
|---|---|---|
| **`analyze_print.py`** + `Phan-Tich-File-In.bat` | Kéo-thả `.3mf`/`.gcode.3mf` → tính **REAL** (mesh: bbox từng-vật/thể tích/thể tích/%mặt cong-đứng-overhang/lật mặt) + form Bambu-style + audit động + tư vấn mục tiêu + symptom + material ref | DONE, đã test 2 file (dragchain, hộp mỹ phẩm) |
| **`bambu_status.py`** + `Trang-Thai-May-In.bat` | Xem **trạng thái máy in qua LAN** (MQTT 8883 trực tiếp từ máy): stage/%tiến độ/lớp/còn-time/nozzle/bed/AMS | Code DONE, **CHƯA test máy thật** (cần IP/serial/access code) |
| `bambu_connect.py` + `Ket-Noi-Bambu.bat` | Test cổng LAN (8883/990) + ghi `.mcp.json` | DONE |
| `.mcp.json` | Đăng ký MCP `@rowbotik/bambu-printer-mcp` (npx) | **Còn PLACEHOLDER** — chưa điền IP/serial/token |
| `a1-img/` | 11 ảnh trích từ PDF User Manual (màn hình A1, Wi-Fi setup) | DONE |

### Đã cài đặt môi trường
- `paho-mqtt` (cho bambu_status.py) · Node v25 + npx (cho MCP) · Python 3.13.

---

## 2. HUB — các tính năng đã build (tham chiếu nhanh)
- **Combobox Nhựa** (PLA Basic/Matte/Lite/PETG/TPU) → đổi live bảng Filament.
- **Combobox Mục tiêu** (Thông thường/Chi tiết trang trí/Công năng cơ khí/Lớp 1 bám 25mm/s) → ô đổi **tô ★ xanh**.
- **Stepper 4 bước BẤM ĐƯỢC**: ① Printer → ② Filament → ③ Process(Global) → ④ Objects → **lọc bảng theo bước**; bấm lại = hiện tất cả.
- **Bước ③ có tab con** Quality/Strength/Speed/Support/Others → **panel clone giao diện Bambu/Orca** (label + ô input, section header nền xám highlight, guide ↑↓ tiếng Việt dưới nhãn).
- Các tab Process/Filament chia **mục con đúng thứ tự phần mềm** (Quality: Layer height→Line width→Seam(scarf)→Precision→Ironing→Wall generator→Advanced; v.v.).
- **Global vs Objects** giải thích (đè setting riêng từng vật/part/height-range).
- **Phân tích file .3mf trong trình duyệt** (ZIP DecompressionStream + parse mesh + project_settings) → stats + advisor động.
- **Tư vấn**: 4 preset mục tiêu (kèm cột **"Chỉnh ở đâu"**) + bảng **triệu chứng→chỉnh gì** + **warping** chi tiết.
- **Cải thiện (Orca)**: smooth chi tiết/lớp ngoài/trên/dưới + **lỗi lộ vân ngoài** + **setting theo màu** (làm rõ) + 24 tính năng Orca (README).
- **Nhựa theo HÃNG** (Bambu/Generic/Sunlu/eSun/Polymaker — PLA & PETG).
- **Bản vẽ chi tiết "Project Filaments"** đánh số ①–⑨ (⑤ = Sync from AMS) kiểu detail xây dựng.

---

## 3. PENDING / NEXT STEPS (session sau)

### Ưu tiên cao
1. **Kích hoạt MCP máy in**: điền IP/Serial/Access Code thật vào `.mcp.json` (hoặc chạy `Ket-Noi-Bambu.bat`) → **restart Claude** → gọi `mcp__bambu-printer__get_printer_status` để verify. Máy phải bật **LAN Only + Developer Mode**.
2. **Test `bambu_status.py`** với máy thật: `Trang-Thai-May-In.bat <IP> <SERIAL> <CODE>`.
3. **Ngoài mạng (external)**: khuyến nghị **Tailscale/WireGuard** VPN vào LAN (tool LAN chạy nguyên); hoặc Bambu Cloud (cần MCP hỗ trợ account login — hiện fork thiên LAN).

### Đã OFFER nhưng CHƯA làm (user chưa chốt)
- Nút **"Xuất preset"** trong Hub → tải `.txt`/`.json` theo (Nhựa + Mục tiêu) đang chọn để dán/nhập Bambu Studio.
- **Bản vẽ detail đánh số thứ 2** cho khu **Slicing Result / Preview**.
- Đổi **màu nền section header theo màu tab** (Quality xanh lá · Strength xanh dương · Speed cam…).
- Toggle **Sáng/Tối** cho Hub.

### Ghi chú kỹ thuật
- Console Windows (cp1252) lỗi khi in tiếng Việt có dấu → dùng `sys.stdout.reconfigure(encoding="utf-8")` (đã có trong các script). HTML/report luôn UTF-8 nên hiển thị dấu OK.
- `analyze_print.py`: mesh volume/bbox **transform-aware**; density theo material (`material_density()` — Matte 1.32 từ repo). Với `.gcode.3mf` sẽ tính thêm **toolpath thật** (max volumetric flow, retract, temp) — chưa test file gcode thực.
- README OrcaSlicer đầy đủ đã lưu tại: `tool-results/mcp-firecrawl-firecrawl_scrape-1783475772263.txt` (92k ký tự) nếu cần trích thêm.

---

## 4. SỰ THẬT KIẾN TRÚC (đừng nhầm ở session sau)
- **OrcaSlicer KHÔNG có MCP.** Trạng thái máy đến từ **MQTT của MÁY** (8883 TLS), không qua slicer.
- **Setting print (Process) KHÔNG theo màu** — theo VẬT LIỆU (Global) hoặc theo VẬT (Objects). Màu chỉ ảnh hưởng **Flushing volumes** + tinh chỉnh ±5°C.
- **A1 = 1 nozzle**, in màu bằng đổi nhựa AMS Lite (tối đa 4 màu). "Chọn đầu in" = chọn ⌀ nozzle.
- **A1 hở khung** → tránh ABS/ASA.
