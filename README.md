# LP-BambuLab — Bộ công cụ Bambu Lab A1

Tài liệu + công cụ tự dùng cho máy in **Bambu Lab A1 (+ AMS Lite)**: một hub HTML tra cứu
thông số offline, bộ phân tích file `.3mf`, và script nói chuyện với máy in qua LAN.

Toàn bộ số liệu trong hub được **đối chiếu với bản Bambu Studio cài trên máy**, không lấy từ
trí nhớ hay từ nhánh `master` trên GitHub (xem [NOTICE](NOTICE) — mục "Vì sao giữ bản sao local").

## Nội dung

| File | Là gì |
|---|---|
| `BambuLab-A1-Hub.html` | Hub chính. Tra thông số theo *nhựa × mục tiêu in*, xem giải thích từng option, thả file `.3mf` vào để audit, xuất preset import được vào Bambu Studio. Chạy offline, không cần server. |
| `BambuLab-A1-Operator-Manual.html` | Sổ tay vận hành máy. |
| `BambuLab-A1-Combo-AMS-TechTransfer.html` | Ghi chú chuyển giao AMS Lite. |
| `BambuLab-A1-Form-Mau-ThongSo.html` | Form mẫu điền thông số. |
| `analyze_print.py` | Phân tích file in. |
| `bambu_status.py` | Đọc trạng thái máy qua MQTT LAN (cổng 8883). |
| `bambu_connect.py` | Sinh `printer.local.json` từ IP / Serial / Access Code. |
| `bambu_web.py` | Web dashboard theo dõi + bảng điều khiển qua LAN (bạn bấm, không phải AI). |
| `printer_config.py` | Đọc/ghi `printer.local.json` dùng chung cho các script. |
| `boxson-PLAMatte-Decor-*.json` | Preset mẫu (process + filament) — import được. |
| `*.cpp` | Mã nguồn Bambu Studio, dùng làm ground truth. AGPL-3.0 — xem [NOTICE](NOTICE). |

## Kết nối máy in

Trên máy in bật **LAN Only Mode** + **Developer Mode**, lấy IP / Serial / Access Code, rồi:

```bash
python bambu_connect.py <IP> <SERIAL> <ACCESS_CODE>   # sinh printer.local.json
python bambu_status.py                                # đọc trạng thái
python bambu_web.py 8787                              # dashboard: http://<IP-PC>:8787
```

`printer.local.json` **không được commit** (nó chứa access code). Khuôn mẫu ở `printer.local.example.json`.

## Bảo mật

**Không bao giờ đặt cấu hình máy in vào `.mcp.json`.** Claude Code tự động nạp
project-scoped MCP server từ `.mcp.json` ở thư mục gốc. Nếu cấu hình nằm ở đó,
AI sẽ được trao toàn quyền điều khiển máy in — `start_print_job`, `cancel_print`,
`set_temperature`, `delete_printer_file`, `upload_gcode`, `set_ams_drying`…

Nguyên tắc của dự án: **mọi lệnh điều khiển do người dùng bấm trên web dashboard;
AI chỉ đọc và phân tích.** Hai lớp bảo vệ đang bật:

1. Cấu hình nằm ở `printer.local.json` (không phải `.mcp.json`), và `.mcp.json` bị gitignore.
2. `.claude/settings.json` đặt `"disabledMcpjsonServers": ["bambu-printer"]`.

## Ba cái bẫy đã tốn thời gian để tìm ra

**1. Scarf seam có hai công tắc, và filament thắng im lặng.**
`seam_slope_type` (Process) bật scarf, nhưng `filament_scarf_seam_type` (Filament) mặc định là
`none` và **không có ô checkbox override** — nên nó luôn đè lên Process. Kết quả: scarf tắt mà
không báo gì, seam vẫn lộ. Lòng chảo/lỗ là *hole*, nên phải đặt `all` (Contour **and hole**),
không phải `external`.

**2. Variable layer height bị hai thứ chặn.**
Bambu từ chối với thông báo *"Variable layer height is not supported with Organic supports"* —
mà `support_style = Default` lại **tự chọn organic** cho tree support. Và *"Prime tower does not
work when Adaptive Layer Height is on"*. Ngoài ra `adaptive_layer_height` nằm trong danh sách
`ignore` của `PrintConfig.cpp` ⇒ **không set được bằng preset**, phải bật tay trên object.

**2b. Bambu Studio 2.x không nhúng kết quả slice vào `Save Project`.**
Kiểm trên 16 file `.3mf`: mọi file do client `1.10.x` ghi đều có `<plate>` + `prediction` trong
`slice_info.config` (3/3); mọi file do `2.x` ghi chỉ có `<header>` (6/6), và không có chỗ nào khác
trong file chứa tổng thời gian. Trên 2.x, cách **duy nhất** để có Thời gian in / Khối lượng thật là
`File ▸ Export ▸ Export plate sliced file` → `.gcode.3mf`. Hub đọc `X-BBL-Client-Version` và báo
đúng theo phiên bản, thay vì đổ lỗi cho thao tác của người dùng.

**3. Hạ tốc độ tường ngoài không "mua" được chất lượng.**
Thời gian in **tường** tỉ lệ với **số lớp**; thời gian **infill** tỉ lệ với **thể tích** (đã chạm
trần lưu lượng 22 mm³/s). Nên: muốn tiết kiệm → giảm infill; muốn mặt cong mịn → Variable layer
height. Hạ `outer_wall_speed`/`acceleration` chỉ làm thời gian tăng gấp ba.

Đo thật trên `boxson.3mf` (182.8 × 151.8 × 150.0 mm, 79% thành đứng):

| | Baseline 0.28 | Bản chỉnh sai | Bản chốt |
|---|---|---|---|
| Layer | 0.28 | 0.16 | **0.20** |
| Outer speed · accel | 200 · 5000/6000 | 100 · 2500/3500 | **200 · 5000/6000** |
| Infill | 15% grid | 15% gyroid | **10% adaptive cubic** |
| Thời gian | 10h37m | **31h54m** | **10h44m** |
| Nhựa | 568 g | 716 g | **469 g** (−17%) |

## Hub kiểm được những gì

Thả file `.3mf` vào tab **Phân tích**, hub đọc `Metadata/project_settings.config` (571 key) + mesh thật rồi báo:

- **Conflict Filament → Process**: scarf seam bị tắt ngầm; 13 key retraction; 7 key overhang/bridge
  (có tôn trọng `nil` và công tắc tổng `override_process_overhang_speed`, nên không báo oan).
- **Chặn Variable layer height**: organic support, prime tower.
- **Trần lưu lượng**: `v_max = max_volumetric_speed / (layer_height × line_width)`. Chỉ ra chỗ đặt
  tốc độ cao vô nghĩa, và chỗ còn dư trần ở vùng khuất (tăng tốc miễn phí, không đụng bề mặt).
- Vân bậc thang, cong vênh đế lớn, `Inner/Outer/Inner` khi < 3 wall, `precise_outer_wall` bị bỏ qua…

## Import preset

`File ▸ Import ▸ Import Configs…` → Ctrl+chọn **cả hai** file `boxson-PLAMatte-Decor-*.json`
→ báo "2 configs imported" → rồi **chọn preset ở dropdown** (import không tự áp dụng).

Schema user-preset bắt buộc có `from: "User"`, `inherits`, `name`, **`version`**. Thiếu `version`
là ra "0 configs imported". Không được có `type` / `instantiation` / `compatible_printers`.
