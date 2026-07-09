# HANDOVER — 2026-07-09 · A1 Hub: audit toàn bộ + xuất preset Bambu + case study `boxson.3mf`

**Thư mục:** `d:\56.BambuStudio` · **STATUS: IN_PROGRESS**
**Verify:** E2E `63/63` · validator preset `0 lỗi` · hub-vs-preset-gốc `0 lệch` · 9/9 file `.3mf` parse OK

---

## 1. Phạm vi phiên này
Bắt đầu từ "bảng hãng phải chỉ điền GIÁ TRỊ NÀO VÀO Ô NÀO" → mở rộng thành: audit toàn bộ hub, sửa 12+ bug, dựng bộ xuất preset **import được vào Bambu Studio**, và tối ưu cấu hình thật cho `boxson.3mf`.

---

## 2. Hub — tính năng đã thêm
| Tính năng | Chi tiết |
|---|---|
| Panel hãng → **clone Filament Settings** | 2 tab (Filament/Cooling), đủ **5 tấm in** (Initial/Other), badge `★ cần điền` vs `để mặc định`, tên EN + giải thích VN ↑↓ |
| **Process clone** có badge | `★ theo mục tiêu` · `◆ theo nhựa` · `nên chỉnh` · `để mặc định` |
| **OPTIONS** cho mọi enum | 22 sparse-infill pattern, ironing, seam, wall gen, top/bottom, support, brim, fuzzy… (Firecrawl + PrintConfig.cpp) |
| **KHUYẾN NGHỊ TOÀN BỘ** | Printer→Filament→Process→Objects + 2 bảng reco + base preset đúng tên Bambu |
| Đồng bộ combobox ↔ stepper | đổi Nhựa → mở bước 2 · đổi Mục tiêu → mở bước 3 |
| **Bước 3 = Nhựa ◆ + Mục tiêu ★ song song** | `mergeOv()` + `MAT_WINS` (vd ironing: **vật liệu thắng**) |
| Phân tích `.3mf` **goal-aware** | bảng "So với KHUYẾN NGHỊ" ✓/⚠, tự cập nhật khi đổi combobox |
| **Ironing advisor** | tự tính thời gian thêm: `A_top / (speed × spacing)` — boxson: **156 cm² → +58 phút** |
| **Xuất 2 preset Bambu** | schema user-preset chuẩn, tên `BambuLab - <nhựa> - LP - <mục tiêu>` |

---

## 3. Bug đã fix (hub)
1. `.3mf` crash — `Math.max(...mảng vài trăm nghìn phần tử)` → stack overflow. Dùng vòng lặp `mx()/mn()`.
2. `.3mf` **ZIP64** — `unzip()` đọc quá biên (`Offset is outside the bounds of the DataView`). Viết lại: bounds-guard + ZIP64 EOCD + **fallback quét local file header**. 8/8 file Downloads parse OK.
3. Bảng Process trống — lặp `GROUPS[i][3]` sai 1 tầng (`[[subname, rows],…]`).
4. `stat()` esc giá trị → HTML lộ raw. Thêm `statH()`.
5. `within()` range lấy `nums[0..1]` → `"220 (215–230)"` báo sai. Dùng **min/max** của mọi số.
6. `within()` không chuẩn hoá `-` `/` → `inner-outer-inner wall` vs `Inner/Outer/Inner` báo ⚠ oan.
7. `nzr` `"220 (→255)"` hiện cả Min lẫn Max = `220 (→255)`.
8. Ironing advisor lấy nhựa từ **file** thay vì **combobox**.
9. Warping/stair-stepping/I-O-I không có luật → thêm 4 luật audit (xem §5).
10. Export preset sai schema (có `type`/`instantiation`, thiếu `version`) → **import ra "0 configs"**.
11. `&amp;` double-escape ở guide Density.
12. A11y: `role=tab` / `aria-selected` / `role=tabpanel`.

---

## 4. ⚠️ Những điều TÔI ĐÃ NÓI SAI — đã sửa bằng ground truth
| Chủ đề | Tôi nói | **Sự thật** (preset/source trên máy) |
|---|---|---|
| PLA Matte max vol | 18–21, "22 quá cao" | **22** (đúng của Bambu) |
| PLA Matte fan / bed | 100% / 55–60 | **80** / **65** |
| PLA Basic fan / density | 100% / 1.24 | **80** / **1.26** |
| **PLA Lite density** | 1.24 | **1.40** ← lệch 13% khi ước tính KL |
| PLA Lite bed / maxvol | 55 / 15–20 | **65** / **16** |
| **PETG HF nozzle** | 250–255 | **240** (initial 230) |
| PETG maxvol / flow | 12–16 / 0.95 | **18** / **0.94** |
| Tab Filament Settings | "Setting Overrides chỉ Orca có" | Bambu **2.07 CÓ** `Setting Overrides` + `Multi Filament` |
| Cấu hình boxson | outer 100 · accel 2500/3500 · wall 3 · layer 0.16 | → **31h54m / 716g** (×3 time). Preset gốc **luôn** dùng `outer 200 · accel 5000/6000` |

> **Bài học:** source `master` trên GitHub ≠ bản user đang cài. Luôn ưu tiên **file cài local + ảnh chụp thật**.

---

## 5. Luật audit mới trong `auditFile()`
- `[LỖI]` **Inner/Outer/Inner nhưng < 3 wall** → thứ tự đó **vô hiệu** (cần ≥3 wall) — verified Firecrawl OrcaSlicer wiki.
- `[CẢNH BÁO]` **Lộ vân bậc thang**: nếu `slope>3%` & `layer≥0.2` → nếu `vert>60%` khuyên **Variable layer height** thay vì hạ layer toàn cục.
- `[CẢNH BÁO]` **Đế lớn → warping**: `dx×dy > 150 cm²` & brim auto/no → đổi `Outer brim only` 5–8mm.
- `[CẢNH BÁO]` **Precise wall bị bỏ qua** nếu `precise_outer_wall=1` & order ≠ `inner wall/outer wall`. (`precise_outer_wall` = `comDevelop`, **ẩn** ở Advanced, default `false`.)
- `[T.TIN]` Support `(auto)` → khuyên `(manual)` + painting.
- Bỏ 3 cảnh báo nhiễu (bed 60 "nóng", profile Matte "sai profile", ironing tắt).

Test: 9/9 file `.3mf` → luật Precise wall bắn **đúng 1 lần** (chỉ boxson), 0 false positive.

---

## 6. Case study `boxson.3mf`
**Hình học (mesh thật):** `182.8 × 151.8 × 150.0 mm` · 1614 cm³ · **thành đứng 79%** · mặt cong **6%** · mặt phẳng trên 6% · overhang 10%

| | Baseline (0.28 Extra Draft) | Bản tôi làm hỏng | **Chốt** |
|---|---|---|---|
| Layer | 0.28 (536 lớp) | 0.16 (936) | **0.20 (750)** |
| Wall / order | 2 / Inner-Outer | 3 / I-O-I | **2 / Outer-Inner** |
| Outer speed · accel | 200 · 5000/6000 | **100 · 2500/3500** ❌ | **kế thừa (200 · 5000/6000)** |
| Infill | 15% grid | 15% gyroid | **10% adaptive cubic** |
| **Thời gian** | 10h37m | **31h54m** | **10h44m** (đo thật) |
| **Nhựa** | 568 g | 716 g | **469 g** (−17%) |

### Vật lý rút ra (đo từ preset + `max_volumetric = 22`)
- **Time TƯỜNG ∝ số lớp** (∝ 1/layer_height) → hạ layer toàn cục **chắc chắn** đội thời gian.
- **Time INFILL/SOLID ∝ THỂ TÍCH** (bị chặn lưu lượng, `0.2×0.45×270 = 24.3 > 22`) → **không** phụ thuộc layer_height.
- ⇒ Đòn tiết kiệm thật = **giảm infill**. Đòn cải thiện bo cong = **Variable layer height** (chỉ vùng cong).
- ⇒ **Không bao giờ** hạ `outer_wall_speed`/`acceleration` để "mua" chất lượng.

### Phát hiện: scarf seam có **2 công tắc**
`seam_slope_type` (Process) = `external` **nhưng** `filament_scarf_seam_type` (Filament) = `none` → **filament override thắng → scarf TẮT** → seam lộ. Và lòng chảo là **hole** ⇒ phải dùng `all` (*Contour and hole*), không phải `external`.

---

## 7. File preset (import được)
- `boxson-PLAMatte-Decor-process.json` → **`BambuLab - PLA Matte - LP - Decor 0.20mm`** (inherits `0.20mm Standard @BBL A1`, 33 key)
- `boxson-PLAMatte-Decor-filament.json` → **`BambuLab - PLA Matte - LP - Decor`** (inherits `Bambu PLA Matte @BBL A1`, 15 key)

**Schema user-preset (đã verify từ `%AppData%\BambuStudio\user\<uid>\`):**
KHÔNG có `type` / `instantiation` / `compatible_printers`. BẮT BUỘC `from:"User"` + `inherits` + `name` + **`version`** (`2.7.0.8`), và
`print_settings_id` + `print_extruder_id` + `print_extruder_variant` (process) · `filament_settings_id` + `filament_extruder_variant` (filament).
Shape (array vs scalar) phải khớp `project_settings.config`. Thiếu `version` → **"0 configs imported"**.

**Nạp:** `File ▸ Import ▸ Import Configs…` → Ctrl+chọn **cả 2 file** → "2 configs imported" → rồi **CHỌN preset ở dropdown** (import ≠ áp dụng).

---

## 8. GROUND TRUTH — tra ở đâu (đừng đoán)
| Cần gì | Ở đâu |
|---|---|
| Số liệu preset thật | `C:\Program Files\Bambu Studio\resources\profiles\BBL\{process,filament}\*.json` (theo chuỗi `inherits`) |
| Schema user preset | `%AppData%\BambuStudio\user\<uid>\{process,filament}\*.json` |
| **Mọi key + shape** | `project_settings.config` trong bất kỳ `.3mf` (571 key) — dùng làm shape-oracle |
| Enum values + `mode` | `PrintConfig.cpp` (GitHub raw hay 429 → đọc bản cài local) |

Script tái dùng (scratchpad): `genpreset.py` (sinh preset), `validate.js` (enum+shape+đối chiếu), `e2e.js` (63 test), `batchcheck.js` (chạy luật trên 9 file).

---

## 9. Next Steps
- [ ] **Seam**: import preset mới (`filament_scarf_seam_type = all` + `seam_slope_type = all`) → Slice → xác nhận seam trên lòng chảo đã biến mất.
- [ ] **Support**: đổi `Type` từ `Tree(auto)` → **`Tree(manual)`** + tick **`On build plate only`**. (Preset mới đã set sẵn; file `.3mf` hiện vẫn `tree(auto)`.)
- [ ] **Hub — ghi chú từng loại**: thêm ghi chú "khi nào dùng" cho **từng option** của `Support type`, `Support style`, `Brim type` (giống cách đã làm cho sparse infill).
- [ ] **Hub — Variable layer height**: chưa có mục nào nhắc; nên thêm luật + hướng dẫn (đây là công cụ chính cứu bo cong).
- [ ] **"Lỗi bề mặt"** user báo (ảnh preview) — chưa chẩn đoán xong. Nghi: seam lộ (do scarf bị tắt) + vân bậc thang lòng chảo. Cần user mô tả rõ.
- [ ] Xác nhận `layer_height` thực tế đang chạy (slider hiện **750 lớp @ Z150** → 0.20mm, dù tên preset ghi 0.24mm ở lần trước).
- [ ] Hub: nút "Xuất 2 preset" mới chưa được test tải file thật trong trình duyệt (mới test hàm sinh JSON).
