# TODO phiên sau — LP-BambuLab hub

> Cập nhật 2026-07-16. Baseline: `main` @ `e7e37a2`, cây làm việc sạch, đã push hết.
> Đọc file này trước khi làm gì. Mọi số trong đây là **đo thật**, không phải ước lượng.

---

## ⚠️ CẦN HỎI USER TRƯỚC KHI LÀM T1

Ràng buộc **"<1h30p"** chưa rõ nghĩa. Hỏi user chọn:
- (a) **Ngân sách thời gian IN**: preset không được vượt baseline quá 1h30m, hay
- (b) **Giới hạn thời gian làm việc** của phiên.

Trước đó user nói *"tối ưu không vượt quá nhiều 1h"* → nghiêng về (a), nhưng **đừng đoán**.

---

## T1. A/B slice ép ngân sách cho cả 3 chế độ — bằng số thật

**Vấn đề:** đo thật trên `BUCKET.3mf` khay 1 (cao 135mm):

| | Thời gian | Nhựa |
|---|---|---|
| Bambu default `0.20mm Standard @BBL A1` | **3h23m** | 119.33g |
| Cân bằng (hub) | **4h46m** = **+1h23m** | 143.20g |
| Đẹp (hub, slice CLI) | **6h12m43s** (844 lớp) | 130.57g |

**Nguồn tốn giờ, xếp hạng** (từ diff data-driven 28 key):
1. `enable_support` 0→1 — **tốn nhất**. Model tên *"No support"*, tác giả để **tắt**, hub tự bật (hub đo 3.89% mặt hẫng).
2. `wall_loops` 2→3
3. `outer_wall_speed` 200→150, `top_surface_speed` 200→150
4. `top_shell_layers` 5→6, `bottom_shell_layers` 3→4

**Cách làm:** A/B slice thật từng lever (đã có `optimize_e2e.apply_preset` + `slicer_cli.slice_3mf`), **không đoán %**.

**KHÔNG được đụng** (đã tra nguồn, ta thắng Bambu):
- `wall_sequence` = inner-outer-inner → Orca wiki: *"gives you the best surface quality"*; Reddit: dùng khi ≥3 tường (ta có 3). Gần như miễn phí.
- `accel`/`travel` giảm → chống lệch trục vật cao, đo thật chỉ +7%.

---

## T2. Tab Plate 1/2/3 + ảnh từng khay

**Lõi XONG rồi** — chỉ thiếu UI:
- `analyzer.plates_3mf(z)` → `[{id, name, objects, thumb}]`
- `analyzer.analyze(path, plate=N)` → `r["plates"]`, `r["plate"]`, `r["plate_name"]`
- `slicer_cli.stats_from_gcode3mf(path, plate=N)` → `{plate, plates_total, time, layers, weight_g}`

**Cần làm trong `bambu_web.py`:**
- Endpoint phục vụ ảnh: file .3mf **đã có sẵn** `Metadata/plate_1.png`, `plate_2.png`… (Bambu Studio render sẵn, không cần tự vẽ).
- Tab khay + gọi lại analyze theo khay đang chọn.

**Số thật `BUCKET.3mf`** (để test đối chiếu):

| Khay | Tên | Kích thước | Bám bàn | Overhang | Slice |
|---|---|---|---|---|---|
| 1 | TWO TONE | 100×80×135 | 60.8cm² | 3.89% | 3h16m34s · 675 lớp · 106.56g |
| 2 | ONE COLOUR | 100×80×135 | 60.8cm² | 3.89% | 2h42m34s · 675 lớp · 104.03g |
| 3 | ONLY FOR NODESTACK | 100×10×122 | 8.9cm² | 0.24% | 1h29m30s · 610 lớp · 40.86g |

File nhiều khay khác trong Downloads: `4+cm+high (1).3mf` (2 khay).

---

## T3. Combo box chọn nhựa + tải filament preset

**Hàm XONG** — `analyzer.filament_preset(name, custom)` trả `{key, preset, why, verified, inherits, safe}`.
Test chạy: `PLA Matte` → `LP-PLA-Matte-safe`, 230°C / mvs 12 / flow 0.98 / bàn 55.

**Cần làm trong `bambu_web.py`:** combo box chọn khay AMS → nút tải `.json` **riêng, cạnh file process** (user đã chốt cách này, không nhét vào 3mf).

**Schema chuẩn** (bám file thật user tự export `boxson-PLAMatte-Decor-filament.json`): **không** có key `"type"`, mọi giá trị là **list string**, có `filament_settings_id` + `inherits` + `filament_extruder_variant` + `version: "2.7.0.8"`.

---

## T4. Bug cân nặng đa màu

`slicer_cli._WEIGHT_PAT` chỉ lấy dòng `filament used [g]` **đầu tiên** → file 2 màu **thiếu ~11%**.
Bằng chứng: `BUCKET.3mf` khay 1 — hub đọc **106.56g** (chỉ nhựa #1), thực tế Bambu Studio báo **119.33g** (nhựa #1 106.56 + nhựa #3 **12.77g**).
**Fix:** `findall` rồi **cộng tất cả**.

---

## T5. `Generic PLA` map sai

`analyzer._fil_export("Generic PLA")` → rơi vào fallback họ `PLA` → `inherits: "Bambu PLA Basic @BBL A1"` — **SAI**, Generic PLA là preset riêng.
**Fix:** thêm entry `GENERIC PLA` với `inherits` đúng. **Phải xác minh tên thật** trước khi ghi (sai `inherits` = Studio không import được).

---

## Ground truth đã xác minh (đừng tra lại)

**Tên `inherits` filament** — lấy từ `filament_settings_id` thật trong `slice_template.3mf`:
- ✓ `Bambu PLA Lite @BBL A1` · ✓ `Bambu PLA Matte @BBL A1` · ✓ `Bambu PETG Basic @BBL A1`
- Các tên khác trong `FIL_EXPORT` mới là **suy luận** (`verified: False`) — cần đối chiếu trước khi tin.

**Default thật `0.20mm Standard @BBL A1`** (đọc từ `project_settings.config`, KHÔNG phải gõ từ ảnh):
`outer_wall_speed 200` · `inner_wall_speed 300` · `sparse_infill_speed 270` · `internal_solid_infill_speed 250` · `top_surface_speed 200` · `initial_layer_speed 50` · `travel_speed 700` · `default_acceleration 6000` · `outer_wall_acceleration 5000` · `sparse_infill_density 8%` · `wall_loops 2` · `top_shell_layers 5` · `bottom_shell_layers 3` · `enable_support 0` · `support_type tree(auto)` · `sparse_infill_pattern gyroid` · `wall_generator classic` · `brim_type auto_brim`

**Số an toàn cộng đồng cho PLA Matte/đen** (forum BL + Reddit + wiki, đã nhúng vào hub):
230°C · max volumetric **12** mm³/s (stock 22) · flow ratio 0.98–0.99 · bàn 55°C · sấy trước · cold pull 260°C→90°C · kẹt cứng: 280–300°C hoá lỏng rồi rút.

---

## Luật ĐÚNG — đừng "sửa" (suýt phá 1 lần rồi)

- **`support_type`**: `flat_ratio ≥ 0.5` (model **hộp**) → `normal` vì *mặt hẫng phẳng cần đỡ đều, cây mọc lệch sẽ võng giữa nhánh*; còn lại → `tree`; cao >150mm → `tree_strong`. BUCKET `flat_ratio=0.73` → normal **đúng**.
- **`sparse_infill_pattern`**: quality→`gyroid` (đều hướng, chắc nhất — Prusa/forum xác nhận); fast/balanced→`adaptivecubic`.

---

## Bài học bắt buộc tuân thủ

1. **Slice-test MỌI key mới** trước khi ship. `brim_object_gap=0.1` từng làm **CLI crash** (không ra gcode). Đã test OK: accel 3000/4000/5000, travel 380.
2. **Một nguồn duy nhất**: `tall_rules(h_mm, mode)` sinh **cả preset lẫn tip**. Trước đây viết tay 2 chỗ → lệch **3 lần liên tiếp**. Thêm rule mới thì thêm vào đây, **đừng** gõ số vào text tip.
3. **Đừng tin ảnh chụp màn hình làm nguồn số** — tôi từng báo động giả "bug lệch thang overhang" vì đọc ảnh bị cuộn cắt mất ô đầu. **Đọc `project_settings.config`**.
4. **Đọc luật trước khi sửa** — suýt phá luật `support_type` đúng vì phán vội từ tip.
5. **`--slice 0` = slice HẾT các khay**, zip xếp **ngược** (plate_3 trước). Luôn chỉ định khay.

---

## Bảo mật — BẤT DI BẤT DỊCH

- **KHÔNG BAO GIỜ** commit `.env`, `printer.local.json`, `filament.local.json`.
- Hostname Tailscale, Access Code, serial, IP máy in **không được xuất hiện trong file tracked**.
- Trước **mọi** `git push`: `git diff --cached | grep -inE "<access-code>|<ip>|<tailscale-host>"` → phải ra rỗng.

---

## Rule theo 3 chế độ đang chạy (vật cao ≥120mm)

| Chế độ | Accel chung | Outer wall | Travel |
|---|---|---|---|
| Nhanh | 5000 | 3000 | 380 |
| Cân bằng | 4000 | 3000 | 380 |
| Đẹp | 3000 | 3000 | 380 |

Nguồn: SparkLab A1 academy (accel<3000, travel<400) + wiki layer-shift. Vật <120mm không dính rule.