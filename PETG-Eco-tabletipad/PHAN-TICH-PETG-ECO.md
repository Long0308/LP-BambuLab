# PETG Eco — giá đỡ iPad "tabletipad-pink" (Bambu A1 · nozzle 0.4)

Sinh bằng `petg_eco_build.py` — số liệu đo từ mesh thật + bảng nhựa đã kiểm chứng
trong `analyzer.py` (`FIL_EXPORT["PETG ECO"]`), **không bịa số**.
Kiểm chứng cuối: **slice thật cả 4 khay** bằng Bambu Studio CLI (`return_code = 0`).

---

## 1. Kết luận nhanh

| Việc | Giá trị |
|---|---|
| Nhựa | **PETG Eco (Tinmorry)** — kế thừa `Bambu PETG Basic @BBL A1` |
| Vòi | **240 °C** (lớp 1 cũng 240 — không hạ lớp đầu để khỏi under-melt) |
| Bàn (Textured PEI) | **80 °C** (eco cần nóng hơn PETG Bambu 70) |
| Trần chảy | **14 mm³/s** → tường/ruột ≤ **161 mm/s** @ layer 0.2 |
| Flow ratio | **0.94** |
| Chống xơ | **retraction 1.2 mm @ 30 mm/s + WIPE 2 mm + Z-hop 0.4 + SẤY nhựa** |
| Bám bàn | **brim outer_only 8 mm**, quạt TẮT lớp đầu |
| Filament slot | **#4** (đúng như Project Filaments của bạn — Plate 3 đang gán Fila. = 4) |
| AMS | **Khe 4 = PETG gray** → khớp 1:1, không cần map tay |
| Tổng | **222.6 g PETG** · **~11 h 37 m** cho cả 4 khay |

---

## 2. Đây là chi tiết gì (đo từ mesh)

Không phải "ốp lưng iPad" — đây là **cụm cơ khí 13 chi tiết**: tấm lưới Voronoi
dẻo + trục vít (worm gear) + bánh răng + vít/nut + 2 tay kẹp trái/phải.

| Chi tiết | Kích thước (mm) | Thể tích | Tam giác |
|---|---|---|---|
| `main_voronoi.stl` | 182 × 150 × 22 | 41.7 cm³ | 54 498 |
| `worm.stl` | 19 × 135.4 × 19 | 20.5 cm³ | 169 744 |
| `left.stl` / `right.stl` | 112.8 × 113.7 × 33 | 27.2 cm³ | 11 802 |
| `bottom.stl` | 180 × 31.3 × 24 | 29.3 cm³ | 2 172 |
| `gear.stl` | 103.3 × 92.3 × 5 | 10.1 cm³ | 3 890 |
| `screw*.stl` (3 loại) | 203 × 9.6 × 4 | 5.7–12.5 cm³ | 3 486–6 880 |
| `nut_3x.stl` | 30.2 × 30.2 × 10 | 5.8 cm³ | 52 190 |

### Khay 3 — `main_voronoi` + 2 `Generic-Cube` (đúng khay trong ảnh bạn gửi)

Đo bằng raster hoá mặt đáy (bước 0.05 mm) + cắt lớp theo trục Z:

| Đại lượng | Số đo | Ý nghĩa cho PETG |
|---|---|---|
| Kích thước đặt trên bàn | **150 × 182 × 22 mm** | khay lớn nhưng **mỏng** |
| Diện tích bề mặt | 473.9 cm² | nhiều đường đi → nhiều chỗ dễ kéo xơ |
| Tấm lưới dày | **≈ 3.5 mm** (mặt đáy Z=0 · mặt trên Z≈3.5) | 18 lớp đặc rồi mới lên chi tiết |
| Thành đứng giữa 2 mặt | 97.5 cm² / mỗi mm chiều cao | tường lỗ dày ⇒ **không có thin-wall** |
| **Bề rộng thanh lưới** | nhỏ nhất **1.80 mm** · P5 2.15 · P50 3.45 mm | 1.80 mm = **4.3 × đường in 0.42 mm** → in khoẻ, không hở/gap-fill |
| Thanh < 0.42 mm | **0 %** | analyzer: `thin_frac = 0` — không có nguy cơ thin-wall |
| **Tiếp xúc bàn** | **124.76 cm²** / 273 cm² bao bóng = **45.7 %** | khá tốt |
| Mặt hẫng > 45° | **1.2 cm² (0.24 %)** — nằm đúng ở lớp 0 | **KHÔNG cần support** |
| Bridge / trần khe | 0 cm² | lỗ Voronoi xuyên thẳng, không phải bắc cầu |
| 2 tai bản lề | vươn từ Z≈6 lên **Z=22** | tường đứng, quạt overhang 100 % lo |

> Vì **không có thin-wall và không có mặt hẫng thật**, hai thứ hay giết PETG đều
> vắng mặt ở khay này. Rủi ro còn lại tập trung đúng 3 chỗ bạn nêu — **xơ · thiếu
> nhiệt · kẹt nhựa** — cộng thêm **bám bàn**.

---

## 3. Xử lý 3 vấn đề bạn nêu

### 3.1. Không bị xơ (kéo sợi / mạng nhện)

| Lever | Giá trị | Vì sao |
|---|---|---|
| **Sấy nhựa 65 °C / 6–8 h** | trước khi in | **#1** — PETG Eco hút ẩm mạnh; hơi nước sủi trong vòi đẩy nhựa phì ra thành tơ. AMS Lite **KHÔNG sấy**. |
| Retraction | **1.2 mm @ 30 mm/s** | dài hơn PLA (0.8) để đứt dứt khoát; **chậm** 30 mm/s để sợi đứt gọn thay vì vuốt thành tơ. |
| Wipe | **1 (bật) · wipe_distance 2 mm** | chà miệng vòi lên đường vừa in trước khi travel → gửi nhựa thừa vào đường in thay vì kéo thành sợi. |
| Z-hop | **0.4 mm** | nhấc vòi qua mép lỗ Voronoi, không quệt. |
| Trần chảy | **14 mm³/s** | cuộn eco đùn nhanh ⇒ áp suất dư ⇒ nhỏ giọt khi travel. 14 là số người dùng PETG-Eco thật báo. |
| Quạt | lớp 1 **TẮT** · min **30 %** · max **50 %** · overhang **100 %** | thổi mạnh làm PETG nguội lệch lớp; nhưng hẫng vẫn cần 100 % cho 2 tai khỏi xệ. |

### 3.2. Đủ nhiệt

| Lever | Giá trị | Vì sao |
|---|---|---|
| Nhiệt vòi | **240 °C cho cả lớp 1** | Eco hãng ghi 230–260 °C; 240 nằm giữa, an toàn cho hotend A1. **Lớp đầu để bằng lớp thân** — hạ lớp đầu là nguyên nhân under-melt/kẹt sớm. |
| Nhiệt bàn | **80 °C cả lớp 1** | PETG Bambu cần 70; **eco cần 75–90** → 80. Bàn nóng đều là điều kiện số 1 để không tróc mép. |
| Range khai báo | 230–270 °C | để Studio không báo "nhiệt ngoài khoảng" và không tự sửa số. |

### 3.3. Không bị kẹt nhựa

| Lever | Giá trị | Vì sao |
|---|---|---|
| Trần chảy **14 mm³/s** | ⇒ tường/ruột ≤ **161 mm/s** | kẹt PETG chủ yếu do **đùn nhanh hơn tốc độ nóng chảy**: bánh răng đẩy mãi mà nhựa không kịp chảy → nhựa bị nghiền. Con số tốc độ trong preset bị chặn theo vật lý `v = mvs / (layer × line_width) = 14 / (0.2 × 0.42) = 166`. |
| Retraction **ngắn 1.2 mm** | không dài hơn | retraction càng dài càng nhiều nguy cơ heat-creep (nhựa nóng leo lên cold zone → kẹt). Direct drive A1 chỉ cần 1.2. |
| **Sấy nhựa** | 65 °C / 6–8 h | hơi nước → bọt khí trong vòi → nghẽn cục bộ. Cùng một nguyên nhân với xơ. |
| Nhiệt 240 (không hạ) | — | nhựa nguội trong vòi = kẹt cứng ở đầu nozzle. |

---

## 4. Bám bàn (phân tích từng khay)

Tỉ lệ **diện tích chạm bàn / bao bóng** là chỉ số quyết định. Dưới 25 % là vùng
nguy hiểm với PETG.

| Khay | Chi tiết | Bao bóng (mm) | Chạm bàn | Tỉ lệ | Mặt hẫng | Support | Thời gian | Nhựa |
|---|---|---|---|---|---|---|---|---|
| 1 | `bottom` + `gear` + 3×`nut` | 175.6 × 183.4 | 83.3 cm² | 26 % | 4.2 cm² (1.41 %) | nên bật | 2 h 05 m | 41.0 g |
| 2 | 8 chi tiết (tay kẹp, vít, trục) | 213.5 × 219.9 | 95.9 cm² | 20 % | 17.8 cm² (2.53 %) | nên bật | 4 h 31 m | 93.3 g |
| **3** | `main_voronoi` + 2 `Generic-Cube` | 150.0 × 182.0 | **124.8 cm²** | **46 %** | 1.2 cm² (0.24 %) | **KHÔNG** | 3 h 02 m | 46.4 g |
| 4 | `worm` + 2×`bottom_middle` | 127.5 × 143.6 | **26.3 cm²** | **14 %** ⚠ | 3.1 cm² (1.11 %) | nên bật | 1 h 58 m | 42.0 g |

### Cách chặn bong bàn

1. **Brim `outer_only` 8 mm** (không phải 5) — đã bake sẵn. Khay 3 mép tấm lưới chỉ
   dày 3.5 mm, khay 4 chỉ 26 cm² tiếp xúc ⇒ 5 mm là thiếu.
2. **Lau bàn bằng cồn/IPA trước khi in** — dầu tay là thủ phạm vênh số 1. Bàn bẩn
   thì mọi preset đều vô nghĩa.
3. **Bàn 80 °C** — PETG bám PEI nhám rất chắc khi bàn đủ nóng.
4. **Quạt TẮT lớp đầu** (`close_fan_the_first_x_layers = 1`) — lớp 1 nguội chậm mới dính.
5. **PETG dính PEI *quá* chắc** → bôi **keo dính (glue stick)** làm lớp ngăn, gỡ ra
   mới không rách mặt bàn. Keo ở đây để **giảm** dính (ngược với PLA).
6. **Khay 4 (14 %)** — nếu vẫn bong: sơn **Brim Ears** ở 2 đầu trục `worm`
   (Others ▸ Brim ▸ Painted) hoặc dựng trục đứng lên. Brim cả vòng chỉ tốn công gọt.
7. **Khay 1 & 2** có hẫng 4.2 / 17.8 cm²: preset đang **TẮT support** theo khuyến nghị
   của hub (hẫng nhỏ). Nếu mặt dưới xấu, bật support cùng PETG với **Top Z = 0.3** /
   **Bottom Z = 0.2** — PETG hàn chính nó, Z nhỏ là dính chết.

---

## 5. Sửa code: in đúng KHAY, đúng FILAMENT #4, đúng KHE AMS 4

Đây là phần **quan trọng nhất** của đợt này — không chỉ là chỉnh preset.

### 5.1. File `.3mf` — ép mọi object về **filament #4**

Ảnh Studio của bạn cho thấy **Plate 3 gán `Fila. = 4`** cho `main_voronoi.stl` và cả
2 `Generic-Cube`. Bản `.3mf` xuất ra đã được ép **toàn bộ 17 object instance về
filament #4** (`Metadata/model_settings.config`, `<metadata key="extruder">`), và cả
6 slot đều khai PETG gray Eco — nên dù Bambu tự map hay map tay, kết quả luôn là
**một cuộn PETG gray ở khe 4**.

Kiểm chứng bằng chính file đã slice:
`Metadata/plate_3.json` → `"filament_ids": [3]`, `"first_extruder": 3`
(= slot **4**, 0-based) — trước khi sửa là `[1]` (= slot 2).

### 5.2. Lỗi cũ trong `bambu_web.py` (nút "In" của hub)

```python
# TRƯỚC
def cmd_project_file(name, path):
    payload = {"print": {
        "param": "Metadata/plate_1.gcode",   # <-- HARD-CODE khay 1
        ...
        "use_ams": False,                    # <-- HARD-CODE tắt AMS
    }}
```

Hai hệ quả thật:

1. File nhiều khay **luôn in ra khay 1**, dù bạn muốn khay 3 — sai âm thầm.
2. **AMS bị tắt hoàn toàn** ⇒ máy luôn đòi cuộn ở giá ngoài, dù PETG gray đang nằm ở
   **AMS khe 4**. Bấm In là máy dừng báo thiếu nhựa.

### 5.3. Đã sửa

| Chỗ | Thay đổi |
|---|---|
| `cmd_project_file(name, path, plate, ams_slot, ams_mode)` | `param = Metadata/plate_N.gcode` **theo khay bạn chọn** |
| Payload MQTT | `use_ams: True` + `ams_mapping` (0-based) + `ams_mapping2` (`{ams_id, slot_id}`) |
| `_ams_slots()` | đọc **AMS thật** qua MQTT (loại nhựa + màu từng khe) — không đoán |
| `_default_ams_slot()` | ưu tiên khe đang có **PETG**; không đọc được AMS → mặc định **khe 4** |
| `_load/_save_print_opts()` | nhớ **khay + kiểu lấy nhựa** giữa các lần in (`print_opts.local.json`, đã gitignore) |
| `GET /api/ams` | UI hỏi trạng thái 4 khe để hiện đúng tên nhựa |
| `POST /api/print` | nhận thêm `plate`, `ams_slot`, `ams_mode` |
| UI trang "File in" | ô **Khay** + **Nhựa lấy từ**; hộp xác nhận hiện rõ *"Khay 3 · AMS đúng khe như file (1:1)"* |

**3 kiểu lấy nhựa:**

| Kiểu | Ý nghĩa | Dùng khi |
|---|---|---|
| **`1:1` (mặc định)** | nhựa #N → khe #N. File khai filament 4 ⇒ lấy **AMS khe 4**. | **Đúng cho project của bạn** (Plate 3 gán Fila.=4, AMS 4 = PETG gray). |
| `Tất cả về khe K` | mọi filament đều lấy khe K (in 1 cuộn cho cả file). | File trộn nhiều slot nhưng bạn chỉ có 1 cuộn PETG. |
| `Cuộn ngoài` | `use_ams: False`. | Không có AMS / nhựa để ở giá ngoài. |

**Mapping AMS:** `ams_mapping[i]` = chỉ số tray **0-based** cho filament thứ `i`
(khe 4 → `3`); `-1` = cuộn ngoài. Gửi **cả** `ams_mapping` (firmware cũ) và
`ams_mapping2` (firmware mới) để tương thích hai chiều.

### 5.4. Kiểm chứng payload (không gửi lệnh xuống máy)

```
_ams_state() khi chưa kết nối máy -> default_slot=4, default_mode="1to1", đủ 4 khe
plate=3 mode=1to1 slot=4 -> param=Metadata/plate_3.gcode use_ams=True  map=[0,1,2,3]
                            map2[3]={ams_id:0, slot_id:3}   <- filament #4 = tray 4
plate=3 mode=same slot=4 -> map=[3,3,3,3,3,3]
plate=3 mode=ext  slot=4 -> use_ams=False, KHONG có ams_mapping
plate=1 mode=1to1 slot=1 -> param=Metadata/plate_1.gcode map=[0,1,2,3]

TAT CA ASSERT PASS   ·   lưu/đọc lại lựa chọn: OK
```

---

## 6. File đã tạo

```
PETG-Eco-tabletipad\
├── 1.Filament\LP_PETG_Eco_FILAMENT.json      ← import tab Filament
├── 2.Process\LP_PETG_Eco_FAST.json           ← 0.28mm · 2 tường · 115 mm/s
├── 2.Process\LP_PETG_Eco_BALANCED.json       ← 0.20mm · 3 tường · 161 mm/s  (khuyến nghị)
├── 2.Process\LP_PETG_Eco_QUALITY.json        ← 0.16mm · 3 tường · 201 mm/s
├── tablet-ipad-pink-PETG-Eco.3mf             ← project đã nhúng config PETG Eco (4 khay)
├── preview\plate_1..4.png                    ← ảnh từng khay
└── PHAN-TICH-PETG-ECO.md                     ← tài liệu này
```

### Dùng

**Cách A — in ngay bằng file `.3mf` này:**
Đẩy `tablet-ipad-pink-PETG-Eco.3mf` lên hub → trang *File in* → chọn **Khay 3** và
**Nhựa lấy từ = AMS đúng khe như file (1:1)** → bấm **In**.

**Cách B — áp vào `tablet-ipad-pink.3mf` của bạn:**
1. Studio ▸ *Filament* ⋯ ▸ Import → `LP_PETG_Eco_FILAMENT.json`.
   Gán preset này cho **filament #4** (và #5, #7, #8, #9 nếu muốn — cùng một cuộn).
2. Studio ▸ *Process* ⋯ ▸ Import → `LP_PETG_Eco_BALANCED.json`.
3. So lại đúng 6 số ở mục 1 (240 / 80 / 14 / 0.94 / 1.2 / 30). Xong.

### Nội dung config đã nhúng (đo từ G-code khay 3)

```
filament_type = PETG × 6          filament_colour = #808080 × 6 (gray ở khe 4)
nozzle 240 °C (lớp 1: 240)        bàn 80 °C (lớp 1: 80)
mvs 14 mm³/s · flow 0.94          retraction 1.2 mm @ 30 mm/s · wipe 2 mm · z-hop 0.4
quạt: lớp 1 TẮT · min 30 % · max 50 % · overhang 100 %
layer 0.2 · 3 tường · ruột 15 % adaptivecubic · mặt trên/dưới 5/4 lớp
tường ngoài 150 · tường trong 161 · mặt trên 100 mm/s · seam = Back
brim outer_only 8 mm · skirt 0 · support TẮT · bỏ Variable Layer Height
```

---

## 7. Kiểm chứng cuối (slice thật, không phải lý thuyết)

Bambu Studio CLI · `return_code = 0` cho **cả 4 khay**:

| Khay | Thời gian | Số lớp | Nhựa |
|---|---|---|---|
| 1 | 2 h 05 m 25 s | 120 | 41.0 g |
| 2 | 4 h 31 m 28 s | 250 | 93.3 g |
| **3** | **3 h 02 m 28 s** | **110** | **46.4 g** |
| 4 | 1 h 57 m 37 s | 98 | 42.0 g |
| **Tổng** | **~11 h 37 m** | | **222.6 g** |

Đã đối chiếu trong G-code khay 3 (22.8 MB):
`M104 S240` ✔ · `M190 S80` ✔ · `filament_type = PETG;PETG;…` ✔ ·
`filament_colour = #808080;…` ✔ · `filament_max_volumetric_speed = 14` ✔ ·
`filament_retraction_length = 1.2` ✔ · `brim_type = outer_only` + `brim_width = 8` ✔ ·
`enable_support = 0` ✔ · 16 925 lệnh retraction + wipe ✔ ·
**không vẽ tháp prime** (in 1 màu → không tốn nhựa).

---

## 8. Nếu vẫn còn lỗi — chỉnh theo thứ tự này

| Triệu chứng | Núm chỉnh (Studio) |
|---|---|
| Vẫn còn tơ mảnh ở travel | **Sấy lại nhựa 65 °C / 8 h** (90 % ca là do ẩm). Rồi mới tăng retraction 1.2 → 1.4 mm. |
| Mặt trên sọc/hở | Giảm **Top surface speed** 100 → 80. |
| Thiếu đùn nhẹ / nghe tiếng bánh răng | Nhiệt 240 → **245 °C** (vẫn trong dải eco 230–260). |
| Vẫn kẹt | mvs 14 → **12**, tốc độ tường/ruột 161 → **140**. |
| Khay 4 bong mép | Sơn **Brim Ears** ở đầu trục `worm`; lau bàn IPA. |
| Máy báo "không tìm thấy nhựa" | Kiểm ô **Nhựa lấy từ**: phải là *AMS đúng khe như file (1:1)*, không phải *Cuộn ngoài*. |
| Muốn mặt gương | Bật **Ironing = Top surfaces** (PETG ủi dễ tơ, chỉ làm nếu cần). |

---

*Ghi chú nguồn file:* `tablet-ipad-pink.3mf` bạn upload trước đây **không còn trên
server** — hub tự xoá file gốc sau khi slice (`bambu_web.py`, `os.remove(src_path)`).
Bản `.3mf` ở trên được dựng lại từ đúng bộ mesh đó
(`slice_jobs/e2e/opt_tabletipad-pink__base.3mf` — `Metadata/plate_3.png` khớp byte
với ảnh khay trong `job_cache`). Preset `.json` thì áp được cho bất kỳ file nào.
