# Auto-optimizer cho BambuLab-A1-Hub — thiết kế

**Ngày:** 2026-07-10 · **Trạng thái:** đã duyệt thiết kế, chờ viết plan

## 1. Mục tiêu

Thả một file `.3mf` vào hub → hub tự sinh **cấu hình tối ưu**, xếp theo đúng thứ tự ưu tiên:

1. First layer luôn bám bàn
2. Không cong vênh (warping)
3. Mặt phẳng đẹp, bo cong mịn
4. Rồi mới tối ưu thời gian

Mọi khuyến nghị **phải ánh xạ về một key preset có thật** trong Bambu Studio. Không có lời khuyên suông.

## 2. Ngoài phạm vi

- Không nhận `.stl` / `.step`. Chỉ `.3mf` (và `.gcode.3mf`), vì `.3mf` mang sẵn 571 key config → biết chính xác nozzle, trần lưu lượng, line width.
- Không tự đoán giá trị hiệu chuẩn (`pressure_advance`, `filament_flow_ratio`). Xem Tầng 0.
- Không đánh đổi chất lượng lấy tốc độ. Thời gian chỉ được cắt bằng đòn bẩy không chạm bề mặt nhìn thấy.
- Không tự ghi `.3mf` đã vá. Đầu ra là preset + bảng Height range.

## 3. Vì sao không cần "nhìn ảnh"

Ảnh render **được sinh ra từ** lưới tam giác; nó là phép chiếu 2D làm mất chiều sâu, mặt khuất và góc thật. Hub đọc thẳng lưới, nên có **nhiều** thông tin hơn ảnh.

Cái thiếu ở hub hiện tại không phải "mắt" mà là **thông tin vị trí bị vứt đi**: `meshStats` rút toàn bộ mesh xuống 14 số vô hướng. Nó biết `Body 14` có 0.32% overhang nhưng không biết chỗ đó nằm ở `Z 130–150mm`.

Bốn tiêu chí trên đều cần **đặc trưng có toạ độ**, và không cái nào đo được từ ảnh:

| Tiêu chí | Đo gì |
|---|---|
| First layer | diện tích tiếp xúc tại `z = zmin`, số đảo rời |
| Warping | diện tích + đường chéo đế, tỉ lệ cao/mảnh |
| Bo cong | histogram `Z × góc dốc`; bậc thang `= layer_h / tan θ` |
| Mặt phẳng | các cao độ có mặt phẳng trên, diện tích từng mảng |

Ảnh chỉ hơn ở việc đoán **ý đồ** ("lọ hoa" hay "giá đỡ chịu lực"). Thứ đó hỏi thẳng qua combobox *Mục tiêu*, chính xác hơn đoán.

## 4. Kiến trúc

```
.3mf → unzip → { ps: 571 key, meshes }
                  │
                  ├── geoFeatures(meshes) → F      thuần hình học, không biết Bambu là gì
                  ├── printerLimits(ps)   → L      nozzle, min/max layer, maxvol, line width
                  │
                  └── optimize(F, L, mat, goal) → { deltaProcess, deltaFilament, vlhRanges[], reasons[], conflicts[] }
                            │
                            ├── renderPlan()       bảng quyết định + con số + nguồn
                            ├── downloadPresets()  tái dùng downloadBothPresets()
                            └── renderVlhTable()   Z-range → layer height
```

Ranh giới bắt buộc:

- **`auditFile()`** (đã có) trả lời *"file hiện tại sai gì"*. **`optimize()`** trả lời *"file nên là gì"*. Không trộn.
- `geoFeatures` không tham chiếu khái niệm nào của Bambu → test bằng mesh tự dựng biết trước đáp án.
- `optimize` là **hàm thuần**: `(F, L, mat, goal) → plan`. Không đụng DOM → test bằng `node`, không cần puppeteer.

## 5. `geoFeatures`

Giữ 14 số cũ, thêm:

| Trường | Định nghĩa |
|---|---|
| `firstArea_cm2` | diện tích mặt hướng xuống có trọng tâm `z ≤ zmin + 0.05` |
| `islands` | số đảo rời ở lát cắt `z = zmin` (rasterize lưới 0.5mm) |
| `baseDiag_mm` | đường chéo bbox của các mặt đó |
| `topPlateaus[]` | `{z, area_cm2}` cho từng mảng phẳng trên (`cosθ > 0.985`) |
| `zSlope[]` | `{z0, z1, area, thetaP10}` — bin Z 10mm, `thetaP10` = phân vị 10 của góc dốc theo diện tích |
| `ohBins` | diện tích mặt hướng xuống, chia dải `45–60°`, `60–75°`, `75–90°`, kèm Z |
| `down_cm2`, `base` | đã có (mặt đáy **không** tính là overhang) |
| `thinWall_cm2` | bề dày `< 2 × line width` |

### Ba dải góc — lấy từ số đo, không từ cảm tính

Bậc thang ngang `= layer_h / tan θ`, với `θ` = góc mặt so với phương ngang. Sàn/trần layer của A1 nozzle 0.4 là `[0.08, 0.28]` (machine profile).

| θ | Bậc @0.28 | Bậc @0.08 (sàn) | Kết luận |
|---|---|---|---|
| 13.5° | 1.17mm | **0.33mm** | hạ layer **vô ích** → ironing + top shell |
| 19° | 0.81mm | 0.23mm | vô ích |
| 33.7° | 0.42mm | 0.12mm | hạ layer **có tác dụng** |
| 45° | 0.28mm | 0.08mm | có tác dụng |
| 60° | 0.16mm | 0.05mm | gần đứng → **dày lên**, miễn phí |

⇒ `θ < 25°` gần phẳng · `25° ≤ θ < 50°` cong thật · `θ ≥ 50°` gần đứng.

Đây chính là chỗ Bambu Adaptive sai: nó hạ layer ở vùng gần phẳng, nơi layer không cứu được gì.

## 6. `optimize()` — thang 6 tầng

Tầng thấp thắng. Tầng ≤ 2 **khoá** key của mình. Khi tầng sau muốn ghi đè, hub ghi vào `conflicts[]` chứ không im lặng.

### Tầng 0 — Hiệu chuẩn (phát hiện, KHÔNG bịa giá trị)

`pressure_advance`, `enable_pressure_advance`, `filament_flow_ratio` đều là key thật (mode `comAdvanced`). `adaptive_pressure_advance` **không tồn tại** trong Bambu (đó là của OrcaSlicer).

Ba giá trị này **đo trên máy**, không suy ra được từ tam giác. Hub chỉ được:

- `enable_pressure_advance = 0` → cảnh báo, chỉ đường chạy **Flow Dynamics Calibration**.
- `filament_flow_ratio` bằng đúng giá trị stock của profile → kết luận *"chưa hiệu chuẩn"*, chỉ đường chạy **Flow Rate Calibration**.
- **Cấm tuyệt đối** đề xuất một con số K cụ thể.

### Tầng 1 — First layer & bám bàn (không ai được ghi đè)

| Key | Điều kiện | Nguồn |
|---|---|---|
| `curr_bed_type` | phải khớp khay vật lý | wiki: chọn sai làm mất bù nozzle 0.04mm của Textured PEI |
| `close_fan_the_first_x_layers = 3` | luôn | wiki *"First layer not sticking"* |
| `initial_layer_speed = 25` | luôn | — |
| `initial_layer_print_height = clamp(layer_height + 0.04, 0.20, 0.28)` | luôn | lớp đầu dày hơn để bám |
| `textured_plate_temp_initial_layer` / `hot_plate_temp_initial_layer` | theo khay | — |

### Tầng 2 — Warping (ghi đè tầng 5)

| Key | Điều kiện | Nguồn |
|---|---|---|
| `brim_type = outer_only`, `brim_width = 8` | `firstArea > 150 cm²` **hoặc** `baseDiag > 150 mm` | wiki: PLA cong góc → brim 8–10mm |
| `brim_type = brim_ears` | `islands > 1` và mỗi đảo nhỏ | wiki *"Sharp corners popping up"* → Brim type `Painted` |
| `sparse_infill_pattern = gyroid`, `sparse_infill_density ≤ 25%` | đế lớn (như trên) | wiki: *"Large flat model warping → Gyroid ≤25%"*; Grid/Triangle tạo ứng suất tuyến |
| `textured_plate_temp = 65` | PLA trên Textured PEI, đế lớn | wiki: đích 55–65°C; A1 khung hở + phòng < 20°C thì +10°C |
| `default_acceleration`, `outer_wall_acceleration` −20…30% | `aspect > 3` | wiki *"Tall thin model collapse"* |
| `brim_object_gap` ↔ `elefant_foot_compensation` | phải nhất quán | wiki Brim: EFC tạo khe hở giữa brim và vật |

**Tách bạch hai điều kiện** (lỗi đã lộ ra khi thử hình cầu): *tiếp xúc bé → brim* và *cao mảnh → giảm accel* là **hai luật khác nhau**. Hình cầu có `firstArea = 0` nhưng `aspect = 1.0`, không được hạ acceleration.

### Tầng 3 — Mặt phẳng & bề mặt nhìn thấy

- `topPlateaus` tổng > 12% diện tích và nhựa **không** phải Matte → `ironing_type = top surfaces`.
- `zSlope` có vùng `θ < 25°` **> 5 cm²** → `top_shell_layers = 5`, `top_surface_pattern = monotonicline`, `top_surface_speed = 150`. **Không** hạ layer ở đây.
- Vật có lỗ/lòng chảo → `seam_slope_type = all` **và** `filament_scarf_seam_type = all`.
- `thinWall_cm2 > 0` → `wall_generator = arachne`.
- **Đọc** `wall_loops` từ config hiện có (tầng này không ghi nó): `≥ 3` → `wall_sequence = inner wall/outer wall/inner wall`; `= 2` → `outer wall/inner wall`.
- **Cấm chạm** `outer_wall_speed` và `outer_wall_acceleration`.

### Tầng 4 — Overhang, bridge, bo cong

`ohBins` phải tách dải, vì mặt 90° (bắc cầu) khác hẳn mặt dốc 60°:

- `ohBins["75–90°"] > 2 cm²` → `enable_overhang_speed = 1`, đặt `bridge_speed`, `overhang_fan_speed = 100`.

**Support — ba khoảng, không có vùng xám** (`down` = overhang thật, đã trừ mặt đáy):

| `down` | Quyết định | Vì sao |
|---|---|---|
| `≤ 2%` | `enable_support = 0` | tự đỡ được (đặt ở tầng 5) |
| `2% < down ≤ 8%` | `enable_support = 1`, `support_type = tree(manual)` | ít overhang + đồ trang trí → chỉ đỡ chỗ sơn, không để sẹo. Hub **phải** kèm cảnh báo: `(manual)` không sinh gì nếu chưa sơn enforcer (`PrintConfig.cpp:5184`) |
| `> 8%` | `enable_support = 1`, `support_type = tree(auto)` | quá nhiều overhang để sơn tay; không có support là hỏng |

- Bo cong: `zSlope` → `vlhRanges[]` (mục 7). Kích hoạt khi `Σ area(25° ≤ θ < 50°) > 3 cm²` **hoặc** `Σ area(θ ≥ 50°) > 20 cm²` — vế sau là cơ hội **dày layer miễn phí** (vase côn loe có 449 cm² ở dải này).
- Khi có `vlhRanges` → gỡ hai blocker: `support_style ≠ tree_organic` (đặt `tree_hybrid`), `enable_prime_tower = 0`.

### Tầng 5 — Thời gian, chỉ đòn bẩy miễn phí

- `inner_wall_speed`, `sparse_infill_speed`, `internal_solid_infill_speed` → sát trần `v_max = maxvol / (layer_height × line_width)`, chừa ~2% biên.
- Overhang thật `≤ 2%` → `enable_support = 0`.
- `enable_prime_tower = 0` khi in một màu.
- **Không được** đổi `sparse_infill_pattern` nếu tầng 2 đã khoá `gyroid`.

## 7. Bảng Height range (VLH)

`adaptive_layer_height` nằm trong `static std::set<std::string> ignore` của `PrintConfig.cpp` ⇒ **không set được bằng preset**. Phải bật tay trên object; nó lưu ở `layer_config_ranges` trong `.3mf`. Vì vậy đầu ra là **bảng Z-range** để người dùng nhập vào *Height range Modifier*.

Thuật toán, cho mỗi bin `Z`:

```
θ = thetaP10 của bin
nếu θ ≥ 50°           → layer = max_layer_height          (0.28)   ← miễn phí
nếu 25° ≤ θ < 50°     → layer = clamp(STEP_TARGET × tan θ, 0.08, 0.28)
nếu θ < 25°           → layer = layer_height gốc           (không hạ)
bin không có mặt nghiêng → layer = max_layer_height
```

Gộp các bin liền kề cùng `layer`. Kẹp trong `[min_layer_height, max_layer_height]` đọc từ machine profile.

Đường đánh đổi đã **đo trên `Body 14`** (phẳng 0.20 = 750 lớp):

| `STEP_TARGET` | Không lọc `<25°` | **Có lọc `<25°`** |
|---|---|---|
| 0.15mm | 1432 lớp (+91%) | 1057 (+41%) |
| 0.20mm | 1232 (+64%) | **857 (+14%)** |
| 0.30mm | 1057 (+41%) | **707 (−6%)** |

Tham chiếu: Bambu Adaptive mặc định cho ra **1155 lớp (+54%)** → `14h41m` so với `10h44m` của phẳng 0.20. Nó chậm hơn 37% chứ không nhanh hơn.

`STEP_TARGET` là tham số hiển thị cho người dùng, mặc định `0.20mm`, kèm bảng trên.

## 8. Đầu ra

1. **Bảng quyết định** — mỗi dòng: `key · giá trị · tầng · con số hình học dẫn tới nó · nguồn` (`PrintConfig.cpp:<dòng>` hoặc URL wiki).
2. **Hai file preset `.json`** import được (tái dùng `downloadBothPresets`).
3. **Bảng Z-range** cho *Height range Modifier*.
4. **`conflicts[]`** — mọi lần một tầng bị chặn đều hiện ra.
5. Thời gian luôn ghi `≈` và kèm lệnh chép sẵn `reslice-benchmark.ps1` để đo thật bằng Bambu Studio CLI. Hub **không bao giờ** hiển thị số ước tính như thể đã đo.

## 9. Kiểm chứng

**Unit — `geoFeatures`.** Mesh tự dựng biết trước đáp án: hộp `100×100×50` (`down = 0`, `base = 100 cm²`, `top = 100 cm²`), hình cầu (phân bố `θ` đối xứng).

**Golden — 6 dạng vật.** Prototype đã chạy và **tìm ra 4 lỗi trước khi viết code**:

| Dạng | Đế | Aspect | Overhang thật | Kỳ vọng |
|---|---|---|---|---|
| Hộp lớn `200×150×20` | 300 cm² | 0.13 | 0% | brim 8mm · gyroid · bàn 65 · no support |
| Cột cao mảnh `20×20×150` | 4 cm² | 7.5 | 0% | brim 8mm · accel −25% |
| Cầu `R40` | 0 cm² | 1.0 | 14% | brim (tiếp xúc bé) · support `tree(auto)` · **không** hạ accel |
| Vase côn loe | 50 cm² | 1.36 | 0% | auto brim · VLH dày (449 cm² mặt `θ ≥ 50°`) |
| Trụ đứng | 50 cm² | 1.88 | 0% | auto brim |
| Bridge 2 chân | 8 cm² | 3.0 | 12.5% | `bridge_speed` · `overhang_fan_speed` |

Đổi luật mà bảng này đổi ⇒ phải giải trình trong PR.

**Regression.** Giữ `e2e 63/63`, `newrules` 10/10 file thật với 0 báo oan, `validate.js` 0 key sai.

## 10. Những điều đã học và đã sửa trong phiên trước

Ghi lại để không lặp:

- `support_type` chỉ có **4** giá trị (`PrintConfig.cpp:5187–5190`). Không có `hybrid(auto)` — `hybrid` là một *style*.
- `filament_scarf_seam_type` nằm ở trang *Filament*, **không có checkbox override**, default `none` ⇒ luôn đè `seam_slope_type` ⇒ tắt scarf âm thầm. Còn 13 key retraction + 7 key overhang ở trang *Setting Overrides* thì **có** checkbox (`nil` = không đè), và nhóm overhang còn bị chặn bởi công tắc tổng `override_process_overhang_speed`.
- Bambu chặn *"Variable layer height is not supported with Organic supports"*, mà `support_style = Default` lại tự chọn organic cho tree support.
- *"Prime tower does not work when Adaptive Layer Height is on"*, và `fdm_process_common` đặt `enable_prime_tower = 1`.
- Bambu Studio **2.x không nhúng kết quả slice** vào `Save Project` (kiểm trên 16 file: `1.10.x` có `<plate>` 3/3, `2.x` không 6/6). Chỉ `File ▸ Export ▸ Export plate sliced file` mới có.
- Chọn filament có đuôi `@BBL A1 0.2 nozzle` sẽ **đổi luôn printer preset**, kéo `max_volumetric_speed` từ 22 xuống 2.
- `meshStats` từng đếm **mặt đáy** là overhang. `Body 14`: 10.0% → 0.32% sau khi sửa; `alphabet-blocks`: 35.3% → 0.0%.

## 11. Phải sửa trong `auditFile()` trước, nếu không sẽ tự báo oan

Optimizer sẽ sinh ra cấu hình mà **luật audit hiện có kết tội**. Hai chỗ:

- Luật `PLA && bed ≥ 65 → "Bed hơi nóng cho PLA"` là ý kiến riêng, **trái với wiki Bambu** (đích 55–65°C trên Textured PEI, và A1 khung hở ở phòng lạnh còn phải +10°C). Đổi thành luật **theo diện tích đế**: đế nhỏ mà bed 65 → nhắc hạ; đế lớn (`> 150 cm²`) mà bed < 65 → nhắc **tăng**.
- Luật khuyên `sparse_infill_pattern` tiết kiệm sẽ va với `gyroid` mà tầng 2 khoá. `auditFile` phải biết: đế lớn ⇒ gyroid là **đúng**, không phải lãng phí.

## 12. Rủi ro

- `islands` cần rasterize lát cắt — phần tốn công nhất. Nếu phải cắt scope, bỏ `thinWall_cm2` trước (nó chỉ dẫn tới `arachne`, vốn đã bật sẵn trong preset).
- Ngưỡng `firstArea > 150 cm²` và `baseDiag > 150 mm` là suy ra từ khuyến nghị wiki cho "large flat model", chưa có số đo trực tiếp. Cần đánh dấu là **giả định** trong bảng quyết định, không được trình bày như đã đo.
- `STEP_TARGET` mặc định `0.20mm` chọn theo bảng đánh đổi, không theo một nghiên cứu về ngưỡng cảm nhận thị giác. Cũng là giả định.
