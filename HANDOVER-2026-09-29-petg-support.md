# HANDOVER — Bambu Lab A1 (29/09/2026)
## Chuyên đề: Quy Chuẩn PETG & Support (Khác Loại vs Cùng Loại)

**Ngày cập nhật:** 2026-09-29 22:20 · **Nhánh:** main · **Thiết bị:** Bambu Lab A1 + AMS Lite + Bàn Textured PEI

---

### 1. Bối cảnh & Mục tiêu phiên 29/09/2026
Xử lý dứt điểm 2 bài toán in PETG Tinmorry/Eco trên máy A1:
1. **Support bóc sạch, không dính chết, không rách vách chi tiết cơ khí (Cantilever Box).**
2. **Đáy chi tiết bám bàn 100% không bung trôi, nhưng khi nguội phải tự nhả, bóc viền brim nhẹ nhàng không bị cứng.**
3. **Phân định rạch ròi 4 trường hợp Support trong hệ thống và bộ não AI Agent (Web + Slack + Telegram).**

---

### 2. Quy chuẩn 4 trường hợp Support (KHÔNG ĐƯỢC NHẦM LẪN)

#### Trường hợp 1: KHÁC LOẠI — Thân PETG + Support Interface là PLA (Bản in sáng 29/09)
* **Cơ chế:** PLA và PETG không bám dính phân tử hoá học ở nhiệt độ in FDM.
* **Thực nghiệm sáng nay (05:48 AM):**
  * Profile `test suppport.json` được tạo với **`support_top_z_distance: 0.36 mm`**, `support_interface_spacing: 0.3 mm`, `Tree Slim`.
  * **Tại sao sáng nay bóc rơi tự do?** Vì kết hợp **khoảng hở 0.36mm** CỘNG VỚI **bản chất không dính của PLA và PETG**, nên lớp support hoàn toàn không thể bám vào đáy, nhấc lên là rơi ra sạch bóng!
* **Tùy chọn nâng cao (Mặt phẳng gương):** Với khác loại, bạn cũng có thể để `Top Z = 0.0 mm` và `Spacing = 0.0 mm` để đáy bóng như mặt kính.
* Flush volume: PLA→PETG ~650 mm³, PETG→PLA ~250 mm³.

#### Trường hợp 2: KHÁC LOẠI — Thân PLA + Support Interface là PETG
* Tương tự trường hợp 1. PETG làm đệm cho thân PLA.
* `Top Z = 0.0 mm`, `Spacing = 0.0 mm`. Bàn nhiệt giữ theo thân PLA (55–65°C).

#### Trường hợp 3: CÙNG LOẠI PLA (Thân PLA + Support PLA)
* Nhựa PLA giòn, liên kết vừa phải.
* `Top Z`: 0.15–0.20 mm (mặt đẹp) hoặc 0.25 mm (dễ gỡ). `Spacing`: 0.20–0.30 mm.

#### Trường hợp 4: CÙNG LOẠI PETG (Thân PETG + Support PETG — Nguy cơ dính chết cao nhất)
* **CẢNH BÁO ⚠️:** PETG ở 248°C dính lớp cực mạnh. Cùng loại mà để Z=0 hoặc <0.2mm sẽ **HÀN NHIỆT DÍNH CHẾT**, gỡ ra là vỡ hộp.
* **Bộ thông số vàng đã kiểm chứng:**
  * `support_type`: **`tree(auto)`** + `support_style`: **`tree_slim`** (tránh xa normal grid).
  * `support_top_z_distance`: **`0.36 mm`** (khe đệm không khí ~1.8–2× layer height).
  * `support_bottom_z_distance`: **`0.20 mm`**.
  * `support_interface_spacing`: **`0.30 mm`** (lưới thưa, TUYỆT ĐỐI không để 0.0mm).
  * `support_interface_top_layers`: 2 lớp, pattern `rectilinear_interlaced`, tốc độ `30–35 mm/s`.
  * `support_object_xy_distance`: **`0.70 mm`** (cách xa vách hộp, chống lem vào thành đứng).
  * `overhang_fan_speed`: **`80% – 100%`** (làm lạnh sốc đông cứng sợi nhựa).
  * `bridge_flow`: **`0.95`** (sợi căng, không võng).

---

### 3. Quy chuẩn Bám Bàn & Gỡ Đáy PETG trên Textured PEI

| Thông số | Giá trị | Giải thích lý do kỹ thuật |
| :--- | :---: | :--- |
| **Bàn nhiệt (`Textured PEI`)** | **`80°C`** | Bắt buộc 80°C từ đầu đến cuối để PETG Tinmorry bám chắc. *(Hạ 70°C sẽ bung/trôi bàn ngay)* |
| **Chiều cao lớp đầu (`Initial layer height`)** | **`0.20 mm`** | Vòi ép đầm chắc sợi nhựa vào gai bàn. *(Nâng lên 0.24mm sẽ mất squish gây bung bàn)* |
| **Bề rộng đường in lớp đầu** | **`0.42 mm`** | Thanh thoát theo vòi 0.4, không ép phè sang kẽ gai như mức 0.50mm |
| **Khe viền Brim (`brim_object_gap`)** | **`0.18 mm`** | Hồi sáng để 0.10mm bị hàn dính chết vào đáy. Đổi sang 0.18mm tạo rãnh đứt gãy, bóc viền brim cực nhẹ |
| **Quy trình tháo bàn** | **< 30–35°C** | Chờ bàn nguội hẳn, uốn nhẹ plate là chi tiết tự bung tiếng "tách" |

---

### 4. Dải tốc độ chuẩn PETG (Khóa cứng không đổi)
* Lớp đầu: `30 mm/s` (infill lớp đầu: `50 mm/s`).
* Vách ngoài: `100 mm/s`.
* Vách trong & Ruột: `120 mm/s`.
* Mặt trên cùng: `80 mm/s`.
* Điền khe: `100 mm/s`.
* Cầu (Bridge): `25 mm/s`.

---

### 5. Vị trí file cấu hình đã đồng bộ
1. **Process Profile:**
   * `C:\Users\Admin\AppData\Roaming\BambuStudio\user\3262261009\process\test suppport.json`
   * `C:\Users\Admin\AppData\Roaming\BambuStudio\user\3262261009\process\LP-Process-Cantilever-Box-PETG-SAFE.json`
   * `D:\16.Sharp3D\Congfig\02.Filament_PETG_Matte_Black&Grey\test suppport.json`
   * `D:\16.Sharp3D\Congfig\02.Filament_PETG_Matte_Black&Grey\LP-Process-Cantilever-Box-PETG-SAFE.json`
2. **Filament Profile:**
   * `LP-Tinimory-Petg-White.json` (Bàn 80°C, Đầu phun 240/248°C, Flow 0.96, MVS 10, Retract 0.5mm@30mm/s).
3. **AI Hub Brain:**
   * `d:\15.BambuStudio\ai_chat.py` (Đã nạp 4 trường hợp Support vào SYSTEM prompt cho Web + Slack).
   * `d:\15.BambuStudio\analyzer.py` (Đã đồng bộ dải tốc độ, MVS 10, Support XY 0.70mm).
   * `d:\15.BambuStudio\PETG-ECO-BAI-HOC.md` (Bài học #10 cập nhật chi tiết).
