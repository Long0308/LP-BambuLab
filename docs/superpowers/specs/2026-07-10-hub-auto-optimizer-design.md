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

### 4b. `optimize()` là một dataflow, không phải danh sách gán key

Không key nào đứng một mình. Engine tự suy ra các đại lượng dẫn xuất, và **tự sửa lại** thiết lập của bạn nếu ràng buộc không thoả — im lặng. Vì vậy `optimize()` phải là vòng **Extract → Transform → Derive → Validate → (lặp) → Load**, chứ không phải một thang gán tuyến tính.

**Đại lượng dẫn xuất** (`derive(cfg, L)`):

```
flow_f          = layer_height × line_width_f × speed_f            (f = mỗi loại đường in)
v_max_f         = filament_max_volumetric_speed / (layer_height × line_width_f)
effTopLayers    = max(top_shell_layers, ceil(top_shell_thickness / layer_height))
effBottomLayers = max(bottom_shell_layers, ceil(bottom_shell_thickness / layer_height))
stair(z)        = layer(z) / tan θ(z)
firstFlow       = initial_layer_print_height × initial_layer_line_width × initial_layer_speed
```

**Bất biến** — kiểm sau mỗi lần một tầng ghi key:

| # | Bất biến | Nếu vỡ thì engine làm gì |
|---|---|---|
| I1 | `flow_f ≤ filament_max_volumetric_speed` | **tự hạ tốc độ**, số bạn đặt vô nghĩa |
| I2 | `top_shell_layers × layer_height ≥ top_shell_thickness` | **tự tăng số lớp đặc** |
| I3 | `layer ∈ [min_layer_height, max_layer_height] ∩ [LH_MIN, LH_MAX]` | kẹp |
| I4 | `filament_scarf_seam_type == seam_slope_type` | scarf **tắt âm thầm** |
| I5 | `vlhRanges ≠ ∅ ⇒ support_style ≠ organic ∧ enable_prime_tower = 0` | từ chối VLH |
| I6 | `elefant_foot_compensation > 0 ⇒ brim_object_gap = 0` | brim tách rời vật |
| I7 | muốn dùng `filament_*` overhang ⇒ `override_process_overhang_speed = 1` | giá trị filament **bị bỏ qua** |

**Vòng lặp tới điểm bất động.** Sau khi các tầng ghi xong: `derive` → kiểm bất biến → tầng sở hữu key vi phạm sửa lại → `derive` lại. Tối đa **3 vòng**; còn vi phạm thì đẩy vào `conflicts[]` và **không** xuất preset cho key đó.

> **Ví dụ thật.** `Body14-PLAMatte-Decor-BALANCED-0.2` đặt `top_shell_layers = 4` nhưng kế thừa `top_shell_thickness = 1.0`. Bề dày thực `4 × 0.20 = 0.80mm < 1.0` ⇒ **I2 vỡ** ⇒ engine âm thầm nâng lại **5 lớp**. Khoản tiết kiệm "top 4" chưa bao giờ tồn tại. Bản `FAST 0.24` cũng vậy (`0.96mm < 1.0`). Một thang gán tuyến tính sẽ không bao giờ phát hiện ra.

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

### Tầng 3b — Độ bền (chỉ bật khi `goal` = chức năng / cơ khí)

Nguồn: [UltiMaker — infill density](https://ultimaker.com/learn/3d-printing-infill-density-optimizing-strength-and-apeed/) và [BigRep — layer height](https://bigrep.com/posts/optimizing-layer-height-3d-printing/).

- **Thành là đường truyền lực chính, infill chỉ là dự phòng.** *"Two extra perimeters often add more strength than raising infill from 20% → 30%."* ⇒ tăng `wall_loops` **trước**, đừng tăng `sparse_infill_density`.
- `wall_loops = 3…4` · `sparse_infill_density` 20–30% (PLA) · `sparse_infill_pattern ∈ {gyroid, cubic}` · `infill_wall_overlap = 15%` (khuyến nghị 10–25%; dưới ngưỡng gây bong tách thành↔infill).
- **`layer_height ≤ 0.25`.** Lớp dày làm yếu liên kết liên lớp.

| `layer_height` | Tensile PLA (MPa) | Thời gian tương đối |
|---|---|---|
| 0.10 | 56 | 80% |
| 0.20 | 52 | 50% |
| 0.30 | 48 | 35% |

- Sàn/trần layer thực dụng cho nozzle 0.4 là **25–75% đường kính** ⇒ `[0.10, 0.30]`. Giao với giới hạn máy `[0.08, 0.28]` ⇒ dùng **`[0.10, 0.28]`**; dưới 0.10 dễ mất ổn định đùn.

### Tầng 4b — Võng mặt trên do infill quá thưa

`topPlateaus` tổng > 15% diện tích **và** `sparse_infill_density < 12%` → mặt trên có nguy cơ **võng** (UltiMaker: *"Low percentages can cause visible surface imperfections, particularly on large flat surfaces where insufficient internal support allows the outer walls to sag"*). Xử lý: nâng `sparse_infill_density` lên 15% **hoặc** `top_shell_layers` lên 6. Ghi rõ đây là đánh đổi thời gian.

### Tầng 5 — Thời gian, chỉ đòn bẩy không hại chất lượng

- `inner_wall_speed`, `sparse_infill_speed`, `internal_solid_infill_speed` → sát trần `v_max = maxvol / (layer_height × line_width)`, chừa ~2% biên. **Đây là đòn duy nhất thật sự miễn phí** — vùng khuất, không đụng bề mặt, không đụng độ bền.
- Overhang thật `≤ 2%` → `enable_support = 0`.
- `enable_prime_tower = 0` khi in một màu.
- **Không được** đổi `sparse_infill_pattern` nếu tầng 2 đã khoá `gyroid`.
- **Không được** dày layer vượt `0.25` nếu tầng 3b đang bật.

## 7. Bảng Height range (VLH)

`adaptive_layer_height` nằm trong `static std::set<std::string> ignore` của `PrintConfig.cpp` ⇒ **không set được bằng preset**. Phải bật tay trên object; nó lưu ở `layer_config_ranges` trong `.3mf`. Vì vậy đầu ra là **bảng Z-range** để người dùng nhập vào *Height range Modifier*.

Thuật toán, cho mỗi bin `Z`:

```
LH_MAX = 0.25 nếu goal = chức năng/cơ khí,  ngược lại 0.28
LH_MIN = 0.10                                (dưới mức này đùn mất ổn định)

θ = thetaP10 của bin
nếu θ ≥ 50°           → layer = LH_MAX          ← rẻ về BỀ MẶT, KHÔNG rẻ về ĐỘ BỀN
nếu 25° ≤ θ < 50°     → layer = clamp(STEP_TARGET × tan θ, LH_MIN, LH_MAX)
nếu θ < 25°           → layer = layer_height gốc   (không hạ — xem §5)
bin không có mặt nghiêng → layer = LH_MAX
```

Gộp các bin liền kề cùng `layer`. Kẹp trong giao của `[min_layer_height, max_layer_height]` (machine profile) và `[LH_MIN, LH_MAX]`.

> **Đính chính.** Bản đầu của spec này gọi việc dày layer ở thành đứng là *"miễn phí"*. **Sai.** Nó miễn phí về **bề mặt** (thành đứng không có bậc thang), nhưng lớp dày làm **yếu liên kết liên lớp**: PLA nozzle 0.4 rơi từ `52 MPa @0.20` xuống `48 MPa @0.30` (BigRep). Với vật trang trí thì không sao; với vật chịu lực thì phải kẹp `LH_MAX = 0.25`. Đòn **thật sự** miễn phí duy nhất là đẩy tốc độ **vùng khuất** lên sát trần lưu lượng.

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

## 12. Bảng đòn bẩy — cái nào thật sự miễn phí

Xếp theo "trả giá bằng gì". Chỉ nhóm đầu được tầng 5 dùng tự động.

| Đòn bẩy | Cắt được | Trả giá bằng |
|---|---|---|
| ↑ tốc độ **vùng khuất** tới trần lưu lượng | ~5–15% phần đó | **không gì** — vùng không nhìn thấy, không chịu lực chính |
| Tắt prime tower (in 1 màu) | thời gian + nhựa purge | không gì |
| Bỏ support khi overhang thật ≤ 2% | support time + nhựa | không gì |
| ↓ `sparse_infill_density` | nhiều (time ∝ thể tích × mật độ) | **độ bền**, và **võng mặt trên** nếu < 12% |
| ↑ `layer_height` | rất nhiều (≈ tuyến tính theo số lớp) | **liên kết liên lớp** (52→48 MPa) + bậc thang |
| ↓ `wall_loops` | vừa | **độ bền nhiều nhất** — thành là đường truyền lực chính |
| ↓ `outer_wall_speed` / accel | **âm** — làm CHẬM đi | đo thật: 10h37m → 31h54m |

Ba dòng cuối là đánh đổi, không phải tối ưu. Hub được phép **đề xuất** chúng kèm số, nhưng không tự áp dụng.

## 12b. Cặp tăng–giảm hợp lý

`optimize()` không chỉ đặt từng key độc lập; nhiều key chỉ có nghĩa **theo cặp**. Tất cả key dưới đây đã xác minh tồn tại trong `PrintConfig.cpp`.

| # | Tăng | Giảm | Được | Mất | Nguồn |
|---|---|---|---|---|---|
| 1 | `wall_loops` | `sparse_infill_density` | bền hơn cùng khối lượng | — | UltiMaker |
| 2 | `top_shell_layers` | `sparse_infill_density` | hết võng mặt trên, không nhồi infill toàn thân | lớp đặc in chậm | UltiMaker |
| 3 | `layer_height` | `top_shell_layers` | giữ `top_shell_thickness` (mm) với ít lớp hơn | liên kết liên lớp yếu | suy từ 2 key |
| 4 | `inner_wall_speed`, `sparse_infill_speed` | `layer_height` | Z mịn hơn, thời gian vùng khuất không đổi | không áp cho tường ngoài | wiki Volumetric |
| 5 | `overhang_fan_speed` | `fan_min_speed` | mát đúng chỗ đua, không thổi lạnh toàn thân | — | wiki Warping |
| 6 | `textured_plate_temp` | `brim_width` | bám bàn tương đương, đỡ cắt brim | bàn nóng dễ phồng chân | wiki Warping |
| 7 | `nozzle_temperature` +5–10°C | — | thêm dư địa lưu lượng | stringing, rủ overhang, đổi màu | wiki Volumetric |
| 8 | `sparse_infill_pattern` → gyroid/cubic | `sparse_infill_density` | pattern hiệu quả cho phép hạ mật độ | gyroid in lâu hơn grid | UltiMaker |

Cặp 7 là **giải pháp cuối**, không phải nước đi đầu: *"Temperature should never be your first adjustment."*

Hai ràng buộc **bắt buộc đi cùng**, không phải lựa chọn:

- `elefant_foot_compensation ↑` ⇒ `brim_object_gap ↓`, nếu không brim tách khỏi vật.
- `seam_slope_type = all` thay được `seam_position = random` — giấu seam mà không làm bề mặt lấm tấm.

### Đính chính: "thời gian tường ∝ số lớp" chỉ đúng khi giữ nguyên tốc độ

Công thức Bambu: `lưu lượng = layer_height × line_width × print_speed`.

Hạ `layer_height` một nửa ⇒ lưu lượng giảm một nửa ⇒ được phép **tăng gấp đôi tốc độ** mà vẫn dưới trần ⇒ thời gian **không đổi**. Thực tế lớp mỏng vẫn lâu vì **tường ngoài bị khoá tốc độ để giữ bề mặt**. Do đó:

- **Tường ngoài** — tốc độ cố định ⇒ thời gian **thật sự** ∝ số lớp.
- **Tường trong + infill** — tốc độ thả tới trần ⇒ thời gian do **lưu lượng** quyết định, gần như độc lập với layer height.

Đây chính là lý do đòn bẩy duy nhất thật sự miễn phí là đẩy tốc độ **vùng khuất** lên sát trần.

## 13. Nguồn

| Khẳng định | Nguồn |
|---|---|
| Enum, default, `ignore` set, mode | `PrintConfig.cpp` (bản cài trên máy) |
| Trang *Setting Overrides*, scarf seam không có checkbox | `Tab.cpp:4113`, `Tab.cpp:4426` |
| Chuỗi chặn VLH / prime tower | `resources/i18n/en/BambuStudio.mo` |
| `min/max_layer_height`, `printable_area` | `profiles/BBL/machine/Bambu Lab A1 0.4 nozzle.json` |
| Bed 55–65°C, brim 8–10mm, no-cooling 3 lớp đầu, gyroid ≤25% cho vật đế rộng, giảm accel 20–30% cho vật cao mảnh, A1 khung hở +10°C | [wiki Bambu — Model Warping](https://wiki.bambulab.com/en/filament-acc/filament/print-quality/warping-falling-off-collapsing) |
| `brim_object_gap` ↔ elephant foot | [wiki Bambu — Brim](https://wiki.bambulab.com/en/software/bambu-studio/auto-brim) |
| Thành > infill; `infill_wall_overlap` 10–25%; infill thấp gây võng mặt phẳng lớn | [UltiMaker — infill density](https://ultimaker.com/learn/3d-printing-infill-density-optimizing-strength-and-apeed/) |
| Layer 25–75% nozzle; bảng MPa/thời gian; halving layer ≈ gấp đôi time | [BigRep — layer height](https://bigrep.com/posts/optimizing-layer-height-3d-printing/) |
| Số lớp / thời gian `Body 14`, đường đánh đổi `STEP_TARGET` | đo thật, phiên 2026-07-09/10 |

## 14. Rủi ro

- `islands` cần rasterize lát cắt — phần tốn công nhất. Nếu phải cắt scope, bỏ `thinWall_cm2` trước (nó chỉ dẫn tới `arachne`, vốn đã bật sẵn trong preset).
- Ngưỡng `firstArea > 150 cm²` và `baseDiag > 150 mm` là suy ra từ khuyến nghị wiki cho "large flat model", chưa có số đo trực tiếp. Cần đánh dấu là **giả định** trong bảng quyết định, không được trình bày như đã đo.
- `STEP_TARGET` mặc định `0.20mm` chọn theo bảng đánh đổi, không theo một nghiên cứu về ngưỡng cảm nhận thị giác. Cũng là giả định.
