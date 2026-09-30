# SESSION NOTE — 2026-09-29 — Antigravity — LP-BambuLab

- **Project:** LP-BambuLab (`d:\15.BambuStudio`)
- **IDE:** Antigravity IDE
- **Model:** Gemini 3.8 Flash
- **Conversation IDs liên quan trong ngày:**
  - Sáng (05:28 - 07:33): `ba344dc5-5a50-4573-a732-145c4373db26` (Tạo `test suppport.json`, in thành công 100%, ghi nhận Bài học #10)
  - Tối (18:56 - 22:20): `525ba5b0-5880-4130-9cf0-da087d0872bc` (Phân tích lớp đáy bị cứng, debug lỗi bung bàn do hạ 70C, chốt 4 trường hợp support, nạp AI Web/Slack, tạo Handover)

---

## 1. Tóm tắt cốt lõi phiên làm việc (Ground Truth)

### A. Sự cố & Nguyên nhân trong ngày:
1. **Sáng 29/09:** 
   - Chi tiết: Khớp nối hộp Cantilever in bằng cuộn `LP-Tinimory-Petg-White`.
   - Cấu hình chạy: `test suppport.json` với **Thân PETG + Support Interface là PLA (KHÁC LOẠI)**.
   - Thông số support: `Top Z = 0.36 mm`, `Interface spacing = 0.3 mm`, `Tree Slim`.
   - Kết quả: Support bóc sạch bóng, rơi tự do không tốn lực vì khoảng hở 0.36mm cộng với đặc tính không dính phân tử giữa PLA và PETG.
   - Vấn đề tồn đọng: Lớp đáy tiếp xúc mặt bàn Textured PEI gỡ ra vẫn còn cứng do `brim_object_gap = 0.10 mm` bị hàn dính liền vào đáy hộp.

2. **Tối 29/09 (Sự cố thử nghiệm thất bại):**
   - AI đề xuất hạ bàn xuống 70°C và nâng lớp đầu lên 0.24mm nhằm dễ gỡ đáy $\rightarrow$ **HẬU QUẢ: BUNG BÀN, KHÔNG BÁM LỚP 1 NGAY KHI VỪA IN**.
   - Thêm vào đó, file `test suppport.json` ở AppData bị thiếu dòng `support_type: tree(auto)` làm Bambu Studio tự lùi về Normal Grid Support ôm sát rạt vào vật thể.
   - **BÀI HỌC RÚT RA:** PETG Tinmorry trên bàn Textured PEI của máy A1 **BẮT BUỘC BÀN 80°C + LỚP ĐẦU 0.20MM** mới đủ độ dính nhiệt cơ sở. Muốn đáy dễ gỡ: giữ nguyên 80°C và 0.20mm, chỉ nới `brim_object_gap = 0.18 mm` và `line width = 0.42 mm`.

---

## 2. Bảng 4 Quy Chuẩn Support (Đã nạp vĩnh viễn vào AI Agent Web & Slack)

1. **Khác loại (Thân PETG + Support PLA — Case sáng 29/09):**
   - `support_interface_filament`: khay PLA.
   - `support_top_z_distance`: `0.36 mm` (như sáng nay bóc rơi tự do) hoặc `0.0 mm` (nếu muốn phẳng gương).
   - `support_interface_spacing`: `0.0 – 0.3 mm`. Bóc rơi cái một vì 2 chất không dính nhau.
2. **Khác loại (Thân PLA + Support PETG):**
   - Tương tự mục 1, PETG làm đệm cho thân PLA. `Top Z = 0.0 mm`, bàn theo PLA (55–65°C).
3. **Cùng loại PLA:**
   - `Top Z`: 0.15–0.20mm (mặt đẹp) hoặc 0.25mm (dễ gỡ). PLA giòn, bẻ gãy nhẹ.
4. **Cùng loại PETG (Thân PETG + Support PETG — Nguy cơ dính chết cao nhất):**
   - `support_type`: `tree(auto)` + `tree_slim`.
   - `support_top_z_distance`: **`0.36 mm`** (~2 layer gap chống hàn dính).
   - `support_interface_spacing`: **`0.30 mm`** (lưới thưa, tuyệt đối KHÔNG để 0.0mm).
   - `support_object_xy_distance`: **`0.70 mm`** (cách xa vách hộp).
   - `overhang_fan_speed`: **`80% – 100%`**, `bridge_flow`: **`0.95`**.

---

## 3. Các file đã kiểm tra và đồng bộ:
- `d:\15.BambuStudio\HANDOVER-2026-09-29-petg-support.md` (Tạo mới)
- `d:\15.BambuStudio\HANDOVER.md` (Cập nhật trỏ tới file mới)
- `d:\15.BambuStudio\PETG-ECO-BAI-HOC.md` (Cập nhật Bài học #10)
- `d:\15.BambuStudio\ai_chat.py` (Cập nhật 4 case support vào SYSTEM prompt)
- `d:\15.BambuStudio\analyzer.py` (Khóa bàn 80C, MVS 10, support XY 0.70mm)
- `C:\Users\Admin\AppData\Roaming\BambuStudio\user\3262261009\process\test suppport.json` (Đồng bộ)
- `D:\16.Sharp3D\Congfig\02.Filament_PETG_Matte_Black&Grey\test suppport.json` (Đồng bộ)
