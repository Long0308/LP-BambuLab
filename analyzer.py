#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Phan tich file in theo triet ly Hub — chay tren SERVER, tra JSON cho web.

Dong hoa nhung gi da lam thu cong cho makep.3mf:
  1. Hinh hoc     : kich thuoc, so tam giac, dien tich overhang >45deg (co can support?)
  2. Xoay thu     : quet goc xoay quanh X tim tu the it overhang nhat — VA canh bao
                    bay "bam ban = 0" (xoay 45deg bien day phang thanh doc, dung canh dao)
  3. Layer height : phat hien Variable Layer Height + tinh so lop THUC TE no gay ra
  4. Tran luu luong: v_max = max_volumetric_speed / (layer_height x line_width).
                    Toc do dat cao hon tran chi la so ao — may tu ham.
  5. Khuyen nghi  : sinh tu 4 muc tren, kem con so tiet kiem uoc tinh.
"""
from __future__ import annotations

import json
import math
import re
import zipfile

COS45 = math.cos(math.radians(45))
BED_EPS = 0.3          # mm — coi nhu dang nam tren ban


# ---------- hinh hoc ----------
def mesh_stats(tris: list) -> dict:
    """tris = [(v1,v2,v3), ...]. Tra kich thuoc + overhang + dien tich bam ban."""
    zs = [v[2] for t in tris for v in t]
    xs = [v[0] for t in tris for v in t]
    ys = [v[1] for t in tris for v in t]
    zmin = min(zs)
    tot = over = bed = 0.0
    for p, q, r in tris:
        ux, uy, uz = q[0]-p[0], q[1]-p[1], q[2]-p[2]
        vx, vy, vz = r[0]-p[0], r[1]-p[1], r[2]-p[2]
        nx, ny, nz = uy*vz-uz*vy, uz*vx-ux*vz, ux*vy-uy*vx
        L = math.sqrt(nx*nx + ny*ny + nz*nz)
        if not L:
            continue
        a = L / 2
        tot += a
        if nz / L < -COS45:
            if max(p[2], q[2], r[2]) - zmin <= BED_EPS:
                bed += a
            else:
                over += a
    return {
        "dims": [round(max(xs)-min(xs), 1), round(max(ys)-min(ys), 1), round(max(zs)-min(zs), 1)],
        "height": round(max(zs)-min(zs), 1),
        "triangles": len(tris),
        "area_cm2": round(tot / 100, 1),
        "overhang_cm2": round(over / 100, 1),
        "overhang_pct": round(over / tot * 100, 2) if tot else 0.0,
        "bed_cm2": round(bed / 100, 1),
        "need_support": (over / tot * 100 if tot else 0) > 1.0,
    }


def try_rotations(tris: list, angles=(-60, -45, -30, -15, 0, 15, 30, 45, 90, 180)) -> list:
    """Quet goc xoay quanh X. Ghi CA overhang lan dien tich bam ban.

    BAY: xoay 45deg co the bien day phang thanh mat doc 45deg -> thuat toan khong
    con dem la overhang (0.59%) nhung bam ban tut ve 0 -> dung tren canh dao, lop
    dau khong bam. Vi vay PHAI doc bed_cm2 cung luc, dung nhin moi overhang.
    """
    out = []
    for ax in angles:
        a = math.radians(ax)
        ca, sa = math.cos(a), math.sin(a)
        rot = [tuple((v[0], v[1]*ca - v[2]*sa, v[1]*sa + v[2]*ca) for v in t) for t in tris]
        s = mesh_stats(rot)
        out.append({"angle_x": ax, "overhang_pct": s["overhang_pct"],
                    "bed_cm2": s["bed_cm2"], "height": s["height"],
                    "usable": s["bed_cm2"] >= 5.0})       # <5cm2 bam ban = khong in duoc
    return out


# ---------- cau hinh trong .3mf ----------
def variable_layer(zf: zipfile.ZipFile, height: float, nominal: float) -> dict | None:
    """Doc layer_heights_profile.txt -> so lop THUC TE vs so lop neu phang."""
    names = [n for n in zf.namelist() if "layer_heights_profile" in n.lower()]
    if not names:
        return None
    raw = zf.read(names[0]).decode("utf-8", "ignore")
    body = raw.split("|", 1)[1] if "|" in raw else raw
    vals = [float(x) for x in body.split(";") if x.strip()]
    zsc, hs = vals[0::2], vals[1::2]
    if len(hs) < 2:
        return None
    n_var = 0.0
    for i in range(1, len(zsc)):
        dz = zsc[i] - zsc[i-1]
        h = (hs[i] + hs[i-1]) / 2
        if h > 0:
            n_var += dz / h
    flat = height / nominal if nominal else 0
    return {"min": round(min(hs), 3), "max": round(max(hs), 3),
            "avg": round(sum(hs)/len(hs), 3),
            "layers_actual": round(n_var), "layers_flat": round(flat),
            "extra_layers": round(n_var - flat),
            "extra_pct": round((n_var/flat - 1) * 100) if flat else 0}


COS15 = math.cos(math.radians(15))
SIN20 = math.sin(math.radians(20))


def face_analysis(tris: list) -> dict:
    """Do do BOXY vs ORGANIC + mat phang dung/tren -> co so quyet dinh seam/wall/ironing.

    1 pass O(n). Dung de suy luan, KHONG hard-code seam/wall nua:
      - flat_ratio : ti le dien tich huong theo 1 truc chinh (cao=CAD/hop, thap=cong/huu co)
      - vert_dom   : ti le mat DUNG lon nhat cung 1 huong -> co "mat phang de giau seam"
      - top_flat_pct: mat phang huong LEN o dinh -> ung vien ironing
    """
    zs = [v[2] for t in tris for v in t]
    zmin, zmax = min(zs), max(zs)
    h = zmax - zmin or 1.0
    tot = flat = top_flat = 0.0
    vbins = [0.0] * 8                       # dien tich mat dung theo 8 huong ngang
    for p, q, r in tris:
        ux, uy, uz = q[0]-p[0], q[1]-p[1], q[2]-p[2]
        vx, vy, vz = r[0]-p[0], r[1]-p[1], r[2]-p[2]
        nx, ny, nz = uy*vz-uz*vy, uz*vx-ux*vz, ux*vy-uy*vx
        L = math.sqrt(nx*nx + ny*ny + nz*nz)
        if not L:
            continue
        a = L / 2
        tot += a
        ex, ey, ez = nx/L, ny/L, nz/L
        if max(abs(ex), abs(ey), abs(ez)) >= COS15:      # huong theo 1 truc chinh
            flat += a
        if abs(ez) < SIN20:                              # mat gan DUNG
            b = int((math.atan2(ey, ex) + math.pi) / (2*math.pi) * 8) % 8
            vbins[b] += a
        if ez > COS15 and (max(p[2], q[2], r[2]) - zmin) > 0.85 * h:   # mat phang tren dinh
            top_flat += a
    return {
        "flat_ratio": round(flat / tot, 3) if tot else 0,
        "vert_dom": round(max(vbins) / tot, 3) if tot else 0,
        "top_flat_pct": round(top_flat / tot * 100, 2) if tot else 0,
        "top_flat_cm2": round(top_flat / 100, 1),
    }


def _nozzle_lw(cfg: dict) -> tuple[float, float]:
    """Lay duong kinh nozzle THAT tu cau hinh -> be rong duong in (~nozzle x 1.05)."""
    try:
        nz = float((cfg.get("nozzle_diameter") or [0.4])[0]) if isinstance(
            cfg.get("nozzle_diameter"), list) else float(cfg.get("nozzle_diameter") or 0.4)
    except (TypeError, ValueError):
        nz = 0.4
    return nz, round(nz * 1.05, 3)


def flow_ceiling(cfg: dict) -> dict | None:
    """v_max = max_volumetric_speed / (layer_height x line_width). Vuot = so ao.

    line_width suy tu duong kinh nozzle THAT (khong hard-code): nozzle x 1.05.
    """
    try:
        mvs = float((cfg.get("filament_max_volumetric_speed") or [None])[0])
        lh = float(cfg.get("layer_height"))
    except (TypeError, ValueError, IndexError):
        return None
    nz, lw = _nozzle_lw(cfg)
    vmax = mvs / (lh * lw)

    def spd(k):
        try:
            return float((cfg.get(k) or [None])[0])
        except (TypeError, ValueError, IndexError):
            return None
    over = {}
    for k, label in (("outer_wall_speed", "Thành ngoài"), ("inner_wall_speed", "Thành trong"),
                     ("sparse_infill_speed", "Ruột"), ("internal_solid_infill_speed", "Ruột đặc")):
        v = spd(k)
        if v and v > vmax:
            over[label] = round(v)
    return {"mvs": mvs, "nozzle": nz, "line_width": lw, "layer_height": lh,
            "v_max": round(vmax), "over_ceiling": over}


def top_shell_layers(lh: float, infill_pct: float, target_mm: float = 1.0) -> tuple[int, str]:
    """So lop mat tren = du de KHONG bi pillowing (vong wiki OrcaSlicer).

    Quy tac wiki: shell day it nhat ~target_mm; neu (layers x lh) mong hon thi TANG.
    Infill thap -> mat tren phai bac cau qua khe rong hon -> +1 lop.
    """
    n = max(3, math.ceil(target_mm / lh))
    reason = f"{n} lớp ≈ {n*lh:.2f}mm (đủ dày {target_mm}mm để không pillowing ở layer {lh}mm)"
    if infill_pct < 12:
        n += 1
        reason += f"; +1 vì infill chỉ {infill_pct:.0f}% (khe rộng, dễ võng mặt trên)"
    return n, reason


def analyze_3mf(path: str) -> dict:
    """Phan tich 1 file .3mf (du an hoac da slice)."""
    res: dict = {"kind": "3mf", "issues": [], "tips": []}
    with zipfile.ZipFile(path) as z:
        names = z.namelist()
        res["sliced"] = any(re.search(r"Metadata/plate_\d+\.gcode$", n, re.I) for n in names)
        cfg = {}
        for n in names:
            if n.lower().endswith("project_settings.config"):
                cfg = json.loads(z.read(n).decode("utf-8", "ignore"))
                break
        res["config"] = {k: cfg.get(k) for k in (
            "printer_model", "layer_height", "wall_loops", "wall_generator", "wall_sequence",
            "sparse_infill_density", "sparse_infill_pattern", "enable_support", "support_type",
            "seam_position", "seam_slope_type", "outer_wall_speed", "inner_wall_speed",
            "sparse_infill_speed", "top_shell_layers", "bottom_shell_layers")}

        # mesh
        obj = [n for n in names if n.lower().endswith(".model") and "objects" in n.lower()]
        if obj:
            xml = z.read(obj[0]).decode("utf-8", "ignore")
            V = [(float(a), float(b), float(c)) for a, b, c in re.findall(
                r'<vertex[^>]*x="([-\d.eE]+)"[^>]*y="([-\d.eE]+)"[^>]*z="([-\d.eE]+)"', xml)]
            T = [(int(a), int(b), int(c)) for a, b, c in re.findall(
                r'<triangle[^>]*v1="(\d+)"[^>]*v2="(\d+)"[^>]*v3="(\d+)"', xml)]
            if V and T:
                tris = [(V[i], V[j], V[k]) for i, j, k in T]
                res["mesh"] = mesh_stats(tris)
                res["faces"] = face_analysis(tris)
                if len(tris) <= 200_000:
                    res["rotations"] = try_rotations(tris)

        nominal = float(cfg.get("layer_height") or 0.2)
        h = res.get("mesh", {}).get("height") or 0
        res["variable_layer"] = variable_layer(z, h, nominal) if h else None
        res["flow"] = flow_ceiling(cfg)

    _advise(res)
    return res


def analyze_stl(path: str) -> dict:
    """Phan tich STL tho (chua co cau hinh -> chi hinh hoc + xoay)."""
    import stl_to_3mf
    tris = stl_to_3mf.parse_stl(path)
    res = {"kind": "stl", "sliced": False, "issues": [], "tips": [],
           "mesh": mesh_stats(tris), "faces": face_analysis(tris), "config": None,
           "variable_layer": None, "flow": None}
    if len(tris) <= 200_000:
        res["rotations"] = try_rotations(tris)
    _advise(res)
    return res


def _advise(r: dict) -> None:
    """Sinh canh bao + khuyen nghi tu so lieu (khong doan bua)."""
    m = r.get("mesh") or {}
    if m:
        if m["need_support"]:
            r["issues"].append(
                f"Cần support: {m['overhang_cm2']} cm² mặt hẫng >45° "
                f"({m['overhang_pct']}% tổng diện tích).")
        else:
            r["tips"].append("Không cần support — hầu như không có mặt hẫng quá 45°.")
        if m["bed_cm2"] < 5:
            r["issues"].append(
                f"Bám bàn chỉ {m['bed_cm2']} cm² — lớp đầu dễ bong. Cần brim/raft.")

    rots = r.get("rotations") or []
    if rots and m:
        cur = next((x for x in rots if x["angle_x"] == 0), None)
        good = [x for x in rots if x["usable"]]
        best = min(good, key=lambda x: x["overhang_pct"]) if good else None
        # Chi khuyen xoay khi VUA giam overhang VUA con bam ban du
        if best and cur and best["angle_x"] != 0 and best["overhang_pct"] < cur["overhang_pct"] - 2:
            r["tips"].append(
                f"Xoay {best['angle_x']}° quanh trục X: overhang {cur['overhang_pct']}% → "
                f"{best['overhang_pct']}% mà vẫn bám bàn {best['bed_cm2']} cm².")
        trap = [x for x in rots if not x["usable"] and cur and x["overhang_pct"] < cur["overhang_pct"]]
        if trap:
            t = trap[0]
            r["issues"].append(
                f"BẪY: xoay {t['angle_x']}° nhìn thì overhang chỉ {t['overhang_pct']}% "
                f"nhưng bám bàn = {t['bed_cm2']} cm² (đứng trên cạnh dao) — KHÔNG dùng được.")

    vl = r.get("variable_layer")
    if vl and vl["extra_layers"] > 20:
        r["issues"].append(
            f"Variable Layer Height đang bật (mỏng nhất {vl['min']}mm, TB {vl['avg']}mm) → "
            f"{vl['layers_actual']} lớp thay vì {vl['layers_flat']} lớp phẳng, "
            f"tức CỘNG THÊM {vl['extra_layers']} lớp (+{vl['extra_pct']}%).")
        r["tips"].append("Tắt Variable Layer Height nếu vật thể chủ yếu là thành đứng — tiết kiệm nhiều nhất.")

    fl = r.get("flow")
    if fl and fl["over_ceiling"]:
        lst = ", ".join(f"{k} {v}" for k, v in fl["over_ceiling"].items())
        r["issues"].append(
            f"Tốc độ vượt TRẦN LƯU LƯỢNG: nhựa chỉ chảy {fl['mvs']} mm³/s → ở layer "
            f"{fl['layer_height']}mm tốc độ tối đa thật là {fl['v_max']} mm/s, nhưng đang đặt "
            f"{lst} mm/s. Máy tự hãm — các số này chỉ là ảo.")
        r["tips"].append(f"Hạ tốc độ về ≤{fl['v_max']} mm/s cho đúng thực tế.")


MODES = {
    "fast":     {"label": "Nhanh",    "layer": 0.28, "infill": "8%",  "walls": 2, "outer": None},
    "balanced": {"label": "Cân bằng", "layer": 0.20, "infill": "10%", "walls": 2, "outer": 150},
    "quality":  {"label": "Đẹp",      "layer": 0.16, "infill": "12%", "walls": 3, "outer": 110},
}


def make_preset(r: dict, name: str = "OPT", mode: str = "balanced") -> dict:
    """Sinh preset process .json TU CHINH cac van de analyzer tim ra, THEO MUC TIEU.

    Khong bia so: moi gia tri deu bat nguon tu 1 phat hien cu the hoac tu mode.
    Layer height la don bay THOI GIAN lon nhat; toc do bi chan boi tran luu luong
    nen day toc do cao hon tran KHONG giup gi.
    """
    M = MODES.get(mode, MODES["balanced"])
    m = r.get("mesh") or {}
    fl = r.get("flow") or {}
    fa = r.get("faces") or {}
    lh = M["layer"]
    why = []

    # inherits khop theo layer height (base preset that cua A1), khong cung 1 gia tri
    base = {0.28: "0.28mm Extra Draft", 0.24: "0.24mm Draft", 0.20: "0.20mm Standard",
            0.16: "0.16mm Optimal", 0.12: "0.12mm Fine"}.get(lh, "0.20mm Standard")
    p = {
        "from": "User",
        "inherits": f"{base} @BBL A1",
        "name": f"A1 - {name} - {mode.upper()}",
        "print_settings_id": f"A1 - {name} - {mode.upper()}",
        "version": "2.7.0.8",
        "layer_height": str(lh),
        "wall_loops": str(M["walls"]),
        "sparse_infill_density": M["infill"],
        # wall_generator: arachne xu ly duong in bien thien do rong (thanh mong, goc nhon
        # cua model huu co). Classic chi hon khi 100% vuong vap — hiem, nen arachne mac dinh.
        "wall_generator": "arachne",
    }

    # 1) LAYER HEIGHT — don bay thoi gian manh nhat
    h = m.get("height") or 0
    if h:
        why.append(f"Layer {lh}mm ({M['label']}) → ~{int(h/lh)} lớp "
                   f"(0.20mm là {int(h/0.20)} lớp). Đây là đòn bẩy thời gian mạnh nhất.")

    # 2) TOC DO — tran luu luong PHU THUOC layer height, phai tinh lai
    mvs = fl.get("mvs")
    if mvs:
        vmax = int(mvs / (lh * 0.42))
        safe = int(vmax * 0.97)
        p["inner_wall_speed"] = [str(safe)]
        p["sparse_infill_speed"] = [str(safe)]
        p["internal_solid_infill_speed"] = [str(safe)]
        outer = M["outer"] or min(safe, 180)
        p["outer_wall_speed"] = [str(outer)]
        p["top_surface_speed"] = [str(min(outer, 150))]
        why.append(f"Tốc độ ≤{safe} mm/s: ở layer {lh}mm, nhựa {mvs} mm³/s chỉ cho tối đa "
                   f"{vmax} mm/s. Đặt cao hơn là số ảo — máy tự hãm."
                   + (f" Thành ngoài {outer} để mặt mịn." if M["outer"] else
                      " Thành ngoài cũng chạy hết tốc (ưu tiên nhanh)."))

    # 3) SUPPORT — tu nhan dinh theo dien tich hang THAT, khong theo cam tinh
    ov = m.get("overhang_pct", 0)
    ov_cm2 = m.get("overhang_cm2", 0)
    if ov_cm2 < 2.0 or ov < 0.5:
        p["enable_support"] = "0"
        why.append(f"TẮT support: chỉ {ov_cm2} cm² mặt hẫng >45° ({ov}%) — quá nhỏ, "
                   f"máy bắc cầu (bridging) qua được. Tiết kiệm thời gian + nhựa + khỏi gọt.")
    else:
        p["enable_support"] = "1"
        p["support_type"] = "tree(auto)"
        p["support_style"] = "tree_hybrid"
        p["support_on_build_plate_only"] = "1"
        p["support_threshold_angle"] = "40"
        why.append(f"BẬT support cây: {ov_cm2} cm² mặt hẫng >45° ({ov}%) — không có thì võng/hỏng. "
                   f"Chỉ chống từ mặt bàn (không tì lên thân → khỏi rỗ mặt). "
                   f"Support TỐN thêm thời gian — đó là giá của bản in không lỗi.")

    # 4) BRIM — quyet dinh bang NGUY CO LAT, khong phai bang cam giac
    #    Nguy co lat ~ chieu cao / canh vuong tuong duong cua mat day.
    #    Day rong + thap  -> KHONG can brim (brim ton thoi gian + phai got via).
    #    Day hep + cao    -> BAT BUOC brim, nguoc lai in giua chung se do.
    bed = m.get("bed_cm2", 0)
    h_mm = m.get("height", 0)
    side = math.sqrt(bed * 100) if bed > 0 else 0.01      # cm2 -> mm2 -> canh vuong td
    ratio = h_mm / side if side else 99
    if bed >= 20 and ratio <= 3:
        p["brim_type"] = "no_brim"
        p["brim_width"] = "0"
        why.append(f"KHÔNG brim: đáy rộng {bed} cm² (cạnh ~{side:.0f}mm) so với cao {h_mm}mm "
                   f"→ tỉ lệ lật {ratio:.1f} (an toàn <3). Đáy dày/rộng thế này brim chỉ tốn "
                   f"thời gian và phải gọt via.")
    elif bed >= 8:
        p["brim_type"] = "outer_only"
        p["brim_width"] = "5"
        why.append(f"Brim 5mm: đáy {bed} cm², tỉ lệ lật {ratio:.1f} — bám thêm cho chắc.")
    else:
        p["brim_type"] = "outer_only"
        p["brim_width"] = "8"
        why.append(f"Brim 8mm (BẮT BUỘC): đáy chỉ {bed} cm², tỉ lệ lật {ratio:.1f} — "
                   f"không brim thì lớp đầu bong / model đổ giữa chừng.")

    # 5) TOP/BOTTOM SHELL — tinh theo quy tac do day (wiki OrcaSlicer), khong cung "4/3"
    infill_pct = float(re.sub(r"[^\d.]", "", M["infill"]) or 10)
    tsl, tsl_why = top_shell_layers(lh, infill_pct, 1.0)
    bsl = max(3, math.ceil(0.8 / lh))
    p["top_shell_layers"] = str(tsl)
    p["bottom_shell_layers"] = str(bsl)
    p["top_shell_thickness"] = "1"          # chot chan: slicer tu tang lop neu mong hon
    p["top_surface_pattern"] = "monotonicline"   # wiki: monotonic line dep nhat cho mat tren
    why.append(f"Mặt trên {tsl} lớp / đáy {bsl} lớp: {tsl_why}.")

    # 6) SEAM — suy tu HINH HOC (boxy hay cong), theo wiki. Khong cung "aligned".
    flat_ratio = fa.get("flat_ratio", 0)
    vert_dom = fa.get("vert_dom", 0)
    if flat_ratio >= 0.55 and vert_dom >= 0.12:
        # Hop/CAD co mat phang dung ro -> seam nem vao goc/canh (aligned), scarf tat
        # (wiki: scarf kem hieu qua o goc nhon, con lam mo canh).
        p["seam_position"] = "aligned"
        p["seam_slope_type"] = "none"
        why.append(f"Seam = Aligned, KHÔNG scarf: model dạng hộp (mặt phẳng {int(flat_ratio*100)}%, "
                   f"có mặt đứng lớn) → dồn seam vào cạnh/góc là giấu tốt nhất; scarf làm mờ cạnh nhọn.")
    else:
        # Cong/huu co -> khong co goc de giau -> scarf ramp (wiki: giau z-seam mat cong)
        p["seam_position"] = "aligned"
        p["seam_slope_type"] = "all"
        why.append(f"Seam = Aligned + SCARF (ramp): model cong/hữu cơ (mặt phẳng chỉ "
                   f"{int(flat_ratio*100)}%) không có góc giấu seam → scarf tán mối nối "
                   f"trên mặt cong (theo wiki OrcaSlicer). Muốn giấu hẳn 1 mặt: dùng Seam painting.")

    # 7) WALL ORDER — suy tu overhang, theo wiki (khong cung "inner/outer")
    ov = m.get("overhang_pct", 0)
    if ov >= 3.0:
        p["wall_sequence"] = "inner wall/outer wall"
        why.append(f"Thứ tự thành = Inner/Outer: overhang {ov}% đáng kể → thành ngoài cần thành "
                   f"trong đỡ lưng (bớt võng), và wiki nói inner/outer cho seam đẹp hơn.")
    elif flat_ratio >= 0.6 and ov < 1.0:
        p["wall_sequence"] = "outer wall/inner wall"
        why.append(f"Thứ tự thành = Outer/Inner: model dạng hộp chức năng (mặt phẳng {int(flat_ratio*100)}%, "
                   f"gần như không overhang) → in thành ngoài trước cho lỗ/chốt CHÍNH XÁC kích thước. "
                   f"Đổi lại seam hơi rõ hơn.")
    else:
        p["wall_sequence"] = "inner wall/outer wall"
        why.append("Thứ tự thành = Inner/Outer (mặc định wiki): thành ngoài in sau, tựa vào thành "
                   "trong → bề mặt mịn + seam gọn.")

    # 8) INFILL pattern — theo muc tieu
    if mode == "quality":
        p["sparse_infill_pattern"] = "gyroid"    # deu huong, chac, dep khi lo ra
        why.append("Ruột Gyroid (chế độ Đẹp): đều mọi hướng, chắc, nhìn đẹp nếu lộ.")
    else:
        p["sparse_infill_pattern"] = "adaptivecubic"
        why.append(f"Ruột Adaptive Cubic {M['infill']}: dày ở gần vỏ, thưa ở giữa → nhanh + ít nhựa.")

    # 9) IRONING — chi khi co mat phang tren LON va uu tien dep
    top_flat = fa.get("top_flat_pct", 0)
    if mode == "quality" and top_flat >= 8:
        p["ironing_type"] = "top"
        why.append(f"Bật ủi (ironing) mặt trên: có {fa.get('top_flat_cm2')} cm² mặt phẳng hướng lên "
                   f"({top_flat}%) → ủi cho phẳng bóng. Tốn thêm ít thời gian, chỉ bật ở chế độ Đẹp.")
    else:
        p["ironing_type"] = "no ironing"

    # 10) INFILL/WALL OVERLAP — wiki: 25% chong ho chan long giua ruot va vo
    p["infill_wall_overlap"] = "25%"
    p["seam_gap"] = "10%"                        # wiki: 0-15% khi PA tune tot

    vl = r.get("variable_layer")
    if vl and vl["extra_layers"] > 20:
        why.append(f"Gỡ Variable Layer Height: nó đang âm thầm cộng {vl['extra_layers']} lớp "
                   f"(+{vl['extra_pct']}%). Server tự gỡ khi slice — không nhét được vào preset "
                   f"vì nó gắn theo vật thể trong .3mf.")

    return {"preset": p, "why": why, "mode": mode, "mode_label": M["label"]}


def analyze(path: str, mode: str = "balanced") -> dict:
    r = analyze_stl(path) if path.lower().endswith(".stl") else analyze_3mf(path)
    import os as _os
    nm = _os.path.splitext(_os.path.basename(path))[0][:20]
    r["export"] = make_preset(r, nm, mode)
    r["presets"] = {k: make_preset(r, nm, k) for k in MODES}
    return r


if __name__ == "__main__":
    import sys
    print(json.dumps(analyze(sys.argv[1]), ensure_ascii=False, indent=2))
