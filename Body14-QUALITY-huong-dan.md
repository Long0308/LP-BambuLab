# Body 14 — In đẹp hơn (hết lộ vân + đều viền)

Model Body 14 là dạng **hữu cơ, toàn mặt cong** → chất lượng bề mặt do **layer height + WALL** quyết định, KHÔNG phải "mặt trên". Chỉnh `top_surface_*` gần như vô ích ở model này.

## 1. Import preset (đã lo sẵn — import là chạy)
File `Body14-PLAMatte-Decor-QUALITY-0.16-process.json`. So với bản `FAST 0.24` đã in:

| Thông số | FAST 0.24 (bị lỗi) | QUALITY 0.16 (mới) | Vì sao |
|---|---|---|---|
| `layer_height` | 0.24 | **0.16** | Bậc thang trên mặt cong giảm ~1/3 → hết "lộ vân" |
| `wall_loops` | 2 | **3** | Thành dày hơn, che sai số, viền đều |
| `wall_sequence` | outer/inner | **inner/outer** | In trong trước → thành ngoài có điểm tựa, mép overhang bớt võng |
| `outer_wall_speed` | ~kế thừa (nhanh) | **120** | Thành lộ ra chạy chậm → mịn, ít gợn |
| `inner_wall_speed` | 240 | **180** | Bớt rung/ringing |
| `seam_position` | back | **aligned** | Đường nối xếp thẳng 1 cột, dễ giấu hơn trên model tròn |
| `top_surface_speed` | 150 | **120** | — |
| `infill_wall_overlap` | 10% | **15%** | Vỏ dính ruột chắc hơn |

Giữ nguyên điểm tốt sẵn có: `wall_generator: arachne`, scarf seam (`seam_slope_type: all`).
Muốn **mịn tối đa** cho đồ trang trí: đổi `layer_height` → `0.12` và `inherits` → `"0.12mm Fine @BBL A1"` (chậm hơn nhưng đẹp nhất).

## 2. Ba việc phải làm TRONG UI (không nhét vào preset được)

**a) Variable Layer Height — quan trọng nhất cho model cong**
Sau khi load model: thanh trái → biểu tượng **"Variable layer height"** → **Adaptive**.
Nó tự để lớp dày ở thành đứng (nhanh) và tự hạ mỏng (0.08–0.12) ở mặt cong thoải (mịn).
→ Diệt "vân" mà thời gian **không** gấp đôi. Đây là thứ sinh ra đúng cho kiểu model này.
(Không lưu được vào preset vì nó gắn theo từng vật thể, nằm trong file .3mf.)

**b) Hiệu chỉnh máy A1 (viền không đều = extrusion không đều)**
Device → **Calibration** → chạy **Flow Dynamics (Pressure Advance)** rồi **Flow Rate**.
240 mm/s mà PA chưa tune là ra thành gợn/mép lệch ngay. Làm 1 lần, dùng mãi.

**c) Slow down for overhangs**
Quality → **"Slow down for overhangs"** → BẬT, để mép các lỗ tròn (overhang) không bị võng.
(Để trong UI thay vì preset vì tên key overhang khác nhau giữa các bản Studio — bật tay chắc ăn.)

## 3. Đánh đổi thời gian
- 0.24 → 0.16: thời gian tăng ~1.4–1.5×, bề mặt đẹp rõ rệt.
- Dùng **Adaptive layer height** thay vì hạ đều: chỉ phần cong mới chậm → tăng ít hơn nhiều.
- Đây là đồ **trang trí** nên ưu tiên bề mặt; không cần hạ xuống 0.08 (quá lâu, lợi ích ít).
