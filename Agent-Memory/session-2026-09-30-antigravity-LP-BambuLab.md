# SESSION NOTE — 2026-09-30 — Antigravity — LP-BambuLab

- **Project:** LP-BambuLab (`d:\15.BambuStudio`)
- **IDE:** Antigravity IDE
- **Thiết bị:** Bambu Lab A1 + AMS Lite + Bàn Textured PEI
- **Bản in thực tế đang chạy:** `【一键打印】实力派书立` (Chặn sách, file `书架书立2.3mf`, 833 lớp)

---

## 1. Tóm tắt cốt lõi phiên làm việc (Ground Truth)

### A. Sự cố & Phân tích chuyên sâu trong ngày:
1. **Lỗi đỏ: `A G-code path goes beyond plate boundaries`:**
   - Xảy ra khi slice mô hình kích thước sát mép bàn in A1 ($250.0 \times 105.0 \times 233.1 \text{ mm}$ trên bàn $256 \times 256 \text{ mm}$).
   - **Nguyên nhân gốc rễ:**
     - `Prime Tower` (Tháp xả) tự động bật khi mix vật liệu (PETG + PLA), bị văng ra ngoài mép bàn hoặc lấn vào vùng cấm cắt sợi của A1.
     - `Brim 5-10mm` khiến $250 + 2 \times 5 = 260\text{mm} > 256\text{mm}$.
     - Chân đế Tree Support xòe ngang ra ngoài mép.
   - **Giải pháp chuẩn:** Khi cạnh mô hình $\ge 240\text{mm}$, bắt buộc cấu hình `enable_prime_tower: 0`, `brim_type: no_brim`, `support_on_build_plate_only: 1`. Đã tích hợp tự động vào `analyzer.py`.

2. **Sự cố thời gian in vọt lên 18h35m (Bẫy đổi sợi 354 lần):**
   - **Hiện tượng:** Studio báo in mất 18 tiếng 35 phút, xả rác 51g nhựa (`Filament change times: 354`).
   - **Nguyên nhân kép:**
     1. Lệch khay cùng loại nhựa: Thân in chọn Khay 1 (PETG) nhưng cành Support lại gán Khay 4 (PETG) $\rightarrow$ AMS tráo qua lại giữa 2 khay PETG trên từng lớp!
     2. Support tự động đâm vào từng lỗ lục giác nghiêng trên vách thân $\rightarrow$ sinh ra 354 tầng interface PLA.
   - **Xử lý:** Khóa chung Khay 4 cho cả Thân và Cành Support; Chặn (Block) support ở các lỗ lục giác nghiêng $\rightarrow$ thời gian tụt ngay từ **18h35m xuống còn ~10h26m** (tiết kiệm hơn 8 tiếng).

3. **Cơ chế Support Khác Loại (PETG thân + PLA interface):**
   - Đệm PLA được phép để `Top Z distance = 0.0 mm` và `Top interface spacing = 0.0 mm` để tạo mặt đáy phẳng gương không tì vết (do PLA và PETG trơ hóa học).
   - Còn bản rơi tự do (như sáng 29/09) để `Top Z = 0.36 mm` + `spacing = 0.30 mm`.

---

## 2. Trạng thái máy in thời gian thực (Telemetry LAN lúc 21:58):
- **Trạng thái:** `RUNNING`
- **File:** `【一键打印】实力派书立` (833 lớp, layer 0.28mm)
- **Tiến độ:** Lớp 0/833, còn lại 626 phút (~10 giờ 26 phút)
- **Nhiệt độ:** Vòi $255^\circ\text{C}$ (đang đạt $252.4^\circ\text{C}$), Bàn $80^\circ\text{C}$ (đang đạt $79.4^\circ\text{C}$)
- **Khay đang in:** AMS Tray 3 (Khay 4 thật: PETG màu xanh ngọc `A4DAE6FF`)
- **Quạt:** Part cooling `0%` (chuẩn lớp 1 bám bàn)
- **Lỗi:** `print_error = 0`, `hms = []` (Máy vận hành hoàn hảo)

---

## 3. Các file đã cập nhật và đồng bộ:
- `d:\15.BambuStudio\analyzer.py`: Thêm luật bảo vệ mô hình sát mép bàn $\ge 240\text{mm}$ (tự tắt Prime Tower, tự chuyển no-brim, chống lỗi G-code beyond boundaries).
- `d:\15.BambuStudio\LP-Process-BookStand-PETG4-SupPLA.json`: Cấu hình hoàn chỉnh cho mẫu chặn sách khổng lồ.
- `d:\15.BambuStudio\Agent-Memory\session-2026-09-30-antigravity-LP-BambuLab.md`: Ghi nhật ký chi tiết.
- `d:\15.BambuStudio\HANDOVER.md`: Cập nhật mốc 30/09/2026.
