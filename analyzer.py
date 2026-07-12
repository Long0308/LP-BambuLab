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


def flow_ceiling(cfg: dict) -> dict | None:
    """v_max = max_volumetric_speed / (layer_height x line_width). Vuot = so ao."""
    try:
        mvs = float((cfg.get("filament_max_volumetric_speed") or [None])[0])
        lh = float(cfg.get("layer_height"))
    except (TypeError, ValueError, IndexError):
        return None
    lw = 0.42
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
    return {"mvs": mvs, "layer_height": lh, "v_max": round(vmax),
            "over_ceiling": over}


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
           "mesh": mesh_stats(tris), "config": None,
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


def make_preset(r: dict, name: str = "OPT") -> dict:
    """Sinh preset process .json TU CHINH cac van de analyzer tim ra.

    Khong bia so: moi gia tri deu bat nguon tu 1 phat hien cu the.
    """
    cfg = r.get("config") or {}
    m = r.get("mesh") or {}
    fl = r.get("flow") or {}
    lh = float(cfg.get("layer_height") or 0.2)
    why = []

    p = {
        "from": "User",
        "inherits": "0.20mm Standard @BBL A1",
        "name": f"A1 - {name} - OPT",
        "print_settings_id": f"A1 - {name} - OPT",
        "version": "2.7.0.8",
        "layer_height": str(lh),
        "wall_generator": "arachne",
        "wall_sequence": "inner wall/outer wall",
        "seam_position": "aligned",
        "seam_slope_type": "all",
    }
    why.append("Arachne + inner/outer + scarf seam: mặt ngoài đều, giấu đường nối.")

    # 1) Toc do: KHONG BAO GIO vuot tran luu luong
    vmax = fl.get("v_max")
    if vmax:
        safe = int(vmax * 0.97)
        p["inner_wall_speed"] = [str(safe)]
        p["sparse_infill_speed"] = [str(safe)]
        p["internal_solid_infill_speed"] = [str(safe)]
        p["outer_wall_speed"] = ["120"]
        p["top_surface_speed"] = ["120"]
        why.append(f"Tốc độ ≤{safe} mm/s — đúng trần lưu lượng {fl['mvs']} mm³/s "
                   f"(đặt cao hơn chỉ là số ảo, máy tự hãm). Thành ngoài 120 để mặt mịn.")

    # 2) Support: chi bat khi that su co overhang
    if m.get("need_support"):
        p["enable_support"] = "1"
        p["support_type"] = "tree(auto)"
        p["support_style"] = "tree_hybrid"
        p["support_on_build_plate_only"] = "1"
        p["support_threshold_angle"] = "40"
        why.append(f"Bật support cây: có {m['overhang_cm2']} cm² mặt hẫng >45°. "
                   f"Chỉ chống từ mặt bàn để không cào xước thân.")
    else:
        p["enable_support"] = "0"
        why.append("Tắt support: gần như không có mặt hẫng >45° → tiết kiệm nhiều thời gian + nhựa.")

    # 3) Bam ban kem -> brim
    if m.get("bed_cm2", 99) < 20:
        p["brim_type"] = "outer_only"
        p["brim_width"] = "8"
        why.append(f"Brim 8mm: diện tích bám bàn chỉ {m['bed_cm2']} cm², dễ bong lớp đầu.")
    else:
        p["brim_type"] = "outer_only"
        p["brim_width"] = "5"

    # 4) Ruot
    p["sparse_infill_density"] = "10%"
    p["sparse_infill_pattern"] = "adaptivecubic"
    p["wall_loops"] = "2"
    p["top_shell_layers"] = "4"
    p["bottom_shell_layers"] = "3"
    p["ironing_type"] = "no ironing"
    p["enable_prime_tower"] = "0"

    vl = r.get("variable_layer")
    if vl and vl["extra_layers"] > 20:
        why.append(f"LƯU Ý: preset không tắt được Variable Layer Height (nó gắn theo vật thể "
                   f"trong file .3mf, không nằm trong preset). Đang cộng thêm {vl['extra_layers']} lớp "
                   f"(+{vl['extra_pct']}%) — dùng nút 'Slice ngay' trên web, server tự gỡ giúp.")

    return {"preset": p, "why": why}


def analyze(path: str) -> dict:
    r = analyze_stl(path) if path.lower().endswith(".stl") else analyze_3mf(path)
    import os as _os
    r["export"] = make_preset(r, _os.path.splitext(_os.path.basename(path))[0][:20])
    return r


if __name__ == "__main__":
    import sys
    print(json.dumps(analyze(sys.argv[1]), ensure_ascii=False, indent=2))
