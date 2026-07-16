# TODO phiên sau — LP-BambuLab hub

> Cập nhật 2026-07-16 (phiên 2). Mọi số trong đây là **đo thật**, không phải ước lượng.
> Phiên này đã xong T1/T2/T3/T4/T5 của danh sách cũ. Đọc phần "Đã chốt" trước khi làm gì.

---

## ✅ ĐÃ XONG PHIÊN NÀY (2026-07-16)

### T1. Ngân sách thời gian — CHỐT NGHĨA + LÀM XONG
User chốt: **ngân sách = thời gian in so với default `0.20mm Standard @BBL A1`**,
**mục tiêu +1h30, sai số chấp nhận tới +2h — "đừng cố ép"**. Lever kỹ thuật
(warping / kéo sợi / vật cao / brim / support hốc rãnh / trần mvs chống kẹt)
**không bao giờ bị cắt**. Hub là "chuyên gia tư vấn, không cứng nhắc": vượt mục tiêu
nhưng trong sai số → giữ chất lượng + note giải thích.

- `optimize_e2e.py`: `BUDGET_S=90*60` (mục tiêu) + `BUDGET_TOL_S=30*60` (sai số) +
  `trim_ladder()` (bậc thang cắt theo GIÁ ĐO THẬT) + guard trong `run_modes()`
  (slice lại sau mỗi bước cắt, ghi rõ đã cắt gì / tiết kiệm bao nhiêu).
- Bậc thang cắt (giá đo A/B BUCKET khay 1, baseline 3h22m54s/119.33g):
  ủi mặt trên −19m28s → ruột 12→8% −9m16s → gyroid→adaptive −4m39s →
  tường 3→2 −32m07s → thành ngoài thả về fast −7m04s → vỏ −6m07s →
  layer notch −45m34s (kèm scale tốc độ theo trần mvs mới — không tự vi phạm luật chống kẹt).
- **Số xác nhận BUCKET khay 1** (cap mới): Nhanh 3h14m (−8m54s) · Cân bằng 4h44m39s
  (+1h21m45s, trong mục tiêu) · Đẹp 5h09m52s (+1h46m58s — cắt 3 bước rẻ, GIỮ layer
  0.16/outer 110/shells 7/5/accel 3000, note tư vấn).
- **Phát hiện quan trọng**: `enable_support` bật trên BUCKET = **+0 giây** (threshold
  30° không sinh support) — TODO cũ xếp #1 tốn giờ là SAI. Thủ phạm thật: walls3
  +32m, mvs-cap-138 +23m, tall accel3000 +24m.
- `bench_ab.py` (mới): A/B từng lever, `--plate N` chọn khay. `gold_run.py` (mới):
  chạy run_modes toàn bộ file trong Downloads → `slice_jobs/gold/GOLD-SET.md`.

### T2. Tab Plate 1/2/3 + ảnh khay — XONG
- `_run_analyze(plate=N)` + bóc `Metadata/plate_N.png` ra `slice_jobs/plateimg/`.
- GET `/api/plateimg?name=&plate=` phục vụ ảnh; `POST /api/analyze?plate=N` chọn khay.
- UI `/analyze`: card tab khay (ảnh + tên + số vật thể, khay active viền xanh),
  bấm khay → `rePlate(n)` gửi lại file phân tích theo khay.

### T3. Combo box nhựa + tải filament preset — XONG
- GET `/api/filpreset?fil=<tên>&custom=` → `analyzer.filament_preset` (JSON riêng,
  cạnh file process — user chốt không nhét vào 3mf).
- UI: combo (khay AMS thật lên đầu + 13 key FIL_EXPORT) + nút tải .json + hiện
  inherits đã-xác-minh/suy-luận.

### T4. Bug cân nặng đa màu — XONG
Root cause thật: Bambu ghi **nhiều số trên 1 dòng phân cách phẩy** (`106.56,12.77`),
regex `[\d.]+` dừng ở phẩy. Fix 3 chỗ: `slicer_cli._WEIGHT_PAT`,
`filament_ftp._HDR_PATS`, hub HTML. Xác minh: 119.33g khớp GUI.

### T5. Generic PLA — XONG
`GENERIC PLA` → inherits `Generic PLA @BBL A1` — xác minh 2 nguồn (BUCKET.3mf thật +
GitHub official). Safe: 220°C / mvs 12 / flow 0.98 / bàn 65. Bonus: PLA METAL
verified=True.

### Hạ tầng
- `slicer_cli.slice_3mf(plate=N)`: `--slice N` chỉ slice khay chọn (nhanh gấp 3);
  `total_secs` = `total_predication` (CÙNG THANG số GUI, gồm flush/mồi — dùng số này
  so ngân sách, KHÔNG dùng "model printing time" header).
- Chống 2 quirk CLI đo thật: **treo ở bước thoát** sau khi đã ghi xong kết quả
  (pipe capture_output → chờ 30'; fix: log ra file + poll + kill cây process) và
  **crash ngẫu nhiên** (retry). Quirk treo hay gặp khi Bambu Studio GUI đang mở.

---

## ✅ THÊM PHIÊN NÀY (đêm 2026-07-16): CAMERA + CHUÔNG

- `camera_stream.py`: camera A1 tích hợp qua cổng 6000 (TLS + bblp + Access Code,
  frame JPEG header 16B — OpenBambuAPI). 1 thread bơm cache frame, n viewer = 1 kết
  nối, tự ngắt sau 15s không ai xem. Đo thật: frame đầu ~2s, poll sau 0.2s, nguồn
  ~1 frame/2s (giới hạn phần cứng A1 — KHÔNG tối ưu fps được).
- `/api/camera` (MJPEG) + `/api/camera.jpg`; UI dashboard dùng **double-buffer poll
  1.2s** (không dùng MJPEG trong <img> — xé hình trên mạng chậm).
- `notify.py`: ntfy/Telegram/Discord qua `.env` (đọc lại mỗi lần — sửa không cần
  restart). Hook MQTT: FINISH ✅ / FAILED 🚨 / PAUSE giữa chừng 🚨 (chỉ khi CHUYỂN
  trạng thái). `/api/notify-test` + nút test trên dashboard + chuông web WebAudio.
- **Telegram ĐÃ cấu hình chạy thật** (bot LPHome_A1_2026_bot, token+chat_id trong
  `.env` — gitignore, KHÔNG push). User đã nhận tin test.
- Audit FIL_EXPORT 13 nhựa vs official 2 tầng: fix ASA inherits 404, PETG HF bug
  2 tầng, ABS mvs 29→16, TPU 4 số, SILK/CF mvs hạ về official, họ PLA bàn 65.
- Ý tưởng phiên sau: đính kèm ẢNH camera vào tin Telegram khi báo (sendPhoto —
  notify.py + camera_stream.get_frame ghép là xong); user cân nhắc /revoke token
  đã lộ trong chat rồi thay .env.

## VIỆC PHIÊN SAU

0. **KẾT QUẢ GOLD SET (đã chạy xong 2026-07-16, 83 file Downloads)** —
   `slice_jobs/gold/GOLD-SET.md` + `gold_results.jsonl`:
   - 79/83 phân tích OK; 4 lỗi THẬT của file: `son fix.3mf` + `無印良品風.stl`
     (plate rỗng −50), `Raupe.3mf` (G-code ngoài vùng in −104, model to hơn bàn A1),
     `Body 14 - LP LP FIX.gcode.3mf` (−6 không parse — file gcode.3mf đã slice).
   - Lọt mục tiêu +1h30: Nhanh 75/76 · Cân bằng 70/76 · Đẹp 60/76.
     Trong sai số +2h thêm: Cân bằng 5 · Đẹp 13 (giữ chất lượng + note tư vấn).
   - VƯỢT +2h (3 ca, đều đã cắt hết lever cho phép, note trung thực):
     `Modular_Storage_System` quality +2h36m (baseline là profile P2S — có cảnh báo
     máy khác rồi) và `AMS+Lite+Top+Mount-Final.3mf` cả 3 mode (+6h50m..+9h21m,
     fast +6h50 với 0 bước cắt!) → **ĐIỀU TRA PHIÊN SAU**: nghi mvs cap theo
     filament khai báo trong file (PETG mvs thấp?) đội thời gian — soi
     `gold_results.jsonl` + config nhúng file này trước khi sửa gì.
   - BÀI HỌC vận hành: 22 file từng fail `return_code=None` vì chạy 2 process CLI
     song song (gold + verify tay) — CLI_LOCK chỉ chống trong 1 process. Đừng slice
     tay khi gold đang chạy; cân nhắc file-lock liên process nếu tái diễn.
2. **Xử lý findings code-reviewer** (nếu phiên này chưa xử lý hết — xem git log).
3. Cân nhắc: note ngân sách hiển thị trong hub UI optimize (hiện chỉ có trong JSON
   report — UI `/api/optstatus` render thêm `budget.note` + `trims`).
4. Ý tưởng data-driven từ gold set: mvs cap là nguồn chậm lớn nhất với PLA Matte —
   cân nhắc chỉ cap tốc độ khi khay AMS THẬT là Matte/Metal, thay vì theo khai báo file.
5. **Nghịch lý dễ gây hiểu lầm** (đo thật Notebook_stand, base 11h34m): Cân bằng
   13h30 > Đẹp 12h05 — vì Đẹp bị guard cắt tường 3→2 còn Cân bằng giữ tường 3 (vẫn
   lọt cap). Cân nhắc: sau khi slice đủ 3 mode, nếu Cân bằng > Đẹp thì thêm note
   giải thích (hoặc đồng bộ bậc cắt giữa 2 mode). Đừng sửa mù — soi jsonl trước.

---

## Ground truth đã xác minh (đừng tra lại)

- Baseline BUCKET khay 1: `total_predication` **12174s = 3h22m54s** (= số GUI 3h23m);
  header "model printing time" 3h16m36s là thời gian in thuần (không flush).
  Cân nặng 106.56 + 12.77 = **119.33g** (2 nhựa).
- `0.20mm Standard @BBL A1` (GitHub official): chỉ override accel 6000 + travel 700
  + elephant foot 0.075, còn lại kế thừa `fdm_process_single_0.20`. Khớp 100% ảnh
  Studio user + config nhúng BUCKET.3mf.
- Tên inherits filament đã xác minh: `Bambu PLA Lite/Matte/Metal @BBL A1`,
  `Bambu PETG Basic @BBL A1`, `Generic PLA @BBL A1` (2 nguồn).
- Giá lever (A/B BUCKET khay 1, s so với 12174s): layer016 +2734 · walls3 +1927 ·
  tall3000 +1449 · mvs138 +1407 · ironing +1168 · tall4000 +947 · infill12 +556 ·
  outer150 +424 · shells64 +367 · arachne +288 (−5.9g) · narrow_top +141 ·
  gyroid vs adaptive +279 · support +0 · layer028 −1864.