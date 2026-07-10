# HANDOVER — 2026-07-10 · A1 Hub: spec + plan auto-optimizer, bộ test vào repo, 4/13 task

**Thư mục:** `d:\56.BambuStudio` · **Repo:** https://github.com/Long0308/LP-BambuLab (public) · **STATUS: IN_PROGRESS**
**Gate xanh:** `npm run verify` → unit `11/11` · e2e `79/79` · pageerror `0` · git sạch, `0 ahead / 0 behind`

---

## 1. Phiên này làm gì

Bắt đầu từ *"tự động tối ưu khi thả file vào hub"* → brainstorm → spec → plan 13 task TDD → chạy tới task 4. Trên đường đi, **số đo bác bỏ 4 khẳng định**, trong đó 2 cái do chính tôi viết ra và đã ship vào preset của user.

---

## 2. Tình trạng HUB hiện tại

`BambuLab-A1-Hub.html` — **199 KB, 1 file offline, 8 tab, 41 luật audit.**

| Tab | Nội dung |
|---|---|
| Tổng quan · Thông số · Quy trình · Tư vấn · Tài nguyên | như cũ |
| **Phân tích file .3mf** | đọc 571 key + mesh thật → 41 luật; đọc time/weight 2 đường (slice_info `<plate>`, fallback gcode nhúng) |
| **Cải thiện (Orca)** | + Variable layer height (3 điều kiện chặn) + bảng đòn bẩy miễn phí/đánh đổi + 8 cặp tăng–giảm + 7 chỗ engine âm thầm sửa + bảng layer↔MPa↔time + card **Wiki vs Cộng đồng** |
| **Kỹ thuật (ETL · Dataflow)** ⟵ MỚI | sơ đồ Extract→Transform→Derive→Validate→Load · vì sao mesh > ảnh · 3 dải góc · ground truth tra ở đâu · **bảng tra 52 key: Trang→Nhóm→Tên hiển thị Bambu→key máy→chế độ** · 4 cạm bẫy |

### Khối `PURE` (dòng ~1917) — chỗ optimizer sẽ sống

```
/* PURE:START */   ← tests/unit/lib/loadPure.js trích khối này chạy bằng node
  geoFeatures()      ✅ ĐÃ CÀI (3308 ký tự) + countIslands()
  printerLimits()    ⬜ stub
  derive()           ⬜ stub
  checkInvariants()  ⬜ stub
  optimize()         ⬜ stub
/* PURE:END */
```

Hub vẫn là **một file HTML offline duy nhất**; harness đọc file, cắt khối giữa 2 marker, `new Function` nó. Không tách file, không mất tính offline.

### Bộ test (đã vào repo — lần trước để scratchpad nên mất sạch)

```
npm test          → node --test "tests/unit/**/*.test.js"   11 pass
npm run e2e       → node tests/e2e/run-all.js               79 pass, pageerror 0
npm run verify    → cả hai
```

| Suite | Nội dung |
|---|---|
| `tests/unit/geoFeatures.test.js` | 11 test, mesh tự dựng biết trước đáp án |
| `tests/e2e/01-smoke` | 8 tab↔8 panel · `support_type` đúng 4 mục & không có `hybrid(auto)` · `support_style` 7 mục · `brim_type` có `auto_brim`+`Painted` · bảng tra ≥50 dòng |
| `tests/e2e/02-analyze` | 9 file `.3mf` thật: luật scarf & overhang khớp **recompute độc lập** từ `project_settings.config` → chống báo oan |
| `tests/e2e/03-time` | 2.x không `<plate>` → "KHÔNG phải lỗi thao tác"; 1.10.x → `3h 56m / 75 g` |
| `tests/e2e/04-fixtures` | **chiều dương** 2 luật LỖI (`scarf-trap.3mf`, `nozzle-02-trap.3mf`) |
| `tests/e2e/report.js` | không phải test — dump config + toàn bộ finding từng file để soi tay |

---

## 3. Bốn khẳng định bị SỐ ĐO bác bỏ

### 3.1 "Variable layer height làm in nhanh hơn" — SAI
Adaptive mặc định thiên mịn: **1155 lớp → 14h41m** so với phẳng 0.20: **750 lớp → 10h44m**. Chậm hơn **37%**.
Nguyên nhân: nó hạ layer ở cả vùng dốc `<25°`, nơi hạ layer **vô ích** — ở `13.5°`, ngay tại sàn `0.08mm` bậc thang vẫn còn `0.33mm`. Chỗ đó phải chữa bằng **ironing + top shell**.
Lọc dải đó ra thì đảo chiều: `STEP_TARGET 0.30mm` → **707 lớp (−6%)**.

### 3.2 "VLH dày layer ở thành đứng là miễn phí" — SAI *(tôi viết ra)*
Miễn phí về **bề mặt**, nhưng lớp dày làm yếu liên kết liên lớp: PLA nozzle 0.4 rơi **52 MPa @0.20 → 48 MPa @0.30** (BigRep). ⇒ kẹp `LH_MAX = 0.25` cho vật chịu lực.

### 3.3 "Đẩy tốc độ vùng khuất tới trần = đòn miễn phí duy nhất" — SAI *(tôi viết ra, và đã ship vào preset)*
Profile stock `0.20mm Standard @BBL A1` (bản cài, **không phải master GitHub**):

```
inner_wall_speed     = 300   trần (PLA Matte) = 244.4  → VƯỢT
sparse_infill_speed  = 270   trần             = 244.4  → VƯỢT
internal_solid_speed = 250   trần             = 261.9  → dưới trần, dư 4.8%
```

Bambu **cố tình** đặt vượt trần rồi để bộ giới hạn lưu lượng ghì về `v_max`. Hai vùng đó **đã chạy hết tốc**.
Preset LP đặt cả hai `= 240` (dưới trần) ⇒ **chậm hơn stock 1.8%**. Tưởng tăng tốc, hoá ra hãm.
**Đã sửa:** bỏ hẳn 2 key (kế thừa stock); `internal_solid_infill_speed` `255 → 260` — chỗ **duy nhất** còn dư, **+4% thật**.

### 3.4 "Thời gian tường ∝ số lớp" — chỉ đúng khi giữ nguyên tốc độ
`lưu lượng = layer × line_width × speed`. Hạ layer một nửa ⇒ được tăng gấp đôi tốc độ mà vẫn dưới trần ⇒ thời gian không đổi.
Thực tế lớp mỏng vẫn lâu vì **tường ngoài bị khoá tốc độ để giữ bề mặt**. Nên: tường ngoài ∝ số lớp · tường trong + infill do **lưu lượng** quyết định.

---

## 4. Ba luật audit từng báo oan — đã sửa (đo: 36 → 22 cảnh báo / 10 file)

| Luật cũ | Vấn đề | Luật mới |
|---|---|---|
| `PLA && bed ≥ 65 → "Bed hơi nóng"` | oan **5/10 file**, trái wiki | theo **diện tích đế**: đế lớn `bed<65` → cảnh báo tăng; đế nhỏ `bed≥65` → nhắc hạ nếu phồng chân |
| `/basic\|generic/ → "Kiểm tra profile nhựa"` | oan **8/10 file** (PLA Basic là nhựa hợp lệ) | **lệch combobox ↔ nhựa trong file** → THÔNG TIN |
| `Tốc độ VƯỢT trần` = CẢNH BÁO | oan **8/10 file** — đó là **thiết kế** của stock | hạ xuống THÔNG TIN + giải thích tốc độ THẬT = `v_max` |

**Luật mới:** đế `>150 cm²` + infill `Grid/Triangle` → đổi `Gyroid ≤25%` (wiki *Warping*: Grid/Triangle tạo ứng suất tuyến). Bắn đúng **3 file thật** (`A1_X2026`: grid 30% trên đế 207×204mm).

Nguồn: Firecrawl **cả hai phía**. Chính wiki Bambu tự nói hai giọng về bed (trang *Warping* bảo tăng lên 55–65; trang *Textured PEI troubleshooting* bảo quá cao → elephant foot + clog). Reddit r/BambuLab đồng thuận **65 là chuẩn** textured PEI. → luật theo diện tích đế dung hoà cả ba.

---

## 5. Preset

### ✅ `boxson-PLAMatte-Decor-*.json` — đã sửa xong (36 + 11 key)
- bỏ `inner_wall_speed`, `sparse_infill_speed` (kế thừa stock)
- `internal_solid_infill_speed = 260`
- `support_style = tree_hybrid`, `enable_prime_tower = 0` (gỡ 2 blocker VLH)
- `seam_slope_type = all` **và** `filament_scarf_seam_type = all`
- filament: **bỏ** `hot/textured_plate_temp = 60` (ngược cả 3 nguồn với đế 265 cm²) → kế thừa stock **65**

### ❌ `Body14-PLAMatte-Decor-{BALANCED,FAST}-*.json` — **CÒN LỖI, chưa sửa**
(commit `c8dc164` của user, chưa động vào)

```
BALANCED 0.2 :  I2  top_shell_layers=4 → engine tự nâng 5 (kế thừa top_shell_thickness=1.0)
                tự hãm: inner_wall_speed=240 < trần 244
                tự hãm: sparse_infill_speed=240 < trần 244
FAST 0.24    :  I2  top_shell_layers=4 → engine tự nâng 5
                I1  inner_wall_speed=240 > trần 204
                I1  sparse_infill_speed=240 > trần 204
                I1  internal_solid_infill_speed=255 > trần 218
```

⇒ Khoản tiết kiệm *"top 4"* trong `Body14-Optimize-Analysis.md` (combo −36%) **chưa bao giờ xảy ra**.
Doc đó còn ghi sai nhựa: `GFA18` là **PLA Lite** (maxvol 16, density 1.40), không phải PLA Matte (`GFA01`, maxvol 22, density 1.32). Con số `190 mm/s` trong §3 tính từ maxvol của Lite.

---

## 6. Spec & Plan (đã duyệt, đã commit)

- **Spec:** `docs/superpowers/specs/2026-07-10-hub-auto-optimizer-design.md` (14 mục)
  Kiến trúc **dataflow**: `Extract → Transform (7 tầng) → Derive → Validate (7 bất biến) → lặp tới điểm bất động (≤3 vòng) → Load`.
  Tầng: `0` hiệu chuẩn (chỉ phát hiện, **cấm bịa K**) · `1` first layer (khoá) · `2` warping (khoá, ghi đè tầng 5) · `3` bề mặt · `3b` độ bền · `4` overhang/bridge/VLH · `4b` võng mặt trên · `5` thời gian.
- **Plan:** `docs/superpowers/plans/2026-07-10-hub-auto-optimizer.md` — 13 task TDD, mỗi task có test code thật + lệnh chạy thật.

### 7 bất biến (`checkInvariants`) — engine âm thầm sửa gì khi vỡ

| # | Bất biến | Engine làm gì |
|---|---|---|
| I1 | `flow ≤ max_volumetric_speed` | tự hạ tốc, số đã nhập vô nghĩa |
| I2 | `top_shell_layers × layer ≥ top_shell_thickness` | **tự tăng số lớp đặc** |
| I3 | `layer ∈ [min,max]` | kẹp |
| I4 | `filament_scarf_seam_type == seam_slope_type` | **scarf tắt âm thầm** |
| I5 | VLH ⇒ support không organic ∧ prime tower tắt | từ chối VLH |
| I6 | `elefant_foot_compensation > 0 ⇒ brim_object_gap = 0` | brim tách khỏi vật |
| I7 | dùng `filament_*` overhang ⇒ `override_process_overhang_speed = 1` | giá trị filament bị bỏ qua |

---

## 7. Tiến độ 13 task

| Task | Trạng thái | Commit |
|---|---|---|
| 1 · sửa luật audit (mở rộng: 3 luật + luật grid + fixture nozzle-0.2 + card wiki-vs-cộng-đồng) | ✅ | `d0b656d` |
| 2 · marker PURE + harness `loadPure` | ✅ | `ce14d80` |
| 3 · 6 mesh fixture | ✅ | `a65cd44` |
| 4 · `geoFeatures()` TDD | ✅ | `48ad61a`, `a8cfa32` |
| **5 · `printerLimits()`** | ⬜ **TIẾP THEO** | |
| 6 · `derive()` + 7 bất biến | ⬜ | |
| 7–10 · `optimize()` 6 tầng + vòng lặp điểm bất động | ⬜ | |
| 11 · golden test 6 dạng vật | ⬜ | |
| 12–13 · UI bảng quyết định + xuất preset + e2e optimizer | ⬜ | |

### `geoFeatures()` — số đo trên 6 dạng vật (đã khoá bằng test)

| Vật | overhang% | firstArea cm² | islands | θ<25° | 25–50° | ≥50° | oh 75–90° |
|---|---|---|---|---|---|---|---|
| hộp lớn phẳng 200×150×20 | 0.00 | 300.0 | 1 | 0 | 0 | 0 | 0 |
| cột cao mảnh 20×20×150 | 0.00 | 4.0 | 1 | 0 | 0 | 0 | 0 |
| cầu R40 | 14.02 | **0.0** | **0** | 21.3 | 48.5 | 114.7 | 1.5 |
| vase côn loe | 0.00 | 50.2 | 1 | 0 | 0 | **449.7** | 0 |
| trụ đứng | 0.00 | 50.2 | 1 | 0 | 0 | 0 | 0 |
| bridge 2 chân | 12.50 | 8.0 | **2** | 0 | 0 | 0 | **20.0** |

---

## 8. Next Steps

- [ ] **Task 5 + 6** (ghép chặt — `derive` cần `printerLimits`): `printerLimits()` trả `vmax` theo từng vùng + `layerMin/Max` = giao của `[machine min,max]` và quy tắc 25–75% nozzle; `derive()` + `checkInvariants()` 7 bất biến. Test code đã viết sẵn trong plan Task 5, 6.
- [ ] **Task 7–10**: `optimize()` 6 tầng. Lưu ý 4 lỗi prototype đã bắt trước: cầu bị hạ accel oan (tách *tiếp xúc bé → brim* khỏi *cao mảnh → giảm accel*); cầu 14% overhang phải `tree(auto)` không `tree(manual)`; vase 449 cm² `θ≥50°` phải kích hoạt VLH; bridge cần `ohBins` tách dải.
- [ ] **Sửa 2 preset `Body14-*`** (mục 5) + đính chính `Body14-Optimize-Analysis.md` (GFA18 = PLA **Lite**).
- [ ] **Task 12**: hub chưa có `renderPlan()` / nút xuất preset tối ưu — mới chỉ có phần tài liệu.
- [ ] Cân nhắc: `bambu_web.py` serve hub ở `/hub` (một server cho cả dashboard + phân tích, rule engine giữ **một nguồn** trong JS).

---

## 9. Bẫy đã biết — đừng dẫm lại

1. **`master` GitHub ≠ bản cài.** Luôn tra `C:\Program Files\Bambu Studio\resources\` và `PrintConfig.cpp` local.
2. **Test phải nằm trong repo.** Bộ e2e cũ (63 test) để ở scratchpad → bị dọn → mất vĩnh viễn, không tái lập được.
3. **Luật chỉ chứng minh chiều âm là luật chết mà không ai biết.** Không file Downloads nào rơi vào ca scarf-trap (`boxson.3mf` đã bị xoá) → phải tự dựng fixture. Tương tự luật nozzle-0.2.
4. **`node --test <thư mục>` không chạy ở Node 25** — ném `Cannot find module`. Dùng `node --test "tests/unit/**/*.test.js"`.
5. **`islands = 0` cho vật cong chạm khay 1 điểm** (cầu). Tầng 2 phải dùng `firstArea_cm2` để bắt `tinyContact`, **không** dựa vào `islands ≥ 1`. Đã khoá bằng test.
6. **Bambu Studio 2.x không nhúng kết quả slice vào `Save Project`** (kiểm 16 file: `1.10.x` có `<plate>` 3/3, `2.x` không 6/6). Chỉ `File ▸ Export ▸ Export plate sliced file` mới có.
7. **Chọn filament đuôi `@BBL A1 0.2 nozzle` đổi luôn printer preset** → maxvol `22 → 2`, line width `0.45 → 0.22`.
8. **`support_type` `(manual)` không sinh support nào** nếu chưa sơn enforcer (`PrintConfig.cpp:5184`). Preview trống là **đúng**.
9. **Hook chặn `git commit`** nếu command chứa `-n` ở bất kỳ đâu (kể cả `grep -n`) — nó tưởng là `--no-verify`.

---

## 10. Ground truth tra ở đâu

| Cần gì | Ở đâu |
|---|---|
| Số liệu preset thật | `C:\Program Files\Bambu Studio\resources\profiles\BBL\{process,filament,machine}\*.json` (theo chuỗi `inherits`) |
| Mọi key + shape | `Metadata/project_settings.config` trong bất kỳ `.3mf` (571 key) — shape-oracle |
| Enum · default · mode | `PrintConfig.cpp` (repo, AGPL — xem `NOTICE`) |
| Bố cục UI (Trang→Nhóm) | `Tab.cpp` — `add_options_page()` + `new_optgroup()` + `append_single_option_line()` |
| Chuỗi UI đã dịch | `resources\i18n\en\BambuStudio.mo` |
| Đo thời gian thật | `reslice-benchmark.ps1` (Bambu Studio CLI) |
