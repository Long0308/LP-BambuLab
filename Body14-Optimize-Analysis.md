# Body 14 - LP — Phân tích tối ưu thời gian in (đo thật bằng slicer CLI)

> Máy: **Bambu Lab A1** · nozzle 0.4 · nhựa **Bambu PLA Matte** (`GFA18`, textured plate 60°C)
> File nguồn: `C:\Users\Admin\Downloads\Body 14 - LP.3mf` · vật thể 182.8 × 151.8 × 150.0 mm
> Slicer đo: **Bambu Studio 2.7 CLI** (xem mục "Vì sao không dùng OrcaSlicer CLI")

## 1. Phát hiện then chốt

Bản hiện tại **KHÔNG phẳng 0.2mm** như tưởng. Nó đang bật **Variable Layer Height thiên MỊN**:
- 1155 lớp cho vật cao 150mm ⇒ **trung bình 0.13 mm/lớp** (profile chạy 0.08 → 0.28mm, tập trung ở 0.08–0.12).
- Đây là lý do chính khiến bản in lâu — **"over-quality"** cho một hộp đựng matte.

Bằng chứng: `Metadata/layer_heights_profile.txt` chứa 2253 giá trị height biến thiên; xoá profile này ⇒ quay về phẳng 0.2 ⇒ 750 lớp.

## 2. Kết quả đo thật (Bambu Studio CLI)

| Phương án | Thời gian | Δ so hiện tại | Số lớp | Nhựa (g) | Ghi chú chất lượng |
|---|---|---|---|---|---|
| **Hiện tại — VLH mịn (avg 0.13mm)** | **14h41m** | — | 1155 | 504.5 | Vòm cực mịn, hơi thừa |
| Phẳng 0.20mm (bỏ VLH) | **10h44m** | **−27% (−3h57)** | 750 | 488.9 | Vòm hơi bậc hơn, tường 0.2 chuẩn |
| Phẳng 0.24mm (bỏ VLH) | **9h52m** | **−33% (−4h49)** | 625 | 491.4 | Bậc thang rõ hơn ở vòm |
| **Combo** 0.24 + infill 8% + top 4 + bỏ support | **9h22m** | **−36% (−5h19)** | 625 | 459.5 | Nhanh & nhẹ nhất (−45g ≈ −9%) |

> Con số là **ước lượng Bambu Studio**. OrcaSlicer ước lượng baseline = **16h51m** (engine khác nhau).
> Lấy **% tiết kiệm** làm thước đo chuyển đổi: trên OrcaSlicer, phẳng 0.2 ≈ **~12h20m**, combo ≈ **~10h45m**.

### Breakdown thời gian baseline (từ `result.json → feature_type_times`)
| Feature | Thời gian | % |
|---|---|---|
| Inner + Outer wall | 5h51m | 40% |
| Sparse infill | 4h28m | 30% |
| Travel + Undefined | 4h29m | 30% |
| Solid infill | 1h20m | 9% |

Tường + infill = 70% và **tỉ lệ thuận số lớp** ⇒ giảm số lớp (VLH thô hơn / layer dày hơn) là đòn mạnh nhất.

## 3. Trần lưu lượng (flow ceiling) — vì sao đừng chỉnh tốc độ

`max_volumetric_speed` của PLA Matte = **16 mm³/s**. Ở layer 0.20 × line 0.42:
```
v_max = 16 / (0.20 × 0.42) ≈ 190 mm/s
```
⇒ inner_wall 240 & solid_infill 255 **không bao giờ đạt** (bị chặn ~190 mm/s). Chỉnh tốc độ cao hơn **vô ích**.
Nguồn: [Bambu Lab Wiki - Volumetric speed](https://wiki.bambulab.com/en/knowledge-sharing/volumetric-speed), [r/BambuLab](https://www.reddit.com/r/BambuLab/comments/zsnouk/volumetric_flow_limit_vs_speed_on_default_profle/).

## 4. Khuyến nghị (xếp theo giữ-chất-lượng)

1. **Tốt nhất (làm trong OrcaSlicer GUI):** giữ Variable Layer Height nhưng **kéo về phía "faster/coarser"** rồi Smooth — mịn ở **vòm**, dày ở **tường phẳng**. Giữ vẻ đẹp vòm mà vẫn cắt lớp tường. Ước tính rơi giữa 10h44 và 14h41. *(Không làm được qua CLI vì adaptive do GUI tính.)*
2. **Nhanh gọn, chất lượng vẫn tốt:** phẳng **0.20mm** ⇒ 10h44 (−27%). Vòm hơi bậc nhưng chấp nhận được với đồ matte.
3. **Nhẹ vật liệu:** infill 10% → 8% + **bỏ support thừa** (kiểm tra: vòm lõm thường tự đỡ) ⇒ −45g.
4. **Ép nhanh tối đa:** combo 0.24 ⇒ 9h22 (−36%), chấp nhận bậc thang rõ hơn.
5. **Giữ nguyên (đã tối ưu):** infill adaptive cubic · accel 5000/6000 · outer_wall 200 · arachne · 2 wall loops.

## 5. Vì sao không dùng OrcaSlicer CLI

`orca-slicer.exe --slice` **crash** (`0xC0000005` access violation) khi headless — bug init OpenGL ở chế độ CLI của OrcaSlicer 2.4.2. Đã thử `--datadir`, đổi plate index, đảo thứ tự tham số → vẫn crash.
**Giải pháp:** dùng **Bambu Studio 2.7 CLI** (`bambu-studio.exe --slice 0 --outputdir <dir> <file.3mf>`) — chạy ổn định, xuất `plate_1.gcode` + `result.json` (chứa `total_predication` giây, `feature_type_times`, `filaments[].main_used_g`).

**Lưu ý flaky:** Bambu Studio CLI crash **có quy luật** khi 3mf **vẫn giữ profile VLH mà sửa infill/support**. Variant **bỏ profile (phẳng)** hoặc **không sửa** thì ổn định. Script `reslice-benchmark.ps1` có sẵn vòng retry.

## 6. Tái lập
```powershell
# Đo 1 file .3mf bất kỳ:
powershell -File reslice-benchmark.ps1 -Input "C:\...\Body 14 - LP.3mf"
```
Xem `reslice-benchmark.ps1` trong cùng thư mục.
