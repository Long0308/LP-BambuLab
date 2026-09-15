# PETG Eco — ĐO TOÀN BỘ: hình học · nhiệt · lưu lượng · hiệu năng · kẹt

Đo ngày **16/09/2026**, trên chính file đang in `tabletipad-pink_plate_3.gcode.3mf`
(6 546 736 byte, 922 016 dòng, 110 lớp) và trên slice thật khay 3.
Mọi con số dưới đây **bóc từ gcode**, không suy đoán.

---

## 1. HÌNH HỌC — vật thấp, phẳng, rộng

| Chỉ số | Số đo | Nghĩa |
|---|---|---|
| Chiều cao | **22.0 mm** | thấp — KHÔNG dính luật "vật cao" (ngưỡng ≥120 mm) |
| Diện tích bề mặt | **473.9 cm²** | rất lớn |
| `flat_ratio` | **0.768** | 76.8% mặt phẳng → đây là một TẤM, không phải khối |
| Overhang | **0.24 %** = 1.2 cm² | dưới ngưỡng → **không cần support** |
| Thành mỏng | **0** (0/4193 mẫu) | không có vách mỏng |
| Cầu (bridge) | 2 mảng, **0 cm²**, span 0 mm | không đáng kể |

**Hệ quả số 1:** vì mặt phẳng rộng 473.9 cm², mỗi lớp đầu rất DÀI. Đó là lý do
79 % thời gian in nằm ở ~14 lớp đầu, dù cả bản có 110 lớp. Càng lên cao tiết diện
càng nhỏ → mỗi lớp càng ngắn.

---

## 2. NHIỆT — phẳng tuyệt đối, không phải biến số gây kẹt

Cấu hình trong file (khe 4 = PETG Eco):

| Thông số | Giá trị |
|---|---|
| `filament_type` (khe 4) | PETG |
| `nozzle_temperature` | **240 °C** (lớp đầu cũng 240 — không under-melt lớp 1) |
| `hot_plate_temp` | **80 °C** |
| `textured_plate_temp` | **80 °C** (bàn PEI nhám — A1 đọc ô này mới đúng) |
| `filament_flow_ratio` | 0.94 |
| `filament_density` | 1.27 g/cm³ |
| `filament_diameter` | 1.75 mm |
| `filament_max_volumetric_speed` | **12 mm³/s** (khai 22 → đã bị kẹp về 12) |

**Đo trong gcode, suốt 110 lớp:** `M104/M109 = 240 °C`, `M140/M190 = 80 °C` — không
đổi một lần nào.

Các mốc nhiệt khác chỉ là thủ tục ngoài vùng in:
`140` (sấy trước) · `25` · `170/190` (hạ nhiệt cuối) · `250/270` (vệ sinh nozzle / AMS).

⇒ **Nhiệt ổn định hoàn toàn. Kẹt nhựa ở bản này KHÔNG đến từ nhiệt — nó là bài
toán LƯU LƯỢNG.**

---

## 3. LƯU LƯỢNG THẬT THEO TỪNG LỚP

Cách đo: mỗi đoạn in lấy `; LINE_WIDTH` (slicer chú thích sẵn) × chiều cao lớp ×
tốc độ `F`. Đây là lưu lượng slicer **yêu cầu**, không phải suy từ nhiệt.

| Nhóm lớp | Z (mm) | Q trung bình | **Q đỉnh** | %trần |
|---|---|---|---|---|
| 1 (lớp đầu 0.24 mm) | 0.00 | 3.13 | 4.31 | 36 % |
| 2–14 | 0.24 – 2.64 | **11.5** | **13.16** | **110 %** |
| 15–40 | 2.84 – 7.84 | 9.3 – 11.5 | 12.1 – 13.1 | 101–109 % |
| 41–67 | 8.04 – 13.24 | **3.5** | 12.15 | 101 % |
| 68–110 | 13.44 – 21.84 | 2.4 – 5.5 | 12.1 – 13.15 | 101–110 % |

### Phát hiện quan trọng nhất

**Trung bình giảm mạnh theo độ cao, nhưng ĐỈNH thì bám trần ở MỌI độ cao.**

- `Q trung bình`: 11.5 → 3.5 → 2.5 mm³/s (vì tiết diện nhỏ dần, và
  `slow_down_layer_time` tự hãm để lớp kịp nguội).
- `Q đỉnh`: **luôn 12.1 – 13.2 mm³/s = 101 – 110 % trần 12.**

Ai chỉ nhìn trung bình sẽ tưởng bản in "nhẹ dần và an toàn". Sai: **đỉnh vẫn chạm
vùng nguy hiểm suốt bản in.**

### Vì sao đỉnh VƯỢT trần 12?

Arachne in đường rộng biến thiên — đo được `LINE_WIDTH` từ **0.42 lên 0.60 mm**. Trần
`filament_max_volumetric_speed` của slicer lại tính theo bề rộng **danh nghĩa 0.42**.

```
135 mm/s × 0.4875 mm × 0.2 mm = 13.16 mm³/s   >   trần 12
```

⇒ Trần mvs không chặn được Arachne ở đường rộng. Chỉ chạy **đúng bằng trần** là vẫn
lọt lên trên. Đây chính là lý do phải có **biên**, chứ không chỉ "đặt bằng trần".

---

## 4. HIỆU NĂNG 3 CẤP — slice thật khay 3

| Cấp | Lớp | Tường/ruột | Mặt trên | mm³/s | %trần | Thời gian | Nhựa | Số lớp |
|---|---|---|---|---|---|---|---|---|
| FAST | 0.28 | 86 | 61 | 10.11 | 84 % | **2h 24m** | 43.76 g | 79 |
| BALANCED | 0.20 | 120 | 85 | 10.08 | 84 % | **3h 07m** | 46.37 g | 110 |
| QUALITY | 0.16 | 151 | 107 | 10.15 | 85 % | **3h 50m** | 48.54 g | 137 |
| *đang in* | 0.20 | 135 | 90 | 11.34 (đỉnh 13.16) | **94 %** | 3h 10m | 47.15 g | 110 |

### Bài học về tốc độ: tốc độ vượt trần là SỐ ẢO

Bản đang in đặt **135 mm/s = 94 % trần**. Bản BALANCED mới đặt **120 mm/s = 84 % trần**.

> 3h 10m 10s → **3h 07m 20s**: hạ tốc độ mà **NHANH HƠN 3 phút**.

Vì sao: khi yêu cầu vượt trần nóng chảy, máy **tự hãm** — phần tốc độ vượt trần
không bao giờ được in ra thật. Nó chỉ làm bánh răng extruder đẩy nhanh hơn tốc độ
nhựa chảy ⇒ **nghiền sợi**. Cắt nó đi: không mất thời gian, mất rủi ro.

**Cao hơn không nhanh hơn. Cao hơn chỉ nguy hiểm hơn.**

---

## 5. CƠ CHẾ KẸT VÀ NGƯỠNG ĐÃ ĐO

| Mốc | Lưu lượng | Kết quả |
|---|---|---|
| 13/09 — mvs 14, tường 161 mm/s | 13.5 mm³/s | **KẸT NHỰA** ở 90 % |
| đang in — mvs 12, tường 135 mm/s | đỉnh 13.16 mm³/s | đi được tới 79 %, chưa kẹt |
| ngưỡng đặt ra — biên 85 % | **10.2 mm³/s** | chừa biên 25 % dưới mốc kẹt |

Cơ chế: bánh răng extruder đẩy nhựa **nhanh hơn tốc độ nóng chảy** → sợi bị nghiền
tại bánh răng (đúng nghĩa "kẹt nhựa"), kéo theo thiếu đùn. Sợi nằm ở 240 °C suốt
3 giờ còn phình trong nozzle — gốc của lỗi **1200-8015** (không rút ra được) cuối
bản in 13/09.

---

## 6. SÁU BÀI HỌC CHỐT

1. **Nhiệt ổn định ⇒ kẹt là bài toán LƯU LƯỢNG.** 110 lớp cùng 240 °C / 80 °C, không
   lay chuyển. Đi tìm nguyên nhân ở nhiệt độ là tìm sai chỗ.

2. **Trung bình vô nghĩa — phải đo ĐỈNH.** Lớp 41–67 có trung bình 3.5 mm³/s nhưng
   đỉnh 12.15. Nhìn trung bình sẽ kết luận sai rằng phần trên an toàn.

3. **Đặt bằng trần là chưa đủ.** Arachne in đường rộng tới 0.60 mm trong khi trần
   tính theo 0.42 ⇒ lọt lên 110 % trần. Cần **biên 15 %**, không chỉ "đúng trần".

4. **Tốc độ vượt trần là số ảo.** Cắt 135 → 120 mm/s: nhanh hơn 3 phút. Máy tự hãm
   phần vượt trần, chỉ giữ lại tác hại.

5. **Vật thấp + phẳng rộng ⇒ thời gian dồn ở đáy.** 473.9 cm² khiến 14 lớp đầu chiếm
   79 % thời gian. Càng lên cao càng nhẹ ⇒ nếu có rủi ro, nó nằm ở ĐÁY, không phải ở đỉnh.

6. **Trần phải lấy theo NHÓM NHUA, không theo lời khai trong file.** File gốc khai
   mvs 22 (đúng cho hotend HF) — với A1 stock đó là con số tự sát. Đã kẹp về 12.

---

*Nguồn: `analyzer.py` (SAFE_MARGIN 0.85, safe_mvs_ceiling) · gcode
`tabletipad-pink_plate_3.gcode.3mf` · slice thật 3 cấp qua `slicer_cli.slice_3mf`.*
