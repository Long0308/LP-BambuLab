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
MIN_BED_CM2 = 5.0      # duoi nguong nay lop dau kho bam (canh vuong <22mm)
VLH_WARN_LAYERS = 20   # variable layer height cong them qua nguong nay moi dang canh bao
ROT_MAX_TRIS = 200_000  # tren nguong nay bo quet xoay (10 vong O(n) thuan Python ~>60s)


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
    # Tien tinh 1 lan: dien tich + normal + (y,z) 3 dinh. Moi goc chi xoay normal
    # va toa do z (phep quay quanh X khong dung x) -> nhanh ~3x so voi dung lai mesh.
    pre = []
    for p, q, r in tris:
        ux, uy, uz = q[0]-p[0], q[1]-p[1], q[2]-p[2]
        vx, vy, vz = r[0]-p[0], r[1]-p[1], r[2]-p[2]
        nx, ny, nz = uy*vz-uz*vy, uz*vx-ux*vz, ux*vy-uy*vx
        L = math.sqrt(nx*nx + ny*ny + nz*nz)
        if not L:
            continue
        pre.append((L/2, ny/L, nz/L,
                    p[1], p[2], q[1], q[2], r[1], r[2]))
    tot = sum(x[0] for x in pre)
    out = []
    for ax in angles:
        a = math.radians(ax)
        ca, sa = math.cos(a), math.sin(a)
        zmin = zmax = None
        rows = []
        for ar, ny, nz, py, pz, qy, qz, ry, rz in pre:
            nz2 = ny*sa + nz*ca
            ztop = max(py*sa + pz*ca, qy*sa + qz*ca, ry*sa + rz*ca)
            zlo = min(py*sa + pz*ca, qy*sa + qz*ca, ry*sa + rz*ca)
            if zmin is None or zlo < zmin:
                zmin = zlo
            if zmax is None or ztop > zmax:
                zmax = ztop
            rows.append((ar, nz2, ztop))
        over = bed = 0.0
        for ar, nz2, ztop in rows:
            if nz2 < -COS45:
                if ztop - zmin <= BED_EPS:
                    bed += ar
                else:
                    over += ar
        out.append({"angle_x": ax,
                    "overhang_pct": round(over / tot * 100, 2) if tot else 0.0,
                    "bed_cm2": round(bed / 100, 1),
                    "height": round((zmax or 0) - (zmin or 0), 1),
                    "usable": bed / 100 >= MIN_BED_CM2})
    return out


# ---------- cau hinh trong .3mf ----------
def variable_layer(zf: zipfile.ZipFile, height: float, nominal: float) -> dict | None:
    """Doc layer_heights_profile.txt -> so lop THUC TE vs so lop neu phang."""
    names = [n for n in zf.namelist() if "layer_heights_profile" in n.lower()]
    if not names:
        return None
    try:
        raw = zf.read(names[0]).decode("utf-8", "ignore")
        body = raw.split("|", 1)[1] if "|" in raw else raw
        vals = [float(x) for x in body.split(";") if x.strip()]
    except (ValueError, KeyError, OSError):
        return None                          # file hong -> coi nhu khong co VLH
    zsc, hs = vals[0::2], vals[1::2]
    n = min(len(zsc), len(hs))               # so phan tu le -> cat cho khop
    zsc, hs = zsc[:n], hs[:n]
    if len(hs) < 2:
        return None
    n_var = 0.0
    for i in range(1, n):
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
    # Do dac cho quyet dinh seam (wiki Bambu):
    #   n_dirs        : so HUONG mat dung dang ke (bin >= 10% tong mat dung).
    #                   Hop = 2-4, tru TRON = 7-8 (rai deu -> khong co goc sac).
    #   vert_dom_ratio: mat dung lon nhat gap may lan trung binh cac mat khac.
    #                   >= ~2 nghia la co 1 "mat lung" ro rang de hy sinh (kieu mat na).
    vsum = sum(vbins)
    nz = [b for b in vbins if b > 0]
    n_dirs = sum(1 for b in vbins if vsum and b >= 0.10 * vsum)
    return {
        "flat_ratio": round(flat / tot, 3) if tot else 0,
        "vert_dom": round(max(vbins) / tot, 3) if tot else 0,
        "n_dirs": n_dirs,
        "vert_dom_ratio": round(max(vbins) / (vsum / len(nz)), 2) if nz and vsum else 1.0,
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
    if lh <= 0 or lw <= 0 or mvs <= 0:      # config hong -> bo qua, dung chia 0
        return None
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
            "sparse_infill_speed", "top_shell_layers", "bottom_shell_layers",
            "filament_type")}   # filament_type: de tu phat hien cap PLA/PETG cho interface

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
                if len(tris) <= ROT_MAX_TRIS:
                    res["rotations"] = try_rotations(tris)
                else:
                    res["tips"].append(f"Mesh {len(tris):,} tam giác vượt ngưỡng {ROT_MAX_TRIS:,} — bỏ quét xoay để không treo server.")

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
    if not tris:
        return {"kind": "stl", "sliced": False, "config": None, "mesh": None,
                "faces": None, "variable_layer": None, "flow": None,
                "issues": ["File STL rỗng hoặc hỏng — không đọc được tam giác nào."],
                "tips": []}
    res = {"kind": "stl", "sliced": False, "issues": [], "tips": [],
           "mesh": mesh_stats(tris), "faces": face_analysis(tris), "config": None,
           "variable_layer": None, "flow": None}
    if len(tris) <= ROT_MAX_TRIS:
        res["rotations"] = try_rotations(tris)
    else:
        res["tips"].append(f"Mesh {len(tris):,} tam giác vượt ngưỡng {ROT_MAX_TRIS:,} — bỏ quét xoay để không treo server.")
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
        if m["bed_cm2"] < MIN_BED_CM2:
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
    if vl and vl["extra_layers"] > VLH_WARN_LAYERS:
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
    "balanced": {"label": "Cân bằng", "layer": 0.20, "infill": "10%", "walls": 3, "outer": 150},
    "quality":  {"label": "Đẹp",      "layer": 0.16, "infill": "12%", "walls": 3, "outer": 110},
}

# Tag tieng Anh cho ten preset co cau truc: LP-BamBu-A1-<Tag>-<layer>mm-<model>
QUALITY_TAG = {"fast": "Fast", "balanced": "Balanced", "quality": "HighQuality"}


def preset_name(mode: str, lh: float, model: str = "") -> str:
    """Ten preset chuan: LP-BamBu-A1-HighQuality-0.2mm-<model>.

    Prefix co dinh de user loc trong Bambu Studio; hau to model de preset cua
    2 file khac nhau KHONG ghi de nhau (support/brim suy theo tung model).
    """
    tag = QUALITY_TAG.get(mode, mode.capitalize())
    slug = re.sub(r"[^A-Za-z0-9_-]+", "", model)[:20]
    base = f"LP-BamBu-A1-{tag}-{lh:g}mm"
    return f"{base}-{slug}" if slug else base


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
    pname = preset_name(mode, lh, name)
    p = {
        "from": "User",
        "inherits": f"{base} @BBL A1",
        "name": pname,
        "print_settings_id": pname,
        # 2 field extruder giong het hub HTML (processPresetJSON) — thieu thi Bambu
        # Studio 2.x import duoc nhung co ban se khong gan duoc variant dau phun
        "print_extruder_id": ["1"],
        "print_extruder_variant": ["Direct Drive Standard"],
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
        lw = fl.get("line_width") or 0.42    # suy tu nozzle THAT trong flow_ceiling
        vmax = int(mvs / (lh * lw))
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

    # 3b) SUPPORT INTERFACE — cai san LUON, ke ca khi support dang TAT: cac o nay chi
    #     co tac dung khi support bat, nen de san gia tri dung de user bat support tay
    #     trong Studio la an ngay (khong phai chinh 5 o). Trick: PLA-PETG khong dinh
    #     nhau ve hoa hoc -> interface bang nhua doi ung thi Z distance = 0 van boc roi.
    #     Luu y: cac o nay chi HIEN trong Studio khi bat toggle Advanced (gia tri van an).
    sup_on = p["enable_support"] == "1"
    ft = [str(t).upper() for t in ((r.get("config") or {}).get("filament_type") or [])]
    body = ft[0] if ft else ""
    partner = {"PLA": "PETG", "PETG": "PLA"}.get(body.split()[0] if body else "")
    # AMS Lite chi co 4 KHAY THAT — file co the khai bao 5+ filament nhung slot >4
    # khong ton tai tren may -> chi tim nhua doi ung trong slot 1-4.
    slot = next((i + 1 for i, t in enumerate(ft[:4]) if partner and t.startswith(partner)), 0)
    ghost = next((i + 1 for i, t in enumerate(ft) if partner and t.startswith(partner) and i >= 4), 0)
    # DOI CHIEU KHAY THAT (MQTT — cung nguon voi panel AMS tren dashboard):
    # file khai bao la mot chuyen, khay dang nap gi la chuyen khac.
    ams = r.get("ams") or []
    ams_has_partner = bool(partner) and any(a.startswith(partner) for a in ams)
    pre = "" if sup_on else " (cài sẵn — đang TẮT support, bật tay trong Studio là ăn ngay)"
    if slot:
        p["support_interface_filament"] = str(slot)
        p["support_top_z_distance"] = "0"
        p["support_bottom_z_distance"] = "0"
        p["support_interface_spacing"] = "0"
        p["support_interface_pattern"] = "rectilinear_interlaced"
        p["independent_support_layer_height"] = "0"
        ams_chk = (f" ✓ Đã đối chiếu AMS: khay máy ĐANG nạp {partner} thật." if ams_has_partner
                   else (f" ⚠️ AMS hiện KHÔNG nạp {partner} (khay thật: "
                         f"{', '.join(ams) or '?'}) — nạp {partner} vào khay trước khi in, "
                         f"không là máy đứng chờ nhựa." if ams else
                         " (Chưa sync được khay AMS — kiểm tra máy có nạp "
                         f"{partner} thật trước khi in.)"))
        why.append(f"TỰ ÁP mẹo gỡ support đẹp{pre}: file có {partner} ở slot {slot} trong khi "
                   f"thân in {body} — 2 nhựa này không dính nhau nên interface {partner} ép khít "
                   f"Z distance = 0 vẫn bóc rời, mặt dưới bóng như mặt trên. Đã set: "
                   f"interface = nhựa {slot}, Top/Bottom Z = 0, spacing = 0, pattern = "
                   f"Rectilinear Interlaced, tắt Independent support layer height. Các ô này "
                   f"nằm trong tab Support, chỉ hiện khi bật toggle ADVANCED (giá trị vẫn ăn "
                   f"kể cả không hiện). Đổi lại: tốn thời gian + nhựa purge mỗi lớp "
                   f"interface.{ams_chk}")
    elif ft:
        # FALLBACK cung vat lieu: khong co nhua doi ung -> interface van la nhua than
        # nhung tro ve DUNG slot than in + khe ho an toan 0.2 (0 la dinh chet).
        body_slot = ft.index(body) + 1
        p["support_interface_filament"] = str(body_slot)
        p["support_top_z_distance"] = "0.2"
        p["support_bottom_z_distance"] = "0.2"
        p["support_interface_spacing"] = "0.5"
        p["support_interface_pattern"] = "rectilinear_interlaced"
        ghost_note = (f" File CÓ khai báo {partner} ở slot {ghost} nhưng AMS Lite chỉ có 4 khay "
                      f"thật — chuyển {partner} vào khay 1-4 + sửa Project Filaments rồi upload "
                      f"lại là hub tự áp Z = 0." if ghost else
                      (f" AMS ĐANG nạp {partner} thật trong khay — chỉ cần THÊM {partner} vào "
                       f"Project Filaments trong Studio rồi upload lại là hub tự áp Z = 0."
                       if ams_has_partner else
                       f" Đã đối chiếu khay AMS thật ({', '.join(ams)}) — không có "
                       f"{partner or 'nhựa đối ứng'}; muốn mặt dưới bóng như mặt trên: nạp "
                       f"{partner or 'PETG'} vào khay + khai báo trong Project Filaments rồi "
                       f"upload lại." if ams else
                       f" Muốn mặt dưới bóng như mặt trên: nạp thêm {partner or 'PETG'} vào AMS "
                       f"(khay 1-4) + khai báo trong Project Filaments rồi upload lại."))
        why.append(f"Support interface CÙNG vật liệu{pre} ({body} slot {body_slot} — không có "
                   f"nhựa đối ứng trong 4 khay AMS): giữ khe Z distance 0.2mm để bóc được "
                   f"(cùng nhựa mà ép 0 là dính chết), pattern Rectilinear Interlaced cho dễ "
                   f"tách. Đổi interface sang khay {body} KHÁC cũng vô ích — cùng hóa học thì "
                   f"dính như nhau, chỉ tốn purge đổi màu.{ghost_note}")
    else:
        ams_note = (f" Khay AMS thật đang nạp: {', '.join(ams)}." if ams else "")
        why.append("MẸO gỡ support đẹp (cần AMS + PETG): đặt Support/raft interface = PETG, "
                   "Top Z distance = 0, Top interface spacing = 0, Interface pattern = "
                   "Rectilinear Interlaced, tắt Independent support layer height (tab Support, "
                   "bật toggle ADVANCED mới hiện các ô này). PLA–PETG không dính nhau về hóa "
                   "học nên khít 0mm vẫn bóc rời — mặt dưới bóng như mặt trên. Upload file .3mf "
                   "có khai báo sẵn PETG trong Project Filaments là hub TỰ ÁP giúp bạn. "
                   "CẢNH BÁO: cùng vật liệu thì KHÔNG được để Z distance 0 (dính chết vào "
                   "model)." + ams_note)

    # 4) BRIM — quyet dinh bang NGUY CO LAT, khong phai bang cam giac
    #    Nguy co lat ~ chieu cao / canh vuong tuong duong cua mat day.
    #    Day rong + thap  -> KHONG can brim (brim ton thoi gian + phai got via).
    #    Day hep + cao    -> BAT BUOC brim, nguoc lai in giua chung se do.
    bed = m.get("bed_cm2", 0)
    h_mm = m.get("height", 0)
    side = math.sqrt(bed * 100) if bed > 0 else 0.01      # cm2 -> mm2 -> canh vuong td
    ratio = h_mm / side if side else 99
    #    Yeu to VAT LIEU (Simplify3D/Xometry): ABS/ASA co ngot manh -> venh mep du day
    #    rong, van can brim. PLA/PETG tren PEI nham thi theo hinh hoc thuan tuy.
    warpy = body.split()[0] in ("ABS", "ASA") if body else False
    if bed >= 20 and ratio <= 3 and not warpy:
        p["brim_type"] = "no_brim"
        p["brim_width"] = "0"
        why.append(f"KHÔNG brim: đáy rộng {bed} cm² (cạnh ~{side:.0f}mm) so với cao {h_mm}mm "
                   f"→ tỉ lệ lật {ratio:.1f} (an toàn <3). Đáy dày/rộng thế này brim chỉ tốn "
                   f"thời gian và phải gọt via.")
    elif bed >= 8 or (warpy and ratio <= 3):
        p["brim_type"] = "outer_only"
        p["brim_width"] = "5"
        why.append(f"Brim 5mm: đáy {bed} cm², tỉ lệ lật {ratio:.1f}"
                   + (f" — nhựa {body} co ngót mạnh, dễ vênh mép nên brim dù đáy rộng."
                      if warpy else " — bám thêm cho chắc."))
    else:
        p["brim_type"] = "outer_only"
        p["brim_width"] = "8"
        why.append(f"Brim 8mm (BẮT BUỘC): đáy chỉ {bed} cm², tỉ lệ lật {ratio:.1f} — "
                   f"không brim thì lớp đầu bong / model đổ giữa chừng.")
    # SKIRT + DRAFT SHIELD: skirt chi de moi nhua (A1 tu moi bang purge line -> tat).
    # RIENG nhua co ngot (ABS/ASA) tren may khung HO nhu A1: draft_shield bien skirt
    # thanh tuong chan gio cao bang model. Bambu AN o nay khoi UI (Tab.cpp comment
    # dong draft_shield) — CHI set duoc qua preset, phai di kem skirt_loops > 0.
    if warpy:
        p["skirt_loops"] = "2"
        p["draft_shield"] = "enabled"
        why.append(f"DRAFT SHIELD bật + skirt 2 vòng: {body} co ngót mạnh mà A1 là máy khung hở "
                   f"— tường skirt cao bằng model chắn gió lùa, đỡ vênh/tách lớp. Ô này Bambu "
                   f"ẨN khỏi giao diện Studio, chỉ preset mới set được — đừng tìm trong tab "
                   f"Others, nó không có ở đó.")
    else:
        p["skirt_loops"] = "0"
        why.append("Skirt = 0 vòng: skirt chỉ để mồi nhựa, mà A1 đã tự mồi bằng purge line "
                   "trước mỗi lần in — vẽ thêm skirt là tốn thời gian vô ích. (PLA/PETG không "
                   "cần draft shield chắn gió.)")

    # 5) TOP/BOTTOM SHELL — tinh theo quy tac do day (wiki OrcaSlicer), khong cung "4/3"
    infill_pct = float(re.sub(r"[^\d.]", "", M["infill"]) or 10)
    tsl, tsl_why = top_shell_layers(lh, infill_pct, 1.0)
    bsl = max(3, math.ceil(0.8 / lh))
    p["top_shell_layers"] = str(tsl)
    p["bottom_shell_layers"] = str(bsl)
    p["top_shell_thickness"] = "1"          # chot chan: slicer tu tang lop neu mong hon
    p["top_surface_pattern"] = "monotonicline"   # wiki: monotonic line dep nhat cho mat tren
    why.append(f"Mặt trên {tsl} lớp / đáy {bsl} lớp: {tsl_why}.")

    # 6) SEAM — quyet dinh theo BANG TRA wiki Bambu Studio (wiki.bambulab.com/.../Seam),
    #    khong code cung theo cam tinh. Z-seam la diem bat dau moi vong in tren TUONG
    #    DUNG nen khong the "giau xuong day". 3 truong hop theo wiki:
    #    a) Aligned/Nearest tu san vi tri theo uu tien: dinh LOM (concave, khong hang)
    #       > dinh loi > diem thuong > diem hang. => Model co GOC CANH SAC thi aligned
    #       tu giau seam vao goc va xep thang hang doc.
    #    b) Back: "seam dat sau model — muon mat TRUOC dep (vi du mat na Iron Man)".
    #       => Chi dung khi co 1 mat dung LON vuot troi lam "mat lung" hy sinh duoc.
    #    c) Scarf: Bambu chi ap khi be mat KHONG co goc du sac (nguyen van co che
    #       "scarf application angle threshold") — tuc mat tron/cong trơn.
    flat_ratio = fa.get("flat_ratio", 0)
    n_dirs = fa.get("n_dirs", 0)
    dom = fa.get("vert_dom_ratio", 1.0)
    has_corners = flat_ratio >= 0.5 and 2 <= n_dirs <= 6   # tru tron rai deu 7-8 huong
    if has_corners:
        # Model hop/CAD -> BACK: ep 100% seam ve phia Y+ (wiki case b — "muon mat truoc
        # dep"). Aligned tuy nap goc tung vong nhung model nhieu vong roi rac (nan, khe)
        # van vuong seam ra mat nhin thay — Back gom het ve 1 mat de xoay ra sau.
        p["seam_position"] = "back"
        p["seam_slope_type"] = "none"
        extra = (f" Mặt đứng lớn nhất gấp {dom:.1f}× các mặt khác — ưu tiên xoay chính mặt đó "
                 f"ra sau." if dom >= 1.8 else
                 f" Các mặt to ngang nhau ({n_dirs} hướng, chênh {dom:.1f}×) — chọn mặt ít nhìn "
                 f"thấy nhất xoay ra sau.")
        why.append(f"Seam = Back (wiki Bambu: 'muốn mặt trước đẹp — như mặt nạ Iron Man'): dồn "
                   f"100% mối nối về phía Y+ của bàn in, các mặt còn lại sạch seam.{extra} "
                   f"Muốn seam nấp góc kiểu CAD cổ điển thì đổi lại Aligned; muốn chỉ định "
                   f"đích xác từng mặt: Seam painting.")
    else:
        # Khong co goc sac (tron/huu co) -> dung dung co che scarf cua Bambu (wiki case c)
        p["seam_position"] = "aligned"
        p["seam_slope_type"] = "all"
        why.append(f"Seam = Aligned + SCARF: bề mặt không có góc đủ sắc để nấp "
                   f"(phẳng {int(flat_ratio*100)}%, {n_dirs or 'rải đều'} hướng đứng) → theo đúng "
                   f"cơ chế 'scarf application angle threshold' của Bambu: tán vát mối nối "
                   f"trên mặt cong. Muốn giấu hẳn 1 mặt: dùng Seam painting.")

    # 6b) MAT CONG MUOT — arc fitting mac dinh TAT trong Bambu (PrintConfig default 0):
    #     bat len thi bien cong xuat G2/G3 arc lien mach thay vi da giac gay khuc (lo
    #     facet doc theo tuong cong). resolution nho hon = duong bao min hon (cham slice).
    #     Van NGANG theo lop (stair-step mat doc) thi CHI giam duoc bang layer nho
    #     (che do Dep) hoac Variable Layer Height — VLH phai bat TAY tren object
    #     (nam trong danh sach ignore cua PrintConfig, preset khong set duoc).
    if not has_corners or mode == "quality":
        p["enable_arc_fitting"] = "1"
        p["resolution"] = "0.008"
        why.append("Mặt cong mượt: BẬT Arc fitting (mặc định Bambu tắt) → biên cong chạy "
                   "G2/G3 liền mạch thay vì đa giác gãy khúc, + resolution 0.008mm (mịn hơn "
                   "mặc định 0.01). Vân NGANG theo lớp trên mặt dốc muốn hết hẳn phải bật "
                   "Variable Layer Height bằng tay trên object trong Studio — preset không "
                   "set được (Bambu ignore key này).")

    # 7) WALL ORDER — phu thuoc SO THANH truoc, roi moi den overhang.
    #    >=3 thanh: "inner-outer-inner wall" (sandwich) la toi uu tuyet doi — thanh ngoai
    #    duoc 1 thanh trong do lung (seam gon, khong vong) NHUNG van in som (kich thuoc
    #    chinh xac). Chi kha thi khi wall_loops >= 3 nen 2 thanh phai chon 1 trong 2.
    ov = m.get("overhang_pct", 0)
    if M["walls"] >= 3:
        p["wall_sequence"] = "inner-outer-inner wall"
        why.append(f"Thứ tự thành = Inner-Outer-Inner (sandwich): có {M['walls']} thành nên thành "
                   f"ngoài được kẹp giữa — vừa có thành trong đỡ lưng (seam gọn, không võng "
                   f"overhang) vừa in sớm (lỗ/chốt chính xác kích thước). Chỉ ≥3 thành mới dùng được.")
    else:
        # 2 thanh khong du de sandwich -> Inner/Outer (wiki default: seam gon, mat min).
        # KHONG dung Outer/Inner nua: loi kich thuoc chinh xac khong dang gia seam xau.
        p["wall_sequence"] = "inner wall/outer wall"
        why.append("Thứ tự thành = Inner/Outer (mặc định wiki, chỉ 2 thành không sandwich được): "
                   "thành ngoài in sau, tựa vào thành trong → bề mặt mịn + seam gọn.")

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

    # 11) LOP DAU — giu 50 mm/s (so Bambu tune cho A1: PEI nham + input shaping);
    #     ha toc do chi lam LAU chu khong bam hon. Bam kem thi tang DO DAY lop dau:
    #     lop day hon = chiu do venh ban tot hon + bead rong hon -> diet tich bam lon hon.
    p["initial_layer_speed"] = ["50"]
    if bed < 8 or ratio > 3:
        p["initial_layer_print_height"] = "0.24"
        why.append(f"Lớp đầu DÀY 0.24mm (thay vì hạ tốc độ): đáy chỉ {bed} cm² / tỉ lệ lật "
                   f"{ratio:.1f} — lớp dày hơn nuốt độ vênh bàn + bead bè rộng hơn → bám chắc "
                   f"hơn mà KHÔNG chậm đi. Tốc độ giữ 50 mm/s chuẩn A1.")
    else:
        why.append(f"Lớp đầu giữ 50 mm/s / 0.2mm (chuẩn A1): đáy {bed} cm² bám thoải mái trên "
                   f"bàn PEI nhám. 25 mm/s là số cũ cho máy bàn kính — chỉ chậm thêm chứ "
                   f"không bám thêm.")

    vl = r.get("variable_layer")
    if vl and vl["extra_layers"] > VLH_WARN_LAYERS:
        why.append(f"Gỡ Variable Layer Height: nó đang âm thầm cộng {vl['extra_layers']} lớp "
                   f"(+{vl['extra_pct']}%). Server tự gỡ khi slice — không nhét được vào preset "
                   f"vì nó gắn theo vật thể trong .3mf.")

    return {"preset": p, "why": why, "mode": mode, "mode_label": M["label"]}


def analyze(path: str, mode: str = "balanced", ams: list | None = None) -> dict:
    """ams: loai nhua THAT trong khay AMS (tu MQTT, vd ['PLA LITE','PETG BASIC']).
    None/[] = khong sync duoc may -> chi suy theo khai bao trong file."""
    r = analyze_stl(path) if path.lower().endswith(".stl") else analyze_3mf(path)
    r["ams"] = [str(t).upper() for t in (ams or []) if t]
    import os as _os
    nm = _os.path.splitext(_os.path.basename(path))[0][:20]
    r["export"] = make_preset(r, nm, mode)
    r["presets"] = {k: make_preset(r, nm, k) for k in MODES}
    return r


if __name__ == "__main__":
    import sys
    print(json.dumps(analyze(sys.argv[1]), ensure_ascii=False, indent=2))
