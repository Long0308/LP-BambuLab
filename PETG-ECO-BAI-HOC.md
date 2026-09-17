# PETG Eco — bài học kinh nghiệm (theo dõi tự động)

Ghi bởi `petg_monitor.py` trong lúc máy in. Mỗi mục là một sự kiện **THẬT** đo được
từ máy qua LAN MQTT — không suy đoán. Xem timeline thô: `job_cache/*__run.jsonl`.

---

## Job: `tabletipad-pink_plate_3` · khay 3 · PETG Eco · 110 lớp

- **BASELINE** — AMS lúc bắt đầu: khe 1 = PLA/4DAFDA · khe 2 = PLA/68724D ·
  khe 3 = PLA/E8AFCF · **khe 4 = PETG/A4AAAC** ← cuộn đang in.
  File `tabletipad-pink_plate_3.gcode.3mf`, **110 lớp** ⇒ khớp đúng bản đã slice.
- **BASELINE (vào in thật, `layer_num ≥ 1`)** — vòi đích **240 °C** · bàn đích
  **80 °C** · quạt **0 %** ⇒ đúng preset `LP-PETG-Eco-Balanced-0.2mm`.

### Bài học #1 — 2 lần báo nhầm nhiệt ở giai đoạn khởi động (đã sửa)

Lần 1: thấy `nozzle_target_temper` = 190 °C rồi 140 °C, khác 240 °C của preset →
monitor báo WARN. Lần 2: đổi mốc sang `mc_percent ≥ 1` thì **vẫn** báo nhầm, vì
`mc_percent` đã nhảy lên 3 % ngay từ pha dò bàn (chưa in lớp nào).

Nguyên nhân thật — A1 chạy chuỗi start gcode TRƯỚC khi in:

```
M104 S170 ; prepare to wipe nozzle
M109 S190 ; dò bàn (probe)
M104 S140 ; prepare to ABL
M109 S140 ; cân bàn
M190 S80  ; giữ bàn 80
M104 S240 ; prepare to print   ← lúc này mới đúng 240
```

⇒ Mốc đúng để biết "đã in thật" là **`layer_num ≥ 1`**, KHÔNG phải `gcode_state`
chuyển RUNNING và cũng KHÔNG phải `mc_percent ≥ 1`. Đã sửa trong `petg_monitor.py`.

**Áp dụng cho lần sau:** cảnh báo nhiệt đọc khi `layer_num = 0` là nhiễu của chuỗi
start gcode — bỏ qua. Muốn biết máy đã vào in thật chưa thì xem `layer_num`.

### Bài học #2 — tiến trình theo dõi nền bị kill khi phiên lệnh đóng

**Hiện tượng:** monitor chạy được ~3 phút rồi mất hút. stdout dừng ở một dòng bình
thường (`22:01:40 ... 5%`), stderr **không có traceback** ⇒ bị **hard-kill**, không
phải lỗi code. Timeline mất một đoạn `22:01:40 → 22:24:20`.

**Nguyên nhân gốc:** tiến trình con nằm trong *job object* của phiên lệnh; khi phiên
đóng thì cả cây tiến trình bị kill.

**Đã thử — kết quả thật:**

| Cách chạy | Kết quả |
|---|---|
| `Start-Process -WindowStyle Hidden` | ❌ chết khi phiên đóng |
| `Win32_Process.Create` (ReturnValue=0, có PID) | ❌ vẫn chết |
| **`schtasks` (Task Scheduler)** | ✅ **SỐNG** — service sở hữu, không thuộc job object |

Cách chạy đúng đang dùng:

```
schtasks /Create /TN "PETG-Monitor-A1" /TR "D:\15.BambuStudio\job_cache\petg-monitor.bat" /SC ONCE /ST 23:59 /F
schtasks /Run    /TN "PETG-Monitor-A1"
```

**Vá thêm:** thêm chế độ `--sample` cho `petg_monitor.py` — mỗi nhịp kiểm tra tự lấy
1 mẫu và ghi vào **cùng** timeline. Nên kể cả tiến trình nền có chết, dữ liệu vẫn còn
(độ phân giải 20 phút thay vì 20 giây).

**Áp dụng cho lần sau:** cần tiến trình nền sống lâu trong môi trường này → dùng
Task Scheduler, đừng dựa vào `Start-Process`.

### Ghi chú đọc số — lớp 1 chiếm ~15 % cả bản in

Lúc `22:24` máy báo **15 %** mà `layer_num` vẫn = **1**. Không phải kẹt: đáy khay 3
là 124.76 cm² + brim 8 mm, in ở 30 mm/s ⇒ riêng lớp 1 mất ~23 phút (≈15 % của 3 h).
**Đừng kết luận kẹt khi thấy % cao mà lớp thấp — hãy so với `layer_num` có tăng không.**

### Cách đọc nhanh trạng thái bất cứ lúc nào

```powershell
python -X utf8 D:\15.BambuStudio\petg_monitor.py --status
python -X utf8 D:\15.BambuStudio\petg_monitor.py --sample   # lấy 1 mẫu mới
```

Xem trực tiếp timeline: `job_cache/tabletipad-pink_plate_3__run.jsonl`
(1 dòng / 20 giây: lớp, %, nhiệt vòi/bàn, quạt, HMS, print_error).

---


  file=tabletipad-pink_plate_3.gcode.3mf layers=110
  `ams=['khe 1=PLA/4DAFDA', 'khe 2=PLA/68724D', 'khe 3=PLA/E8AFCF', 'khe 4=PETG/A4AAAC']`
  bàn đích 80C · quạt 0% · 110 lớp ⇒ **đúng preset PETG Eco**

---

## KẾT QUẢ BẢN IN (13→14/09/2026)

**Bản in HOÀN THÀNH đủ 110/110 lớp, 99 %** — rồi máy PAUSE ở bước **nhả nhựa**
cuối cùng. Đây là lỗi *sau khi in xong*, không phải lỗi in.

| Mốc | Trạng thái |
|---|---|
| 21:53 → 21:58 | chuỗi start gcode (dò bàn, cân bàn) |
| 21:58 | vào in thật: vòi 240 °C · bàn 80 °C · quạt 0 % · **110 lớp** |
| 22:24 → 01:05 | 15 % → 89 %, nhiệt giữ đúng 240/80 suốt, **0 sự kiện** |
| 01:24 | đạt **110/110 lớp**, 99 % |
| **01:24:21** | **PAUSE** · `print_error = 302022677` (**1200-8015**) · HMS `1200-1300-0002-0002` |
| 01:26 | bàn đã tắt (đích 0 °C), vòi nguội 220 °C ⇒ end-gcode đã chạy |

Tổng thời gian theo dõi: **3 h 26 m** (21:58 → 01:26), so với ước lượng Studio
3 h 12 m — lệch **+7 %**, hợp lý vì lớp 1 dài (đáy lớn + brim 8 mm ở 30 mm/s).
Trong suốt 3,5 giờ in: **không một lần** lệch nhiệt, đứng tiến độ, hay lỗi đùn.

### Bài học #3 — PAUSE 1200-8015: rút nhựa khỏi đầu in thất bại (KHÔNG phải lỗi in)

**Hiện tượng đo được:** ở 110/110 lớp máy dừng (PAUSE), `print_error = 1200-8015`,
HMS `1200-1300-0002-0002`, bàn đã tắt hoàn toàn. Vật in đã đủ lớp.

**Nghĩa chính xác** (wiki chính thức `wiki.bambulab.com/en/hms/error-code`):

> **1200-8015** — *"Failed to pull out the filament from the toolhead. Please check
> if the filament is stuck, or the filament is broken inside the extruder or PTFE
> tube."* — Máy **rút sợi nhựa khỏi đầu in thất bại** khi nhả nhựa về AMS.

**Nguyên nhân gốc (khả năng cao nhất, cần kiểm tra thực tế ở đầu in):**
PETG Eco nằm ở 240 °C suốt ~3,5 giờ; đầu sợi trong nozzle bị **phình/mềm dính**,
hoặc có **mảnh sợi gãy kẹt trong extruder / ống PTFE**. Khi AMS kéo ngược, sợi
không tuột ra được nên máy dừng để bạn xử lý — đây là **hành vi bảo vệ**, không
phải máy in hỏng.

**Cần làm (theo thứ tự):**
1. Lấy vật in ra — nó **đã in xong đủ 110 lớp**, kiểm tra chất lượng bình thường.
2. Mở nắp đầu in, xem sợi ở cụm extruder và ống PTFE có bị kẹt/gãy không.
3. Bấm **Retry / Continue** trên màn hình máy để máy thử nhả nhựa lại.
4. Nếu vẫn lỗi: hâm vòi lên ~250–260 °C rồi rút sợi bằng tay (đừng giật mạnh),
   cắt bỏ đoạn sợi phình ở đầu rồi mới nạp lại.

**Cách tránh cho lần in PETG dài sau:**
- Cắt **đầu sợi vuông, phẳng, không có burr** trước khi nạp — đầu sợi xù là nguyên
  nhân hay gặp nhất của việc không rút ra được.
- Sau bản in dài, đừng để máy tự rút ngay ở 240 °C; hạ nhiệt vòi xuống ~230–240 °C
  hoặc dùng lệnh **Unload thủ công** rồi mới để AMS rút.
- Nếu tái diễn nhiều lần → kiểm tra/thay ống PTFE và bánh răng extruder.

### Bài học #4 — bug công cụ: mã HMS bị ghép sai (đã sửa)

Monitor in ra `1302-0002` — **vô nghĩa**. Nguyên nhân: hàm cũ ghép
`(attr << 16) | code` trong khi 2 field MQTT là **2 nửa ĐỘC LẬP** của mã HMS:

```
attr = 301994752 = 0x12001300  ->  2 nhóm đầu  "1200-1300"
code = 131074    = 0x00020002  ->  2 nhóm sau  "0002-0002"
ma dung: 1200-1300-0002-0002
```

Đã sửa `_hms_hex(attr, code)` + thêm `_hms_vn()` tra theo cặp `module-error`
(khớp cả mã 2 nhóm như `1200-8015` lẫn mã 4 nhóm), và bổ sung 2 mã đã xác minh vào
bảng: `1200-8007` (đùn thất bại) và `1200-8015` (rút nhựa thất bại).

**Áp dụng cho lần sau:** gặp mã HMS mà bảng chưa có → tra
`wiki.bambulab.com/en/hms/error-code` rồi thêm vào `HMS_VN` để lần sau nhận ra ngay.

---

## 15/09/2026 — VẪN KẸT NHỰA ⇒ TỐC ĐỘ 161 mm/s LÀ QUÁ CAO

**Bằng chứng (không suy đoán):** preset đang dùng để tường/ruột **161 mm/s**
⇒ **13.52 mm³/s**, chỉ cách trần chảy 14 mm³/s đúng 3 %. Ghi chú của chính repo
(`analyzer.py` dòng 2151, mục `PETG ECO`) nói ngược lại điều đó:

> *"Cuộn eco KHÔNG chạy nhanh được — người dùng PETG-Eco trên forum Bambu phải
> hạ tốc **<100 mm/s** + mvs 14."*

**Cơ chế kẹt:** nhựa eco nóng chảy chậm hơn PETG thường. Ở 13.5 mm³/s, bánh răng
extruder đẩy nhựa nhanh hơn tốc độ nóng chảy → sợi bị **nghiền tại bánh răng**
(đúng nghĩa "kẹt nhựa"), kéo theo thiếu đùn. Và vì đầu sợi nằm ở 240 °C suốt 3 giờ,
nó phình ra trong nozzle — đây là gốc của lỗi **1200-8015** (không rút ra được) ở
cuối bản in 13/09.

### Bài học #5 — hạ tốc độ, đo lại bằng slice thật

Đã tạo preset **CHỐNG KẸT**, hạ cả trần chảy lẫn tốc độ:

| Thông số | Bản cũ | **Bản chống kẹt** |
|---|---|---|
| Trần chảy (mvs) | 14 mm³/s | **12 mm³/s** |
| Tường ngoài | 150 mm/s | **110 mm/s** |
| Tường trong / ruột / ruột đặc | 161 mm/s | **135 mm/s** |
| Mặt trên | 100 mm/s | **90 mm/s** |
| Lớp 1 | 30 mm/s · 0.20 mm | **25 mm/s · 0.24 mm** |
| Lưu lượng thực khi in | 13.52 mm³/s | **11.34 mm³/s** (−16 %) |

**Giá phải trả — đo bằng slice thật khay 3:** 3 h 02 m 28 s → **3 h 10 m 10 s**
(+7 m 42 s, **+4.2 %**), nhựa 46.37 g → **47.15 g**. Đổi 8 phút lấy việc hết kẹt là
rẻ.

**File:** `2.Process/LP_PETG_Eco_CHONGKET.json` và
`tablet-ipad-pink-PETG-Eco-CHONGKET.3mf` (+ preset nhựa `LP_PETG_Eco_FILAMENT.json`
đã sửa mvs 14 → **12**).

**Nếu vẫn còn kẹt, hạ tiếp theo thứ tự:** nhiệt 240 → **245 °C** (nhựa chảy dễ hơn,
giảm áp ngược) → mvs 12 → **10**, tường/ruột 135 → **120**.

**Bài học chung:** `mvs` chỉ là *trần lý thuyết của hotend*. Cuộn nhựa rẻ/eco có
trần thực thấp hơn — phải lấy con số **thực nghiệm của đúng cuộn đó**, không lấy
sát trần lý thuyết. Quy tắc an toàn: đặt tốc độ ≤ **85 %** trần lý thuyết khi chưa
kiểm chứng cuộn.

### Bài học #6 (16/09/2026) — biến luật 85 % thành MẶC ĐỊNH cho MỌI loại nhựa

Bài học #5 mới chỉ sửa **PETG Eco**. Nhưng lỗ hổng nằm ở tầng chung:
`flow_ceiling()` lấy `mvs` **từ khai báo trong file**, mà file thì hay khai số
*lý thuyết của hãng* — Matte stock 22, PETG HF 18, ABS gốc fdm 29. Tin theo là
tốc độ ra sát trần ⇒ kẹt. Đã vá **2 tầng độc lập** trong `analyzer.py`:

**Tầng 1 — biên an toàn toàn cục.** `SAFE_MARGIN = 0.85` (trước là 0.97).

| | Trước | Sau |
|---|---|---|
| Công thức tốc độ | `vmax × 0.97` | **`vmax × 0.85`** |
| Biên an toàn | 3 % | **15 %** |

3 % không phải biên — đó là *sát trần*. Trần của hãng là số lý tưởng (hotend
chuẩn, sợi khô hoàn hảo); hotend A1 là bản stock, sợi thực luôn ẩm hơn.

**Tầng 2 — kẹp trần theo nhóm nhựa.** `safe_mvs_ceiling()` nhận diện nhựa từ khai
báo trong file rồi **kẹp `mvs`** trước khi tính tốc độ — nên không còn phụ thuộc
vào việc file khai đúng hay sai:

| Nhóm | Trần dùng | Vì sao |
|---|---|---|
| PLA (Basic/Lite) | 21 | official A1, đã kiểm chứng chạy tốt |
| PLA Matte / Silk / CF / GF / Metal | 12 | bột độn + sợi cứng: dễ kẹt, mài mòn nozzle |
| PETG (thường / eco) | 12 | bài học kẹt 13/09 |
| PETG HF | 13 | chỉ đúng khi cuộn là HF thật |
| ABS / ASA | 14 | official A1 là 16/18 nhưng khung A1 hở, co ngót mạnh |
| TPU | 6 | đùn nhanh là buckling (sợi cong trong extruder) |
| PC / PA | 10 | nhiệt cao, dễ tích cặn |
| Không rõ loại | 12 | số thận trọng nhất |

**Kết quả đo lại (slice thật, PETG Eco, khay 3):**

| Chế độ | Lớp | Tường trong | Lưu lượng | % trần |
|---|---|---|---|---|
| FAST | 0.28 mm | 86 mm/s | 10.11 mm³/s | 84 % |
| BALANCED | 0.20 mm | 120 mm/s | 10.08 mm³/s | 84 % |
| QUALITY | 0.16 mm | 151 mm/s | 10.15 mm³/s | 85 % |

Trước đây chạy **96 %** trần. Nay **84-85 %**, cộng thêm trần đã bị kẹp về đúng
nhóm nhựa — hai lớp bảo vệ độc lập.

**Nguyên tắc chốt:** *chậm mà chắc*. Mất ~13 % tốc độ, đổi lấy việc **không bao
giờ mất 3-8 giờ in vì kẹt ở 90 %**. File cấu hình:
`1.Filament/LP_PETG_Eco_FILAMENT.json`,
`2.Process/LP_PETG_Eco_{FAST,BALANCED,QUALITY}.json` và
`tablet-ipad-pink-PETG-Eco.3mf` (mvs 12 cho cả 6 khe).

**Trạng thái bản in đang chạy (kiểm tra 16/09):** `tabletipad-pink_plate_3`,
lớp **10/110**, **55 %**, còn **92 phút**, nozzle 240 °C · bàn 80 °C,
`print_error = 0`, `hms = []` — **không kẹt, không lỗi**.

### Bài học #7 (16/09/2026) — HỎNG IM LẶNG: MÁY BÁO `FINISH` NHƯNG CHI TIẾT CHỈ CAO ~31 LỚP

> 🩸 **ĐÍNH CHÍNH.** Bản đầu của mục này tôi viết *"bản in đã xong 100 %, không kẹt"* —
> **SAI**. Tôi tin vào chữ `FINISH` của firmware. Người dùng lấy chi tiết ra thì nó
> **mỏng, chỉ cao khoảng 31 lớp**; ảnh camera lúc đó cho thấy bàn đã trống. Đây là
> kiểu hỏng tệ nhất: **máy báo thành công trong khi chi tiết bỏ đi.**

**Mốc thời gian thật** (từ `notify.log` của hub):

| Mốc | Thời điểm |
|---|---|
| BẮT ĐẦU IN | 2026-09-15 **21:52:52** |
| MỐC 30 % | 23:01:27 |
| MỐC 50 % | 23:46:47 |
| vision 70 % | 2026-09-16 00:31:50 → **KQ: ON** |
| MỐC 75 % | 00:42:45 |
| vision 90 % | 01:16:19 → **KQ: ON** |
| máy báo FINISH | 2026-09-16 **01:33:51** |

Thời gian máy chạy: **3h 41m 00s**. Nhưng **không phải 3h41m in ra chi tiết** — từ
khoảng lớp 31 trở đi máy **chạy đường đi mà không ra nhựa**. Ước lượng: chi tiết chỉ
nhận ~1/3 khối lượng nhựa mà file dự kiến (47.20 g).

**BẰNG CHỨNG CƠ CHẾ — đếm từ gcode (đã sửa cách đếm cho đúng chuẩn M83):**

| Số đo | Giá trị |
|---|---|
| Tổng số lần rút sợi (retraction) cả bản in | **81 780** |
| Tổng chiều dài travel | **257.8 m** |
| Lớp 1 | 18 526 đoạn in · **3 066 lần rút** · 10.2 m travel |
| Lớp 2 | 21 754 đoạn in · **5 563 lần rút** · 11.6 m travel |
| Lớp 11 | 21 222 đoạn in · **5 749 lần rút** · 12.0 m travel |
| Lớp 17–40 (vùng trụ) | ~85 đoạn in · **15–26 lần rút** · 0.8 m travel |

🩸 **Lớp 1–14 (vùng lưới Voronoi) mỗi lớp có ~5 000–5 700 lần rút sợi và ~12 mét
travel.** Đó là mật độ phi lý — hệ quả trực tiếp của việc một lớp có hàng nghìn đảo
nhỏ, mỗi đảo cần một travel + rút sợi. Cộng dồn ~80 000 lần rút chỉ trong 2.8 mm đầu.

**Hai giả thuyết, cùng trỏ vào một vùng thủ phạm:**

1. **Bánh răng extruder nghiền sợi do rút quá nhiều.** Mỗi chu kỳ rút–nhả bào mòn một
   chút; ~80 000 chu kỳ ở lớp 1–14 tạo vết dẹt trên sợi → mất độ bám → lớp ~31 hết
   đẩy được nhựa. **Hỏng tích luỹ, biểu hiện muộn** — khớp với việc nó chết ở vùng
   trụ (nơi mật độ rút chỉ 15–26/lớp) chứ không chết ngay giữa lưới.
2. **Lưu lượng đỉnh vượt trần.** Lớp 2–14 đo được **13.16 mm³/s = 110 % trần 12**
   (Arachne in đường rộng tới 0.60 mm trong khi trần tính theo 0.42). Vùng này **trùng
   đúng vùng đã kẹt ngày 13/09**. Nay có thêm bằng chứng thứ hai: 13.16 cũng hỏng.

**So sánh hai lần in cùng model — biên an toàn thật rất mỏng:**

| | 13/09 | 16/09 |
|---|---|---|
| Lưu lượng đỉnh (đo từ gcode) | ~13.5 mm³/s | **13.16 mm³/s** |
| %trần | 96 % | 94 % |
| Kết quả | kẹt ở 90 %, lỗi 1200-8015 | **hỏng im lặng ở ~lớp 31** |

⇒ Hai lần hỏng chỉ cách nhau **2.5 % lưu lượng đỉnh**. Chạy sát trần ở cuộn nhựa này
**luôn hỏng** — khác nhau chỉ ở chỗ hỏng *ồn ào* hay *im lặng*.

**Bài học lớn nhất — `FINISH` KHÔNG PHẢI LÀ BẰNG CHỨNG:**

- Firmware chỉ biết nó đã chạy hết file. Nó **không biết nhựa có ra hay không**.
  `print_error = 0` + `hms = []` + 110/110 lớp là **cổng luôn xanh**: đo *máy có chạy*,
  không đo *chi tiết có hình thành*.
- Cả hai mốc vision 70 % và 90 % của hub đều trả **ON** — vì AI soi camera tìm
  spaghetti/rủ/lệch, **không đo chiều cao khối in**. Chi tiết đứng yên ở 6 mm nên ảnh
  trông "bình thường".
- ⇒ Máy nào báo xong, **vẫn phải cân/gõ chi tiết**. Trước khi có bước kiểm đó, mọi
  kết luận "in thành công" từ telemetry đều là phỏng đoán.

**Việc cần làm để chốt thủ phạm (1 phút):** rút sợi ra soi chỗ bánh răng ăn vào —
thấy **vết dẹt/mài bóng** là giả thuyết 1; sợi còn nguyên mà đầu nozzle tắc cứng là
giả thuyết 2. Kết quả này quyết định sửa `retraction` hay sửa `trần lưu lượng`.

### Bài học #8 (16/09/2026) — GIẢ ĐỊNH "CHẬM MÀ CHẮC" SAI. CHẬM HƠN THÌ HỎNG SỚM HƠN

> 🩸 **ĐÍNH CHÍNH LẦN 2.** Bài học #6 tôi chốt *"chậm mà chắc — mất 13 % tốc độ đổi
> lấy không mất 3-8 h in"*. Bản in tối 16/09 **bác bỏ điều đó**.

**Bản in tối 16/09 (cấu hình tôi vừa sửa) — HUỶ ở lớp 9:**

| | |
|---|---|
| HMS | **`0300-400C`** |
| Nghĩa wiki Bambu | *"Printing was cancelled"* — **mã CHUNG, KHÔNG chẩn đoán được nguyên nhân** |
| Chết ở | **lớp 9 / 110** (≈ Z 1.8 mm) |

> 🩸 **ĐÍNH CHÍNH (17/09/2026).** Bản đầu của mục này tôi viết *"module 0300 = cảm biến
> lực đùn ⇒ máy phát hiện quá tải lực đùn rồi tự huỷ"*. **SAI.** Tra wiki Bambu:
> `0300-400C` chỉ nghĩa **"Printing was cancelled"** — nó ghi *việc bị huỷ*, không ghi
> *vì sao*. Cảm biến lực đùn/eddy-current của A1 là nhóm **`0300-1800-xxxx`**.
> Muốn biết nguyên nhân phải tìm các mã cụ thể: **`0300-4006` = "The nozzle is clogged"**,
> `0300-4005` = quạt nozzle, `0300-0900-0002-0001` = lực đùn.

Điểm tích cực vẫn giữ: lần này máy **có dừng và báo** (khác 16/09 sáng, nó chạy câm
79 lớp rồi báo FINISH).

**Bằng chứng không thể chối — xếp theo tốc độ tường trong:**

| Tốc độ | mvs | Kết quả | Đi được |
|---|---|---|---|
| **161 mm/s** | 14 | kẹt | **90 %** |
| **135 mm/s** | 12 | hỏng câm ở lớp ~18 | ~82 % |
| **113 mm/s** | 12 | **HUỶ ở lớp 9** | **~50 %** |

🩸 **Đơn điệu: chậm hơn ⇒ hỏng sớm hơn.** Giả định "chậm mà chắc" bị dữ liệu bác bỏ.

**Vì sao mô hình của tôi sai (2 lỗi lập luận, không phải lỗi số):**

1. **Hạ tốc độ làm ĐỈNH lưu lượng TĂNG, không giảm.** Đo trên chính gcode: 135 → 113 mm/s
   mà đỉnh 13.16 → **13.87** mm³/s. Vì Arachne bù bằng cách in đường **rộng hơn**.
   Tôi *đã thấy* con số này rồi **đổi thước đo** (sang chiều-dài-vượt-trần) để tự thuyết
   phục — đó là lỗi lập luận.
2. **Bỏ qua cơ chế nhiệt.** Nhựa đi **chậm** ⇒ lưu lâu trong hotend ⇒ **heat creep**
   (nhiệt leo ngược lên trên buồng nóng) ⇒ sợi mềm/phình ⇒ tắc ⇒ cảm biến lực đùn ngắt.
   ⇒ **Chậm hơn = heat creep nặng hơn.** Đúng chiều với dữ liệu.

**Đã sửa (commit sau bài học này):**

| Thay đổi | Trước | Sau | Lý do |
|---|---|---|---|
| `SAFE_MARGIN` | 0.85 (suy diễn) | **0.95 → ~134 mm/s** | lấy mốc **đã đo** (135 đi xa nhất), không suy diễn |
| `reduce_crossing_wall` | 1 (tôi bật) | **bỏ** | bật lên cắt retraction 36 % nhưng **tăng travel** → dễ kéo sợi; chưa chứng minh được lợi |
| `filament_max_volumetric_speed` | 12 | **12** giữ | hồ sơ **chính hãng TINMORRY cho A1** cũng ghi 12 |

**Nguồn chính hãng đã tìm được** — `TINMORRY-filament-profile-for-Bambu-printers`,
`PETG-ECO (A1-Bambu-TINMORRY).json`:

```json
{ "filament_max_volumetric_speed": ["12"],  "filament_flow_ratio": ["0.96"],
  "nozzle_temperature": ["245"],  "nozzle_temperature_initial_layer": ["240"],
  "inherits": "Generic PETG @BBL A1" }
```

⇒ **mvs 12 được hãng xác nhận** (không phải 14). Nhưng ta đang lệch hãng ở
`flow_ratio` (0.94 vs **0.96**) và `nozzle` (240 vs **245**). Và đáng chú ý:
preset nền `Generic PETG @base` của Bambu để bàn **70 °C**, còn ta (và `@BBL A1`)
để **80 °C** — bàn nóng hơn ⇒ buồng nóng hơn ⇒ heat creep mạnh hơn.

**LUẬT MỚI, từ đây áp dụng:**

1. **Một lần chỉ đổi MỘT biến.** Tối 16/09 tôi đổi 2 thứ cùng lúc (tốc độ + reduce_cross)
   nên không tách được nguyên nhân. Đó là lỗi phương pháp.
2. **Đừng đốt 2-3 giờ cho một phép thử.** Ba lần liên tiếp hỏng ở 2-3 h/bản. Phải in
   **mẫu test nhỏ** (tháp nhiệt / panel thu nhỏ) — 15-20 phút/vòng.
3. **Ưu tiên nghi vấn VẬT LÝ trước khi chỉnh slicer.** Ba cấu hình khác nhau, ba điểm
   chết khác nhau, càng "thận trọng" càng chết sớm ⇒ nguyên nhân không nằm ở slicer.
   Nghi vấn hàng đầu: **hotend tích cặn / heat creep / nhựa ẩm / ống PTFE**.

**Phép thử kế tiếp (một biến duy nhất):** vệ sinh hotend (cold pull 260 → 90 °C) rồi
in lại với **bàn 70 °C** thay vì 80 °C. Giữ mọi thứ khác nguyên.

### Bài học #9 (17/09/2026) — ĐỐI CHIẾU CỘNG ĐỒNG + WIKI HÃNG (có nguồn)

Điều tra qua wiki Bambu / forum Bambu / r/BambuLab / Prusa KB. Chỉ ghi thứ **có URL**;
chỗ nào không có nguồn thì ghi rõ là phỏng đoán.

**a) Mã lỗi — đọc đúng mới chẩn đúng**

| Mã | Nghĩa thật (nguồn: wiki.bambulab.com/en/hms/error-code) |
|---|---|
| `0300-400C` | "Printing was cancelled" — **mã chung**, không nói nguyên nhân |
| **`0300-4006`** | **"The nozzle is clogged"** ← đây mới là mã cần tìm khi nghi kẹt |
| `0300-1800-xxxx` | "The extruder **eddy current sensor** signal is abnormal" — cảm biến lực đùn A1 |
| **`1000-C001`** | **"High bed temperature may lead to filament clogging in the nozzle"** |
| `1200-8015` | "Failed to pull out the filament from the toolhead. Please check if the filament is stuck, or the filament is broken inside the extruder or **PTFE tube**" |

⇒ Lỗi 13/09 (`1200-8015`) trỏ về **kẹt/đứt sợi trong extruder hoặc ống PTFE** — không
phải cảm biến lực. Và lỗi 16/09 tối (`0300-400C`) **không dùng để chẩn đoán** được.

**b) Heat creep — hãng THỪA NHẬN A1 có**

> *"A common clog that occurs on **A1 series** is the filament getting stuck inside the
> hotend due to **heat creep** issues."* — wiki Bambu, trang unclog A1/A1 mini

Và cơ chế "chậm ⇒ tệ hơn" có nguồn:

> *"**A slow print can cause heat creep**…"* — Prusa Knowledge Base, bài heat creep

> *"Going too slow means that this same heat energy no longer has enough filament
> volumetrically to transfer it to, and instead transfers it to the [filament]"* — r/BambuLab

🩸 **Khớp đúng thứ tự hỏng của ta: 161 mm/s → 90 %, 135 mm/s → lớp 18, 113 mm/s → lớp 9.**
Chậm hơn ⇒ nhựa lưu lâu trong hotend ⇒ nhận nhiều nhiệt hơn ⇒ mềm/phình ⇒ tắc.

**c) Bàn 80 °C là nghi vấn có mã lỗi riêng của hãng**

`1000-C001` nói thẳng *"High bed temperature may lead to filament clogging in the nozzle"*,
và wiki khuyên với PETG *"reduce the bed temperature when possible"*. Preset nền
`Generic PETG @base` của Bambu để **70 °C**. ⇒ Đã hạ bàn **80 → 75 °C** (giao của
hãng 75-90 · handover 75-80 · Bambu base 70).

**d) Nhiệt nozzle — KHÔNG có bằng chứng 250-260 °C gây kẹt trên A1**

Có tiền lệ A1 dùng **260-265 °C + hạ mvs xuống 10** cho PETG (forum Bambu A1 combo).
Đây là **cân bằng giữa under-melting và heat creep**, không phải "càng cao càng tốt".
⇒ Giữ **240 °C**, chỉ tăng nếu chứng minh được là thiếu nhiệt.

**e) Lịch bảo trì hãng (wiki Bambu — basic maintenance A1)** — phần ta CHƯA làm lần nào:

| Việc | Chu kỳ |
|---|---|
| **Cold pull** | **≥ 1 lần / tháng** |
| Vệ sinh **quạt làm mát hotend** | **mỗi tuần** ← heat creep là hệ quả trực tiếp của mất làm mát |
| Vệ sinh bánh răng đùn + nozzle | mỗi **5 cuộn** |
| Thay **ống PTFE** | mỗi **6 cuộn** |
| Kiểm tra lưỡi cắt | mỗi **3 cuộn** |

**f) Sấy nhựa**: lò đối lưu **60-65 °C / 8 h**. Lưu ý **A1 không dùng bàn nhiệt để sấy được**.

**g) Cảnh báo quan trọng — có thể là HAI lỗi khác nhau, đừng gộp**

Bản 16/09 sáng (chạy câm 92 lớp rồi báo FINISH) **không khớp heat creep kinh điển**.
Nó khớp hơn với ca đã có nguồn ở `bambulab/BambuStudio#4624`:
> *"the printer stops feeding filament through the nozzle. **No error is reported** and
> the printer continues regardless, not printing."*

⇒ Giả thuyết: **(a)** tắc/đùn kém mà firmware không phát hiện, và **(b)** lần bị ngắt có
báo. Đừng coi cả ba lần hỏng là một nguyên nhân.

**h) KHÔNG tìm được nguồn (vẫn là phỏng đoán)**

- Không có nguồn nói **PETG ẩm gây kẹt cứng ngắt cảm biến lực** — chỉ có nguồn cho
  "chảy kém, bọt, tắc một phần, bề mặt nhám".
- Không có nguồn nói **250-260 °C gây heat creep/kẹt trên A1**.
- Không có ca cộng đồng nào khớp số **"hạ tốc ⇒ kẹt sớm hơn 90 %→18→9"** — chỉ có
  nguyên lý chung.
- Không có nguồn nào nói **`reduce_crossing_wall`** liên quan kẹt nhựa.

---

## Nhật ký sự kiện (tự động — đã gộp mục trùng)

> Ghi chú: các mục trước **01:26 ngày 14/09** in mã HMS theo hàm ghép cũ
> (sai) nên hiện `1302-0002`; mã đúng là `1200-1300-0002-0002` như đã sửa ở Bài học #4.

- **2026-09-13 21:58:40** · `START` — job=tabletipad-pink_plate_3

- **2026-09-13 21:58:40** · `BASELINE` — lúc vào in thật: nozzle đích 240C ·

- **2026-09-13 22:25:20** · `START` — job=tabletipad-pink_plate_3 file=tabletipad-pink_plate_3.gcode.3mf layers=110  
  `ams=['khe 1=PLA/4DAFDA', 'khe 2=PLA/68724D', 'khe 3=PLA/E8AFCF', 'khe 4=PETG/A4AAAC']`

- **2026-09-13 22:25:20** · `BASELINE` — AMS lúc bắt đầu: khe 1=PLA/4DAFDA | khe 2=PLA/68724D | khe 3=PLA/E8AFCF | khe 4=PETG/A4AAAC

- **2026-09-13 22:25:20** · `BASELINE` — Lúc vào in thật: nozzle đích 240C · bàn đích 80C · quạt 0% · 110 lớp

- **2026-09-14 01:24:21** · `HMS` — mã 1302-0002 (chưa có trong bảng — tra wiki.bambulab.com)    _(lặp ×18)_
  `state=PAUSE · layer=110`

- **2026-09-14 01:24:21** · `PRINT_ERROR` — print_error=302022677    _(lặp ×18)_
  `state=PAUSE · layer=110`
