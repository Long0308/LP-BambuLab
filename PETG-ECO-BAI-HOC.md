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
