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


# ---------- doc mesh 3mf (co ap transform) ----------
def _mat(s: str | None) -> list | None:
    """Chuoi transform 3MF '12 so' -> list[12], sai dinh dang -> None (bo qua)."""
    try:
        f = [float(x) for x in (s or "").split()]
    except ValueError:
        return None
    return f if len(f) == 12 else None


def _xf(v, m):
    """Ap ma tran 3MF (row-vector: v' = v @ M) len 1 dinh."""
    x, y, z = v
    return (x * m[0] + y * m[3] + z * m[6] + m[9],
            x * m[1] + y * m[4] + z * m[7] + m[10],
            x * m[2] + y * m[5] + z * m[8] + m[11])


def _mesh_tris(xml: str, mats: list) -> list:
    """Doc vertex/triangle tu 1 file .model roi ap lan luot cac ma tran trong mats."""
    V = [(float(a), float(b), float(c)) for a, b, c in re.findall(
        r'<vertex[^>]*x="([-\d.eE]+)"[^>]*y="([-\d.eE]+)"[^>]*z="([-\d.eE]+)"', xml)]
    for m in mats:
        if m:
            V = [_xf(v, m) for v in V]
    T = [(int(a), int(b), int(c)) for a, b, c in re.findall(
        r'<triangle[^>]*v1="(\d+)"[^>]*v2="(\d+)"[^>]*v3="(\d+)"', xml)]
    return [(V[i], V[j], V[k]) for i, j, k in T if i < len(V) and j < len(V) and k < len(V)]


def load_3mf_tris(z: zipfile.ZipFile, names: list, notes: list | None = None) -> list:
    """Doc TOAN BO mesh trong .3mf va ap transform xoay/di chuyen cua Bambu Studio.

    Bambu luu phep xoay o <component transform> + <item transform> trong
    3D/3dmodel.model goc — toa do dinh trong 3D/Objects/*.model KHONG doi.
    Doc dinh tho ma bo qua transform thi xoay kieu gi ket qua cung nhu cu.
    """
    models = [n for n in names if n.lower().endswith(".model")]
    root = next((n for n in models if "objects" not in n.lower()), None)
    if not root:
        obj = [n for n in models if "objects" in n.lower()]
        return _mesh_tris(z.read(obj[0]).decode("utf-8", "ignore"), []) if obj else []

    xml = z.read(root).decode("utf-8", "ignore")
    items = {}                       # objectid goc -> ma tran <item> (hoac None)
    for it in re.finditer(r'<item\b[^>]*objectid="(\d+)"[^>]*/?>', xml):
        tm = re.search(r'transform="([^"]+)"', it.group(0))
        mat = _mat(tm.group(1)) if tm else None
        if tm and mat is None and notes is not None:
            notes.append("⚠ Không đọc được ma trận xoay trong .3mf — phân tích có thể "
                         "KHÔNG khớp hướng đặt thật trong Bambu Studio.")
        items[it.group(1)] = mat

    tris: list = []
    for om in re.finditer(r'<object\b[^>]*\bid="(\d+)"[^>]*>(.*?)</object>', xml, re.S):
        oid, body = om.group(1), om.group(2)
        if oid not in items:
            continue                 # object khong duoc build -> bo qua
        if "<mesh" in body:          # mesh nhung truc tiep trong root (3mf ngoai Bambu)
            tris += _mesh_tris(body, [items[oid]])
        for cm in re.finditer(r'<component\b[^>]*/?>', body):
            tag = cm.group(0)
            pm = re.search(r'(?:\w+:)?path="([^"]+)"', tag)
            tm = re.search(r'transform="([^"]+)"', tag)
            cmat = _mat(tm.group(1)) if tm else None
            if not pm:               # component tro toi object cung file -> hiem, bo qua
                continue
            want = pm.group(1).lstrip("/").lower()
            src = next((n for n in models if n.lower() == want), None)
            if src:
                tris += _mesh_tris(z.read(src).decode("utf-8", "ignore"),
                                   [cmat, items[oid]])
    if tris:
        return tris
    # fallback: khong doc duoc gi tu root -> hanh vi cu (file Objects dau tien, khong transform)
    if notes is not None:
        notes.append("⚠ File .3mf không theo cấu trúc Bambu chuẩn — đọc mesh thô, BỎ QUA "
                     "transform xoay (nếu có). Kiểm tra lại hướng đặt trước khi tin đề xuất.")
    obj = [n for n in models if "objects" in n.lower()]
    return _mesh_tris(z.read(obj[0]).decode("utf-8", "ignore"), []) if obj else []


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


def try_rotations(tris: list, x_angles=(-60, -45, -30, -15, 0, 15, 30, 45, 90, 180),
                  y_angles=(-90, -45, 45, 90)) -> list:
    """Quet xoay quanh X VA quanh Y -> phu du 6 mat up xuong + cac goc nghieng.
    Ghi CA overhang lan dien tich bam ban, danh dau 'recommend' cho huong TOT NHAT.

    BAY: xoay 45deg co the bien day phang thanh mat doc 45deg -> thuat toan khong
    con dem la overhang (0.59%) nhung bam ban tut ve 0 -> dung tren canh dao, lop
    dau khong bam. Vi vay PHAI doc bed_cm2 cung luc, dung nhin moi overhang.

    Diem xep hang huong (chi trong cac huong 'usable'):
      1. overhang_pct nho nhat  — it support nhat (tien nhua + thoi gian + khoi got)
      2. bed_cm2 lon nhat       — bam ban chac nhat (lop 1-2 song sot)
      3. height thap nhat       — in nhanh + do rung dinh cao
    """
    # Tien tinh 1 lan: dien tich + normal + toa do 3 dinh; moi huong chi can
    # thanh phan z sau xoay cua normal va dinh -> khong dung lai mesh.
    pre = []
    for p, q, r in tris:
        ux, uy, uz = q[0]-p[0], q[1]-p[1], q[2]-p[2]
        vx, vy, vz = r[0]-p[0], r[1]-p[1], r[2]-p[2]
        nx, ny, nz = uy*vz-uz*vy, uz*vx-ux*vz, ux*vy-uy*vx
        L = math.sqrt(nx*nx + ny*ny + nz*nz)
        if not L:
            continue
        pre.append((L/2, nx/L, ny/L, nz/L, p, q, r))
    tot = sum(x[0] for x in pre)

    def measure(axis: str, ang: float) -> dict:
        a = math.radians(ang)
        ca, sa = math.cos(a), math.sin(a)
        # Quay quanh X: z' = y*sin + z*cos.  Quay quanh Y: z' = -x*sin + z*cos.
        if axis == "X":
            nzf = lambda nx, ny, nz: ny*sa + nz*ca
            zf = lambda v: v[1]*sa + v[2]*ca
        else:
            nzf = lambda nx, ny, nz: -nx*sa + nz*ca
            zf = lambda v: -v[0]*sa + v[2]*ca
        zmin = zmax = None
        rows = []
        for ar, nx, ny, nz, p, q, r in pre:
            nz2 = nzf(nx, ny, nz)
            zs = (zf(p), zf(q), zf(r))
            ztop, zlo = max(zs), min(zs)
            if zmin is None or zlo < zmin:
                zmin = zlo
            if zmax is None or ztop > zmax:
                zmax = ztop
            rows.append((ar, nz2, ztop))
        over = bed = 0.0
        sup_vol = 0.0     # UOC LUONG SUPPORT: dien tich hang x chieu cao cot chong (mm3)
        zbase = zmin or 0
        for ar, nz2, ztop in rows:
            if nz2 < -COS45:
                if ztop - zmin <= BED_EPS:
                    bed += ar
                else:
                    over += ar
                    sup_vol += ar * (ztop - zbase)   # mat hang cang CAO khoi ban -> cot cang dai
        return {"axis": axis, "angle": ang, "angle_x": ang if axis == "X" else None,
                "overhang_pct": round(over / tot * 100, 2) if tot else 0.0,
                "bed_cm2": round(bed / 100, 1),
                "support_cm3": round(sup_vol / 1000, 1),   # mm3 -> cm3 (ti le nhua+gio support)
                "height": round((zmax or 0) - (zmin or 0), 1),
                "usable": bed / 100 >= MIN_BED_CM2}

    out = [measure("X", ax) for ax in x_angles] + [measure("Y", ay) for ay in y_angles]
    good = [x for x in out if x["usable"]]
    if good:
        # Xep hang theo SUPPORT THAT (cm3 = it nhua+gio nhat) truoc, roi bam ban, roi cao.
        # Truoc day chi theo overhang% -> co the chon huong bam ban to nhung support NHIEU.
        best = min(good, key=lambda x: (x["support_cm3"], x["overhang_pct"], -x["bed_cm2"], x["height"]))
        best["recommend"] = True
    return out


def _rot_vertex(v, axis: str, ca: float, sa: float):
    """Xoay 1 dinh quanh X hoac Y — CUNG cong thuc voi measure() trong try_rotations."""
    x, y, z = v
    if axis == "X":
        return (x, y*ca - z*sa, y*sa + z*ca)
    return (x*ca + z*sa, y, -x*sa + z*ca)


def render_iso_svg(tris: list, axis: str = "X", ang: float = 0,
                   size: int = 230, max_faces: int = 12000,
                   rgb: tuple = (233, 125, 62)) -> str:
    """Ve model da xoay thanh anh SVG isometric nho (painter's algorithm thuan Python).

    Muc dich: user NHIN THAY model up mat nao xuong ban o huong de xuat — khong phai
    doan tu con so goc. Mesh lon thi giu max_faces tam giac to nhat (du hinh dang)."""
    a = math.radians(ang)
    ca, sa = math.cos(a), math.sin(a)
    C30, S30 = math.cos(math.radians(30)), math.sin(math.radians(30))
    lx, ly, lz = 0.40, 0.30, 0.87                       # huong den (da chuan hoa ~1)
    faces = []
    for p, q, r in tris:
        p2, q2, r2 = (_rot_vertex(v, axis, ca, sa) for v in (p, q, r))
        ux, uy, uz = q2[0]-p2[0], q2[1]-p2[1], q2[2]-p2[2]
        vx, vy, vz = r2[0]-p2[0], r2[1]-p2[1], r2[2]-p2[2]
        nx, ny, nz = uy*vz-uz*vy, uz*vx-ux*vz, ux*vy-uy*vx
        L = math.sqrt(nx*nx + ny*ny + nz*nz)
        if not L:
            continue
        # camera iso nhin tu (+1,+1,+1): cull mat quay lung (n·cam <= 0)
        if (nx + ny + nz) / L <= 0:
            continue
        shade = 0.35 + 0.65 * max(0.0, (nx*lx + ny*ly + nz*lz) / L)
        pts = []
        depth = 0.0
        for x, y, z in (p2, q2, r2):
            u = (x - y) * C30
            w = (x + y) * S30 - z                       # truc man hinh huong xuong
            pts.append((u, w))
            depth += x + y + z
        faces.append((depth / 3, L / 2, shade, pts))
    if not faces:
        return ""
    if len(faces) > max_faces:                          # mesh khung: giu tam giac to
        faces.sort(key=lambda f: -f[1])
        faces = faces[:max_faces]
    faces.sort(key=lambda f: f[0])                      # xa ve truoc (painter)
    us = [u for _, _, _, pts in faces for u, _ in pts]
    ws = [w for _, _, _, pts in faces for _, w in pts]
    u0, u1, w0, w1 = min(us), max(us), min(ws), max(ws)
    span = max(u1 - u0, w1 - w0) or 1.0
    k = (size - 16) / span
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}" '
             f'viewBox="0 0 {size} {size}">']
    for _, _, shade, pts in faces:
        cr, cg, cb = int(rgb[0]*shade), int(rgb[1]*shade), int(rgb[2]*shade)
        d = " ".join(f"{(u-u0)*k+8:.1f},{(w-w0)*k+8:.1f}" for u, w in pts)
        parts.append(f'<polygon points="{d}" fill="rgb({cr},{cg},{cb})"/>')
    parts.append("</svg>")
    return "".join(parts)


def rot_preview(tris: list, rots: list, color: str | None = None) -> dict:
    """Cap anh render 'hien tai' vs 'de xuat' — user NHIN de biet xoay the nao.
    color: hex '#RRGGBB' cua khay AMS that (tu MQTT) -> render dung mau nhua."""
    rgb = (233, 125, 62)
    if color:
        h = color.lstrip("#")
        if len(h) >= 6:
            try:
                c = tuple(int(h[i:i+2], 16) for i in (0, 2, 4))
                # mau qua toi thi nang len de con thay khoi (shade nhan them 0.35-1.0)
                rgb = tuple(max(v, 40) for v in c)
            except ValueError:
                pass
    out = {"current": render_iso_svg(tris, "X", 0, rgb=rgb)}

    # 1-2 GOI Y XOAY — CHI khi THUC SU BOT SUPPORT, khong bia phuong an te hon:
    #   - support_cm3 phai THAP HON ro rang -> xoay de BOT NHUA+GIO support (dung y user:
    #     bam ban to ma support nhieu thi in lau, khong dang)
    #   - bam ban du CHAC (>=20cm2 VA khong sut qua nua) -> tranh "bay canh dao"
    # Huong hien tai da it support nhat + bam tot -> options rong -> "da tot nhat".
    cur = next((x for x in rots if x["axis"] == "X" and x["angle"] == 0), None)
    cur_sup = cur.get("support_cm3", 999.0) if cur else 999.0
    cur_bed = cur["bed_cm2"] if cur else 0.0
    bed_floor = max(20.0, 0.5 * cur_bed)
    ranked = sorted((x for x in rots if x.get("usable")),
                    key=lambda x: (x.get("support_cm3", 0), -x["bed_cm2"], x["height"]))
    opts, seen = [], set()
    for x in ranked:
        if x["axis"] == "X" and x["angle"] == 0:
            continue                                   # bo huong hien tai
        # phai bot support DANG KE (>=15% hoac >=3cm3) — khong xoay chi de nhinh chut
        if x.get("support_cm3", 0) > cur_sup - max(3.0, 0.15 * cur_sup):
            continue
        if x["bed_cm2"] < bed_floor:
            continue                                   # bam qua it/tut manh -> bay canh dao
        key = (x["axis"], x["angle"])
        if key in seen:
            continue
        seen.add(key)
        opts.append({"axis": x["axis"], "angle": x["angle"], "overhang_pct": x["overhang_pct"],
                     "bed_cm2": x["bed_cm2"], "height": x["height"],
                     "support_cm3": x.get("support_cm3", 0),
                     "svg": render_iso_svg(tris, x["axis"], x["angle"], rgb=rgb)})
        if len(opts) >= 2:
            break
    out["options"] = opts
    out["current_meta"] = ({"overhang_pct": cur["overhang_pct"], "bed_cm2": cur["bed_cm2"],
                            "height": cur["height"], "support_cm3": cur.get("support_cm3", 0)}
                           if cur else None)
    # "tot nhat" = KHONG con phuong an xoay AN TOAN nao tot hon (khop voi options)
    out["current_is_best"] = not opts
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


def analyze_3mf(path: str, color: str | None = None) -> dict:
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

        # mesh — doc qua load_3mf_tris de AP TRANSFORM xoay cua Bambu Studio
        tris = load_3mf_tris(z, names, notes=res["tips"])
        if tris:
            res["mesh"] = mesh_stats(tris)
            res["faces"] = face_analysis(tris)
            if len(tris) <= ROT_MAX_TRIS:
                res["bridges"] = ceiling_bridges(tris)
                res["thin"] = thin_walls(tris)
            if len(tris) <= ROT_MAX_TRIS:
                res["rotations"] = try_rotations(tris)
                res["rot_preview"] = rot_preview(tris, res["rotations"], color)
            else:
                res["tips"].append(f"Mesh {len(tris):,} tam giác vượt ngưỡng {ROT_MAX_TRIS:,} — bỏ quét xoay để không treo server.")

        nominal = float(cfg.get("layer_height") or 0.2)
        h = res.get("mesh", {}).get("height") or 0
        res["variable_layer"] = variable_layer(z, h, nominal) if h else None
        res["flow"] = flow_ceiling(cfg)

    _advise(res)
    return res


def analyze_stl(path: str, color: str | None = None) -> dict:
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
        res["bridges"] = ceiling_bridges(tris)
        res["thin"] = thin_walls(tris)
    if len(tris) <= ROT_MAX_TRIS:
        res["rotations"] = try_rotations(tris)
        res["rot_preview"] = rot_preview(tris, res["rotations"], color)
    else:
        res["tips"].append(f"Mesh {len(tris):,} tam giác vượt ngưỡng {ROT_MAX_TRIS:,} — bỏ quét xoay để không treo server.")
    _advise(res)
    return res


def orientation_tips(rots: list) -> list:
    """Tips xoay huong THONG MINH — chi xuat hien khi co de xuat xoay khac huong
    hien tai, de user can nhac them cac tieu chi ma hinh hoc thuan khong do duoc.

    Nguon: Protolabs/Hubs knowledge-base (part orientation: accuracy/strength/
    time/finish) + kiem chung slice that tren hub (hop dung 698 lop NHANH hon
    hop nam 510 lop ~10% vi moi lop nho hon — so lop KHONG quyet dinh thoi gian).
    """
    best = next((x for x in rots if x.get("recommend")), None)
    cur = next((x for x in rots if x["axis"] == "X" and x["angle"] == 0), None)
    if not best or not cur or best is cur:
        return []
    tips = []
    d_ov = cur["overhang_pct"] - best["overhang_pct"]
    if cur["usable"] and d_ov <= 8:
        tips.append(
            f"⚖️ Hướng hiện tại CŨNG in được (overhang chỉ hơn đề xuất {d_ov:.1f}%). "
            "Xếp hạng hình học là DỰ ĐOÁN: thời gian in phụ thuộc diện tích mỗi lớp "
            "nhiều hơn số lớp — hướng cao hơn có thể vẫn NHANH hơn. Muốn số thật, "
            "chạy Tối ưu E2E slice cả hai hướng rồi so.")
    tips.append(
        "💪 Nếu chi tiết CHỊU LỰC: lớp FDM khỏe theo mặt phẳng XY gấp 4–5 lần phương Z "
        "(Protolabs/Hubs) — ưu tiên hướng đặt đường lực NẰM TRONG mặt lớp; lực kéo dọc Z "
        "dễ tách lớp, quan trọng hơn cả việc ít support.")
    tips.append(
        "👁 Mặt cần ĐẸP: mặt trên cùng mịn nhất (mỏ đùn ủi qua), mặt úp bàn ăn vân PEI, "
        "mặt tựa support XẤU nhất — xoay mặt thẩm mỹ lên trên hoặc úp xuống bàn.")
    tips.append(
        "⭕ Lỗ tròn/trụ chính xác nhất khi trục thẳng ĐỨNG (lớp đồng tâm, không bậc thang) — "
        "nếu model có lỗ lắp ghép, ưu tiên tiêu chí này hơn overhang (Hubs).")
    return tips


def _advise(r: dict) -> None:
    """Sinh canh bao + khuyen nghi tu so lieu (khong doan bua)."""
    r["tips"] = (r.get("tips") or []) + orientation_tips(r.get("rotations") or [])
    th = r.get("thin") or {}
    # Chi canh bao khi >=8% mat mau la thanh mong VA mong that (0.3-1.2mm) — duoi
    # nguong nay la nhieu ray-cast, khong keu bao dong gia.
    if th.get("thin_frac", 0) >= 0.08 and (th.get("min_mm") or 9) <= WALL_SOFT_MM:
        r["issues"].append(
            f"THÀNH MỎNG: ~{int(th['thin_frac']*100)}% bề mặt (mẫu) có bề dày < {WALL_SOFT_MM}mm "
            f"(mỏng nhất {th['min_mm']}mm). Dưới {WALL_HARD_MM}mm (2 đường nozzle 0.4) là "
            f"KHÔNG in đặc được (Wikifactory); 1.2mm = 2 perimeter khuyến nghị (LayerX); "
            f"chịu lực nên ≥1.5mm (3D Demand). Arachne (đã bật) cứu được phần nào, nhưng "
            f"triệt để phải dày hóa trong CAD hoặc scale model lên.")
    # VAT CAO -> canh bao LECH TRUC / VENH DINH tren A1 (bed-slinger day ban Y). Cang cao,
    # tam khoi cao, quan tinh khi ban giat cang lon -> ~2/3 chieu cao hay lech/nghieng.
    # Nguon: wiki Bambu layer-shift + dac thu A1 khung ho 1 ray Z.
    m0 = r.get("mesh") or {}
    h_tall = m0.get("height") or 0
    dims0 = m0.get("dims") or []
    footmin = min(dims0[0], dims0[1]) if len(dims0) >= 2 and dims0[0] and dims0[1] else 999
    slim = (h_tall / footmin) if footmin else 0     # cao/canh day nho nhat: >3 la manh de venh
    if h_tall >= 140:
        r["issues"].append(
            f"VẬT CAO {h_tall:.0f}mm (>140mm){' + MẢNH (cao/đáy '+str(round(slim,1))+'×)' if slim>3 else ''}: "
            f"trên A1 (đẩy bàn trục Y, khung hở 1 ray Z) dễ LỆCH TRỤC / nghiêng ở ~2/3 chiều cao — "
            f"lúc này khối cao, quán tính khi bàn giật lớn nhất, cộng rung cộng hưởng.")
        r["tips"].append(
            f"🗼 Vật cao {h_tall:.0f}mm chống lệch trục Z (nguồn: wiki Bambu layer-shift + đặc thù A1): "
            "(1) BẬT 'Auto-recovery from step loss' trên máy (Cài đặt ▸ Print Options) — máy tự về đúng "
            "vị trí khi mất bước. (2) GIẢM tốc + gia tốc: outer/inner wall accel về ~3000–5000, tốc thành "
            "ngoài ≤120 để bớt lực giật (chế độ Cân bằng/Đẹp đã chậm hơn Nhanh). (3) Căng lại DÂY ĐAI "
            "trục Y (chùng đai = lệch lặp ở cùng cao độ). (4) Brim/đáy rộng cho vững chân; nếu quá mảnh: "
            "chẻ đôi in 2 phần rồi ghép, hoặc xoay cho THẤP xuống. (5) Đừng đổi sang tốc Ludicrous giữa in.")
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
        cur = next((x for x in rots if x["axis"] == "X" and x["angle"] == 0), None)
        best = next((x for x in rots if x.get("recommend")), None)
        # Chi khuyen xoay khi VUA giam overhang VUA con bam ban du
        if best and cur and not (best["axis"] == "X" and best["angle"] == 0) \
                and best["overhang_pct"] < cur["overhang_pct"] - 2:
            r["tips"].append(
                f"★ ĐỀ XUẤT xoay {best['angle']}° quanh trục {best['axis']}: overhang "
                f"{cur['overhang_pct']}% → {best['overhang_pct']}% (bớt support), bám bàn "
                f"{best['bed_cm2']} cm², cao {best['height']}mm. Xếp theo: ít support nhất "
                f"→ bám bàn nhiều nhất → thấp nhất.")
        trap = [x for x in rots if not x["usable"] and cur and x["overhang_pct"] < cur["overhang_pct"]]
        if trap:
            t = trap[0]
            r["issues"].append(
                f"BẪY: xoay {t['angle']}° quanh {t['axis']} nhìn thì overhang chỉ "
                f"{t['overhang_pct']}% nhưng bám bàn = {t['bed_cm2']} cm² "
                f"(đứng trên cạnh dao) — KHÔNG dùng được.")

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



BRIDGE_MM = 10.0    # span tran <= 10mm -> bac cau khong can support (Hydra Research design rules)
WALL_HARD_MM = 0.8  # 2 duong nozzle 0.4 — duoi muc nay thanh KHONG in dac duoc (Wikifactory)
WALL_SOFT_MM = 1.2  # 2 perimeter khuyen nghi (LayerX); 1.5mm neu chiu luc (3D Demand)


def ceiling_bridges(tris: list, bridge_mm: float = BRIDGE_MM) -> dict:
    """Do TRAN LO/KHE: patch mat up xuong gan ngang, lo lung tren khong.

    Loc tam giac nz < -0.9 (up xuong, nghieng <~26 do so voi ngang) khong cham ban,
    gom patch theo dinh chung (union-find), span = canh NGAN cua bbox patch (khe
    8x100mm chi can bac cau 8mm). span <= bridge_mm -> A1 bac cau duoc, khong can
    support; lon hon -> tran that, phai do.
    """
    zmin = min(v[2] for t in tris for v in t)
    down = []
    for p, q, r in tris:
        ux, uy, uz = q[0]-p[0], q[1]-p[1], q[2]-p[2]
        vx, vy, vz = r[0]-p[0], r[1]-p[1], r[2]-p[2]
        nx, ny, nz = uy*vz-uz*vy, uz*vx-ux*vz, ux*vy-uy*vx
        L = math.sqrt(nx*nx+ny*ny+nz*nz)
        if not L or nz/L > -0.9:
            continue
        if min(p[2], q[2], r[2]) - zmin <= BED_EPS:
            continue                       # cham ban -> khong phai tran
        down.append((L/2, p, q, r))
    if not down:
        return {"patches": 0, "bridge_cm2": 0.0, "ceil_cm2": 0.0, "max_span": 0.0}

    key = lambda v: (round(v[0], 1), round(v[1], 1), round(v[2], 1))
    parent = {}
    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a
    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb
    for _, p, q, r in down:
        for v in (p, q, r):
            parent.setdefault(key(v), key(v))
        union(key(p), key(q)); union(key(p), key(r))
    groups = {}
    for i, (ar, p, q, r) in enumerate(down):
        groups.setdefault(find(key(p)), []).append(i)

    bridge = ceil = 0.0
    max_span = 0.0
    for idxs in groups.values():
        xs = [v[0] for i in idxs for v in down[i][1:]]
        ys = [v[1] for i in idxs for v in down[i][1:]]
        span = min(max(xs)-min(xs), max(ys)-min(ys))
        area = sum(down[i][0] for i in idxs)
        max_span = max(max_span, span)
        if span <= bridge_mm:
            bridge += area
        else:
            ceil += area
    return {"patches": len(groups), "bridge_cm2": round(bridge/100, 1),
            "ceil_cm2": round(ceil/100, 1), "max_span": round(max_span, 1)}


def thin_walls(tris: list, soft: float = WALL_SOFT_MM,
               max_samples: int = 4000) -> dict:
    """Do THANH MONG bang ray-cast mau: tu trong tam mat ban tia nguoc normal,
    gap mat doi dien gan hon `soft` mm -> thanh mong (Moller-Trumbore, hash o 2mm).

    Heuristic lay mau (khong quet 100% mat) — du de canh bao, khong thay duoc CAD.
    """
    n = len(tris)
    step = max(1, n // max_samples)
    cell = 2.0
    grid = {}
    pre = []
    for i, (p, q, r) in enumerate(tris):
        ux, uy, uz = q[0]-p[0], q[1]-p[1], q[2]-p[2]
        vx, vy, vz = r[0]-p[0], r[1]-p[1], r[2]-p[2]
        nx, ny, nz = uy*vz-uz*vy, uz*vx-ux*vz, ux*vy-uy*vx
        L = math.sqrt(nx*nx+ny*ny+nz*nz)
        if not L:
            pre.append(None); continue
        cx, cy, cz = (p[0]+q[0]+r[0])/3, (p[1]+q[1]+r[1])/3, (p[2]+q[2]+r[2])/3
        pre.append((L/2, nx/L, ny/L, nz/L, cx, cy, cz))
        grid.setdefault((int(cx//cell), int(cy//cell), int(cz//cell)), []).append(i)

    def hit_dist(i):
        ar, nx, ny, nz, cx, cy, cz = pre[i]
        dx, dy, dz = -nx, -ny, -nz
        ck = (int(cx//cell), int(cy//cell), int(cz//cell))
        best = None
        for ox in (-1, 0, 1):
            for oy in (-1, 0, 1):
                for oz in (-1, 0, 1):
                    for j in grid.get((ck[0]+ox, ck[1]+oy, ck[2]+oz), ()):
                        if j == i or pre[j] is None:
                            continue
                        if pre[j][1]*nx + pre[j][2]*ny + pre[j][3]*nz > -0.6:
                            continue           # can mat DOI DIEN gan song song (normal nguoc chieu ro rang)
                        p2, q2, r2 = tris[j]
                        e1 = (q2[0]-p2[0], q2[1]-p2[1], q2[2]-p2[2])
                        e2 = (r2[0]-p2[0], r2[1]-p2[1], r2[2]-p2[2])
                        hx, hy, hz = dy*e2[2]-dz*e2[1], dz*e2[0]-dx*e2[2], dx*e2[1]-dy*e2[0]
                        a = e1[0]*hx + e1[1]*hy + e1[2]*hz
                        if abs(a) < 1e-9:
                            continue
                        f = 1.0/a
                        s = (cx-p2[0], cy-p2[1], cz-p2[2])
                        u = f*(s[0]*hx + s[1]*hy + s[2]*hz)
                        if u < 0 or u > 1:
                            continue
                        qv = (s[1]*e1[2]-s[2]*e1[1], s[2]*e1[0]-s[0]*e1[2], s[0]*e1[1]-s[1]*e1[0])
                        v = f*(dx*qv[0] + dy*qv[1] + dz*qv[2])
                        if v < 0 or u+v > 1:
                            continue
                        t = f*(e2[0]*qv[0] + e2[1]*qv[1] + e2[2]*qv[2])
                        # floor 0.3mm: duoi muc nay la tam giac ke grazing / nhieu mesh,
                        # KHONG phai thanh in duoc (1 duong nozzle ~0.4mm la mong nhat that).
                        if 0.3 < t <= soft + 0.1 and (best is None or t < best):
                            best = t
        return best

    thin_n = samp_n = 0
    tmin = None
    for i in range(0, n, step):
        if pre[i] is None:
            continue
        samp_n += 1
        d = hit_dist(i)
        if d is not None:
            thin_n += 1
            tmin = d if tmin is None else min(tmin, d)
    # Bao cao theo TI LE mat mau (khong nhan scale — tranh thoi phong dien tich ao).
    frac = thin_n / samp_n if samp_n else 0.0
    return {"thin_frac": round(frac, 3), "thin_n": thin_n, "sampled": samp_n,
            "min_mm": round(tmin, 2) if tmin else None}


MODES = {
    "fast":     {"label": "Nhanh",    "layer": 0.28, "infill": "8%",  "walls": 2, "outer": None},
    "balanced": {"label": "Cân bằng", "layer": 0.20, "infill": "10%", "walls": 3, "outer": 150},
    "quality":  {"label": "Đẹp",      "layer": 0.16, "infill": "12%", "walls": 3, "outer": 110},
}

# Tag tieng Anh cho ten preset co cau truc: LP-BamBu-A1-<Tag>-<layer>mm-<model>
QUALITY_TAG = {"fast": "Fast", "balanced": "Balanced", "quality": "HighQuality"}


def preset_name(mode: str, lh: float, filament: str = "") -> str:
    """Ten preset chuan: LP-<nhua>-<che do>-<lop>mm.

    Vd: LP-PLA-Lite-Fast-0.28mm. Co TEN NHUA de user biet preset danh cho cuon nao
    (PLA Lite/Matte/Silk khac nhau). KHONG kem ten file model theo yeu cau.
    """
    tag = QUALITY_TAG.get(mode, mode.capitalize())
    # ten nhua -> gon, GIU acronym viet hoa: "PLA LITE" -> "PLA-Lite", "PETG BASIC" -> "PETG-Basic"
    acr = {"PLA", "PETG", "ABS", "ASA", "TPU", "PVA", "PC", "PA", "PET", "HIPS", "PCTG", "PP", "CF", "GF"}
    words = [w for w in re.split(r"[^A-Za-z0-9]+", filament or "PLA") if w]
    fil = "-".join(w.upper() if w.upper() in acr else w.capitalize() for w in words)[:24] or "PLA"
    return f"LP-{fil}-{tag}-{lh:g}mm"


# Vi tri MOI khoa preset trong giao dien Bambu Studio: (tab, section, nhan tieng Anh).
# Tab = Quality/Strength/Speed/Support/Others. Muc dich: hub chi ro "chinh o dau" de
# user hoc + nho, doc duoc TRUOC khi xuat JSON. Nhan tieng Anh = nguyen van tren UI 2.x.
BS_LOC = {
    "layer_height":                   ("Quality",  "Layer height",       "Layer height"),
    "initial_layer_print_height":     ("Quality",  "Layer height",       "Initial layer height"),
    "top_surface_line_width":         ("Quality",  "Line width",         "Top surface"),
    "seam_position":                  ("Quality",  "Seam",               "Seam position"),
    "seam_slope_type":                ("Quality",  "Seam",               "Scarf seam type"),
    "seam_gap":                       ("Quality",  "Seam",               "Seam gap"),
    "resolution":                     ("Quality",  "Precision",          "Resolution"),
    "enable_arc_fitting":             ("Quality",  "Precision",          "Arc fitting"),
    "ironing_type":                   ("Quality",  "Ironing",            "Ironing Type"),
    "wall_generator":                 ("Quality",  "Wall generator",     "Wall generator"),
    "wall_sequence":                  ("Quality",  "Advanced",           "Order of walls"),
    "bridge_flow":                    ("Quality",  "Advanced",           "Bridge flow"),
    "bridge_speed":                   ("Speed",    "Other layers speed", "Bridge"),
    "wall_loops":                     ("Strength", "Walls",              "Wall loops"),
    "top_shell_layers":               ("Strength", "Top/bottom shells",  "Top shell layers"),
    "top_shell_thickness":            ("Strength", "Top/bottom shells",  "Top shell thickness"),
    "bottom_shell_layers":            ("Strength", "Top/bottom shells",  "Bottom shell layers"),
    "top_surface_pattern":            ("Strength", "Top/bottom shells",  "Top surface pattern"),
    "sparse_infill_density":          ("Strength", "Sparse infill",      "Sparse infill density"),
    "sparse_infill_pattern":          ("Strength", "Sparse infill",      "Sparse infill pattern"),
    "infill_wall_overlap":            ("Strength", "Advanced",           "Infill/Wall overlap"),
    "outer_wall_speed":               ("Speed",    "Other layers speed", "Outer wall"),
    "inner_wall_speed":               ("Speed",    "Other layers speed", "Inner wall"),
    "sparse_infill_speed":            ("Speed",    "Other layers speed", "Sparse infill"),
    "internal_solid_infill_speed":    ("Speed",    "Other layers speed", "Internal solid infill"),
    "top_surface_speed":              ("Speed",    "Other layers speed", "Top surface"),
    "initial_layer_speed":            ("Speed",    "Initial layer speed","Initial layer"),
    "enable_overhang_speed":          ("Speed",    "Other layers speed", "Slow down for overhangs"),
    "overhang_1_4_speed":             ("Speed",    "Overhang speed",     "Overhang speed 10-25%"),
    "overhang_2_4_speed":             ("Speed",    "Overhang speed",     "Overhang speed 25-50%"),
    "overhang_3_4_speed":             ("Speed",    "Overhang speed",     "Overhang speed 50-75%"),
    "overhang_4_4_speed":             ("Speed",    "Overhang speed",     "Overhang speed 75-100%"),
    "overhang_totally_speed":         ("Speed",    "Overhang speed",     "Overhang speed 100%"),
    "enable_support":                 ("Support",  "Support",            "Enable support"),
    "support_type":                   ("Support",  "Support",            "Type"),
    "support_style":                  ("Support",  "Support",            "Style"),
    "support_threshold_angle":        ("Support",  "Support",            "Threshold angle"),
    "support_on_build_plate_only":    ("Support",  "Support",            "On build plate only"),
    "support_interface_filament":     ("Support",  "Support filament",   "Support/raft interface"),
    "support_top_z_distance":         ("Support",  "Advanced",           "Top Z distance"),
    "support_bottom_z_distance":      ("Support",  "Advanced",           "Bottom Z distance"),
    "support_interface_spacing":      ("Support",  "Advanced",           "Top interface spacing"),
    "support_interface_pattern":      ("Support",  "Advanced",           "Interface pattern"),
    "independent_support_layer_height": ("Support","Advanced",           "Independent support layer height"),
    "brim_type":                      ("Others",   "Bed adhension",       "Brim type"),
    "brim_width":                     ("Others",   "Bed adhension",       "Brim width"),
    "brim_object_gap":                ("Others",   "Bed adhension",       "Brim-object gap"),
    "skirt_loops":                    ("Others",   "Bed adhension",       "Skirt loops"),
    # draft_shield: co trong PrintConfig nhung dong UI bi comment-out o MOI ban Tab.cpp
    # -> user KHONG chinh duoc tren giao dien, CHI set qua preset JSON (hub tu ghi).
    "draft_shield":                   ("Others",   "Bed adhension (ẩn — chỉ preset)", "Draft shield"),
}
TAB_ORDER = ("Quality", "Strength", "Speed", "Support", "Others")


def _guide_reason(key: str, val: str, r: dict, lh: float = 0.2) -> str:
    """Giai thich NGAN cho tung dong guide — TU CONG SINH theo so lieu model.

    Khong phai text co dinh: rut tu mesh/faces/flow/bridges cua chinh file dang xem.
    """
    m = r.get("mesh") or {}
    fa = r.get("faces") or {}
    fl = r.get("flow") or {}
    br = r.get("bridges") or {}
    h = m.get("height") or 0
    bed = m.get("bed_cm2") or 0
    ov = m.get("overhang_cm2") or 0
    bridge = br.get("bridge_cm2") or 0
    eff = max(0.0, ov - bridge)
    flat = int((fa.get("flat_ratio") or 0) * 100)
    nz = fl.get("nozzle") or 0.4
    R = {
        "layer_height": lambda: f"{val}mm → ~{int(h/float(val))} lớp" if h and float(val) else f"{val}mm theo chế độ",
        "initial_layer_print_height": lambda: f"lớp đầu dày {val}mm: đáy nhỏ/tỉ lệ lật cao → bám chắc hơn",
        "top_surface_line_width": lambda: f"hẹp {val} (mặc định {round(nz*1.05,2)}) → nhét kín khe, hết lấm tấm/vân thưa mặt trên",
        "seam_position": lambda: (f"model dạng hộp (phẳng {flat}%, {fa.get('n_dirs')} hướng) → dồn mối nối ra sau"
                                  if val == "back" else f"mặt cong (phẳng {flat}%) → rải đều + scarf"),
        "seam_slope_type": lambda: "vát mối nối trên mặt cong" if val == "all" else "không vát (model góc cạnh)",
        "seam_gap": lambda: "10% khi Flow/PA đã chuẩn (wiki Bambu)",
        "resolution": lambda: f"{val}mm mịn hơn mặc định 0.01 → biên cong nét hơn",
        "enable_arc_fitting": lambda: "bật → biên cong chạy G2/G3 liền mạch, hết facet",
        "ironing_type": lambda: (f"ủi mặt trên: {fa.get('top_flat_cm2')}cm² phẳng hướng lên"
                                 if val == "top" else "không ủi (mặt phẳng trên nhỏ / không phải chế độ Đẹp)"),
        "wall_generator": lambda: "Arachne: đường biến thiên độ rộng → nhét góc nhọn, chi tiết nhỏ",
        "bridge_flow": lambda: f"{val} (mặc định 1.0): sợi bắc cầu nở ra dính nhau → bridge/overhang mịn không cần support + lấp internal bridge (wiki Bambu, PLA 1.4-1.7)",
        "bridge_speed": lambda: f"{val} mm/s chậm: sợi bắc cầu kịp nguội, bớt võng (wiki Bambu)",
        "enable_overhang_speed": lambda: "BẬT: đường hẫng >45° tự hạ tốc → mặt hẫng mịn không cần support (kể cả chế độ Nhanh)",
        "overhang_1_4_speed": lambda: f"{val} mm/s (hẫng 10-25%): 0 = không hãm, gần như không hẫng",
        "overhang_2_4_speed": lambda: f"{val} mm/s (hẫng 25-50%)",
        "overhang_3_4_speed": lambda: f"{val} mm/s (hẫng 50-75%): chậm cho sợi bám",
        "overhang_4_4_speed": lambda: f"{val} mm/s (hẫng 75-100%): rất chậm, chống võng",
        "overhang_totally_speed": lambda: f"{val} mm/s (hẫng 100% ~ bridge)",
        "wall_sequence": lambda: ("≥3 thành → sandwich: ngoài kẹp giữa (seam gọn + kích thước chuẩn)"
                                  if "inner-outer-inner" in val else "2 thành → inner/outer"),
        "wall_loops": lambda: f"{val} thành theo chế độ",
        "top_shell_layers": lambda: f"{val} lớp ≈ {float(val)*lh:.2f}mm ≥1mm → chống pillowing/lỗ mặt trên",
        "top_shell_thickness": lambda: "chốt chặn 1mm: slicer tự thêm lớp nếu mỏng hơn",
        "bottom_shell_layers": lambda: f"{val} lớp đáy ≈ 0.8mm kín đáy",
        "top_surface_pattern": lambda: "monotonic line: đường song song đều → mặt trên mịn nhất",
        "sparse_infill_density": lambda: f"{val} theo chế độ (đủ đỡ mặt trên, ít nhựa)",
        "sparse_infill_pattern": lambda: ("Gyroid: đều mọi hướng, đẹp nếu lộ" if val == "gyroid"
                                          else "Adaptive Cubic: dày gần vỏ, thưa giữa → nhanh"),
        "infill_wall_overlap": lambda: "25% chống hở giữa ruột và vỏ (wiki)",
        "outer_wall_speed": lambda: f"{val} mm/s: chậm hơn để mặt ngoài mịn",
        "inner_wall_speed": lambda: (f"{val} mm/s ≈ trần lưu lượng {fl.get('v_max')} (nhựa {fl.get('mvs')}mm³/s ở layer {lh}mm)"
                                     if fl.get('v_max') else f"{val} mm/s"),
        "sparse_infill_speed": lambda: f"{val} mm/s (bám trần lưu lượng)",
        "internal_solid_infill_speed": lambda: f"{val} mm/s (bám trần lưu lượng)",
        "top_surface_speed": lambda: f"{val} mm/s: chậm ở mặt trên cho mịn, kín khe",
        "initial_layer_speed": lambda: "50 mm/s chuẩn A1 (PEI nhám + input shaping); hạ xuống chỉ lâu hơn",
        "enable_support": lambda: (f"{eff:.1f}cm² hẫng cần đỡ thật (đã trừ {bridge}cm² khe bridge được)" if val == "1"
                                   else f"chỉ {eff:.1f}cm² hẫng thật sau khi trừ khe → bắc cầu được, khỏi support"),
        "support_type": lambda: (f"model phẳng {flat}% → giàn giáo NORMAL đỡ đều" if "normal" in val
                                 else "model cong/chi tiết → cây TREE chạm điểm, ít sẹo"),
        "support_style": lambda: (f"tree_strong: cao {h:.0f}mm nhánh to khỏi lắc" if val == "tree_strong"
                                  else val),
        "support_threshold_angle": lambda: f"{val}°: dốc hơn góc này tự đỡ ({'ABS/ASA nguội chậm nâng 40' if val=='40' else 'default Bambu, PrintConfig.cpp'})",
        "support_on_build_plate_only": lambda: "chỉ chống từ bàn, không tì lên thân (khỏi seo)",
        "support_interface_filament": lambda: f"nhựa khe {val} làm lớp tiếp giáp (dễ bóc)",
        "support_top_z_distance": lambda: ("0: khác nhựa (PLA-PETG không dính) → khít vẫn bóc, mặt dưới bóng"
                                           if val == "0" else f"{val}mm: cùng nhựa phải chừa khe mới bóc được"),
        "support_bottom_z_distance": lambda: f"{val}mm khe đáy support",
        "support_interface_spacing": lambda: ("0: interface đặc (khác nhựa)" if val == "0" else f"{val}mm giãn cách interface"),
        "support_interface_pattern": lambda: "Rectilinear Interlaced: dễ tách",
        "independent_support_layer_height": lambda: "0: support cùng layer height với model",
        "brim_type": lambda: ("không brim: đáy rộng, tỉ lệ lật an toàn" if val == "no_brim"
                              else f"brim viền ngoài neo mép (đáy {bed}cm²)"),
        "brim_object_gap": lambda: f"{val}mm khe brim-model: nhỏ=bám chắc, lớn=dễ gỡ (0.1 cân bằng; 0.2-0.4 dễ tách)",
        "brim_width": lambda: (f"{val}mm neo mép (giá đo thật ~+{'3.4' if val=='8' else '1.9'}% thời gian)"
                               if val != "0" else "0: không cần brim"),
        "skirt_loops": lambda: ("0: A1 tự mồi bằng purge line" if val == "0" else f"{val} vòng skirt (đi kèm draft shield chắn gió)"),
        "draft_shield": lambda: "tường chắn gió (ABS/ASA co ngót) — Bambu ẩn UI, chỉ preset set được",
    }
    fn = R.get(key)
    try:
        return fn() if fn else ""
    except Exception:      # noqa: BLE001 — reason chi de doc, loi thi bo trong
        return ""


def config_guide(preset: dict, r: dict | None = None) -> list:
    """Nhom cac khoa preset theo TAB Bambu Studio, kem nhan tieng Anh + gia tri
    + GIAI THICH tu cong sinh theo so lieu (cot 'why').

    De web hien 'clone' tung muc cau hinh giong cac tab trong Studio — user doc
    va biet chinh o dau + TAI SAO TRUOC khi xuat JSON. Bo qua khoa ky thuat.
    """
    r = r or {}
    try:
        lh = float(preset.get("layer_height") or 0.2)
    except (TypeError, ValueError):
        lh = 0.2
    skip = {"from", "inherits", "name", "print_settings_id", "version",
            "print_extruder_id", "print_extruder_variant"}
    groups = {t: [] for t in TAB_ORDER}
    extra = []
    for k, v in preset.items():
        if k in skip:
            continue
        val = v[0] if isinstance(v, list) else v
        why = _guide_reason(k, str(val), r, lh)
        loc = BS_LOC.get(k)
        if loc:
            tab, section, en = loc
            groups[tab].append({"key": k, "en": en, "section": section, "value": str(val), "why": why})
        else:
            extra.append({"key": k, "en": k, "section": "Khác", "value": str(val), "why": why})
    out = []
    for tab in TAB_ORDER:
        items = sorted(groups[tab], key=lambda x: x["section"])
        if items:
            out.append({"tab": tab, "items": items})
    if extra:
        out.append({"tab": "Khác (chưa map)", "items": extra})
    return out


def make_preset(r: dict, name: str = "OPT", mode: str = "balanced",
                emit_tips: bool = True) -> dict:
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
    # ten nhua: khay AMS THAT (slot 1) > khai bao trong file > mac dinh PLA
    _ams0 = (r.get("ams") or [None])[0]
    _cft = ((r.get("config") or {}).get("filament_type") or [None])[0]
    pname = preset_name(mode, lh, filament=_ams0 or _cft or "PLA")
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
        # Thanh ngoai + mat tren CUNG phai <= tran (safe) — neu khong la so ao het,
        # dung mat NHIN THAY nhieu nhat. Truoc day set cung 150/110 co the vuot vmax.
        outer = min(M["outer"] or min(safe, 180), safe)
        p["outer_wall_speed"] = [str(outer)]
        p["top_surface_speed"] = [str(min(outer, 150, safe))]
        why.append(f"Tốc độ ≤{safe} mm/s: ở layer {lh}mm, nhựa {mvs} mm³/s chỉ cho tối đa "
                   f"{vmax} mm/s. Đặt cao hơn là số ảo — máy tự hãm."
                   + (f" Thành ngoài {outer} để mặt mịn." if M["outer"] else
                      " Thành ngoài cũng chạy hết tốc (ưu tiên nhanh)."))

    # Nhua than in — dung cho threshold support (3), interface (3b), brim/draft (4)
    ft = [str(t).upper() for t in ((r.get("config") or {}).get("filament_type") or [])]
    body = ft[0] if ft else ""
    # filament_type Bambu KHONG co space, dung DAU GACH: ABS-GF, ASA-CF, PLA-CF...
    # -> tach theo "-" de bat ca dong soi gia cuong (de venh nhat tren A1 khung ho).
    fam = body.split("-")[0] if body else ""
    warpy = fam in ("ABS", "ASA")
    # BRIM-PRONE (wiki Bambu auto-brim): nhua ung suat nhiet cao can brim RONG hon —
    # ABS/ASA/PC/PA + moi loai soi gia cuong CF/GF (PLA-CF, PET-CF, PA-CF...). TPU thi
    # NGUOC lai (brim hep). warpy chi dung cho draft_shield (rieng ABS/ASA khung ho).
    brim_prone = warpy or fam in ("PC", "PA", "PET") or "CF" in body or "GF" in body

    # 3) SUPPORT — tu nhan dinh theo dien tich hang THAT, khong theo cam tinh
    ov = m.get("overhang_pct", 0)
    ov_cm2 = m.get("overhang_cm2", 0)
    br = r.get("bridges") or {}
    bridge_cm2 = br.get("bridge_cm2", 0)
    # LO/KHE DUC TREN SHELL: tran patch span <= 10mm la BRIDGE — A1 bac cau khong can
    # support (Hydra Research design rules) -> TRU khoi dien tich hang truoc khi quyet.
    eff_cm2 = max(0.0, ov_cm2 - bridge_cm2)
    if bridge_cm2 >= 0.5:
        why.append(f"Lỗ/khe đục trên shell: {br.get('patches', 0)} mảng trần, trong đó "
                   f"{bridge_cm2} cm² có nhịp ≤ {BRIDGE_MM:g}mm — A1 BẮC CẦU được, đã TRỪ "
                   f"khỏi diện tích cần support (nguồn: Hydra Research, bridge ≤10mm). "
                   f"Nhịp dài nhất: {br.get('max_span', 0)}mm.")
    if eff_cm2 < 2.0 or ov < 0.5:
        p["enable_support"] = "0"
        why.append(f"TẮT support: {ov_cm2} cm² mặt hẫng >45° nhưng {bridge_cm2} cm² là trần "
                   f"lỗ/khe bridge được → chỉ còn {eff_cm2:.1f} cm² thật sự cần đỡ — quá nhỏ. "
                   f"Tiết kiệm thời gian + nhựa + khỏi gọt.")
    else:
        # KIEU support theo HINH HOC + CHIEU CAO (dong thuan cong dong/forum Bambu):
        #  - Mat hang PHANG (model boxy) -> NORMAL: gian giao do DEU toan mat, be mat
        #    duoi dep; tree nhanh moc lech, cho co cho khong -> vong giua cac nhanh.
        #  - Model cong/chi tiet -> TREE: cham diem, tiet kiem nhua, khong seo mat.
        #  - Cang CAO nhanh tree cang lac -> model cao thi tree_strong (nhanh to).
        p["enable_support"] = "1"
        p["support_on_build_plate_only"] = "1"
        # Threshold = goc nghieng so voi mat NGANG, support khi mat doc DUOI nguong
        # (PrintConfig.cpp:5585). Default Bambu 30 — da tune cho quat A1 + PLA/PETG.
        # ABS/ASA nguoi mat cham (cooling thap) -> vong som hon -> nang 40 do support
        # bat som hon (Raise3D: ha nguong chiu hang cua ABS/ASA ~5-10 do).
        p["support_threshold_angle"] = "40" if warpy else "30"
        why.append(f"Ngưỡng support = {'40' if warpy else '30'}°: mặt dốc hơn góc này so với "
                   f"mặt ngang thì tự đỡ được. 30° là default Bambu tune cho A1"
                   + (f", nâng lên 40° vì {body} nguội chậm, võng sớm hơn PLA." if warpy
                      else " (nguồn: PrintConfig.cpp, default 30)."))
        h_sup = m.get("height") or 0
        if (r.get("faces") or {}).get("flat_ratio", 0) >= 0.5:
            p["support_type"] = "normal(auto)"
            p["support_style"] = "default"
            why.append(f"BẬT support THƯỜNG (giàn giáo đều): {eff_cm2:.1f} cm² hẫng >45° cần đỡ thật ({ov}% tổng) "
                       f"trên model dạng hộp — mặt hẫng PHẲNG cần đỡ ĐỀU toàn mặt; support cây "
                       f"nhánh mọc lệch, chỗ có chỗ không → võng giữa các nhánh, và càng cao "
                       f"càng lắc. Chỉ chống từ mặt bàn (không tì lên thân).")
        else:
            p["support_type"] = "tree(auto)"
            p["support_style"] = "tree_strong" if h_sup > 150 else "tree_hybrid"
            why.append(f"BẬT support CÂY: {eff_cm2:.1f} cm² hẫng >45° cần đỡ thật ({ov}% tổng) trên model "
                       f"cong/chi tiết — tree chạm điểm, ít sẹo mặt, tiết kiệm nhựa. "
                       + (f"Model cao {h_sup:.0f}mm → dùng tree_strong (nhánh to, khỏi lắc). "
                          if h_sup > 150 else "")
                       + "Chỉ chống từ mặt bàn (không tì lên thân).")

    # 3b) SUPPORT INTERFACE — cai san LUON, ke ca khi support dang TAT: cac o nay chi
    #     co tac dung khi support bat, nen de san gia tri dung de user bat support tay
    #     trong Studio la an ngay (khong phai chinh 5 o). Trick: PLA-PETG khong dinh
    #     nhau ve hoa hoc -> interface bang nhua doi ung thi Z distance = 0 van boc roi.
    #     Luu y: cac o nay chi HIEN trong Studio khi bat toggle Advanced (gia tri van an).
    sup_on = p["enable_support"] == "1"
    partner = {"PLA": "PETG", "PETG": "PLA"}.get(fam)
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
        # (slot 1 — than in luon la filament dau tien) + khe ho an toan 0.2 (0 la dinh chet).
        body_slot = 1
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
    #    DAY BO CONG/VAT: bam ban < ~80% footprint nghia la mep ngoai day KHONG cham
    #    ban (fillet/vat) — lop 1-2 o mep la dai mong in ho tren khong -> xu, bong,
    #    keo soi. Case nay BAT BUOC brim de neo mep, du ti le lat an toan.
    dims = m.get("dims") or []
    foot = (dims[0] * dims[1] / 100) if len(dims) >= 2 and dims[0] and dims[1] else 0
    bed_frac = min(bed / foot, 1.0) if foot else 1.0   # cap 1.0: mat cham co the > bbox do artifact do
    rounded_base = bed_frac < 0.8
    #    Yeu to VAT LIEU (Simplify3D/Xometry): ABS/ASA co ngot manh -> venh mep du day
    #    rong, van can brim. PLA/PETG tren PEI nham thi theo hinh hoc thuan tuy.
    if rounded_base and bed >= 8:
        p["brim_type"] = "outer_only"
        p["brim_width"] = "5"
        why.append(f"Brim 5mm (đáy BO CONG/VÁT): chỉ {int(bed_frac*100)}% footprint chạm bàn "
                   f"({bed} cm² / {foot:.0f} cm²) — mép ngoài đáy cong hớt lên, lớp 1-2 ở mép "
                   f"là dải mỏng in hờ → xù mép, bong, kéo sợi. Brim neo mép cong xuống bàn "f"(giá đo thật: +1.9% thời gian, +1.9% nhựa — quá rẻ so với hỏng lớp đầu). "
                   f"Triệt để hơn: úp mặt đáy phẳng nhất xuống bàn khi sắp xếp.")
    elif bed >= 20 and ratio <= 3 and not brim_prone:
        p["brim_type"] = "no_brim"
        p["brim_width"] = "0"
        why.append(f"KHÔNG brim: đáy rộng {bed} cm² (cạnh ~{side:.0f}mm) so với cao {h_mm}mm "
                   f"→ tỉ lệ lật {ratio:.1f} (an toàn <3), đáy chạm bàn {int(bed_frac*100)}% (phẳng, "
                   f"không bo cong) + nhựa không co ngót. Brim chỉ tốn thời gian và phải gọt via. "
                   f"⚠️ NHƯNG no-brim vẫn vênh nếu: bàn dính dầu tay (rửa bàn) HOẶC vài góc nhọn hớt "
                   f"lên (dùng Painted ▸ Brim Ears neo riêng góc — khỏi brim cả vòng).")
    elif bed >= 8 or (brim_prone and ratio <= 3):
        p["brim_type"] = "outer_only"
        p["brim_width"] = "5"
        why.append(f"Brim 5mm: đáy {bed} cm², tỉ lệ lật {ratio:.1f}"
                   + (f" — nhựa {body} ứng suất nhiệt cao/co ngót, dễ vênh mép nên brim dù đáy rộng "
                      f"(wiki Bambu auto-brim: PC/ABS/ASA/CF cần brim rộng hơn)."
                      if brim_prone else " — bám thêm cho chắc (giá đo thật: +1.9% thời gian/nhựa)."))
    else:
        p["brim_type"] = "outer_only"
        p["brim_width"] = "8"
        why.append(f"Brim 8mm (BẮT BUỘC): đáy chỉ {bed} cm², tỉ lệ lật {ratio:.1f} — "
                   f"không brim thì lớp đầu bong / model đổ giữa chừng (giá đo thật brim 8mm: "
                   f"+3.4% thời gian, +3.1% nhựa — rẻ hơn 1 lần in hỏng).")
    # BRIM-OBJECT GAP (wiki Bambu + OrcaSlicer): khe giua brim va model. Nho = bam chac,
    # Lon = DE GO. KHONG ghi de key nay vao preset: mac dinh Bambu da la 0.1mm (can bang),
    # va GHI key qua apply_preset lam Bambu CLI sap khi slice (da kiem chung: co gap ->
    # crash, bo gap -> slice OK 9h04). De user tu chinh trong Studio neu can.
    if p["brim_type"] != "no_brim":
        why.append("Brim-object gap: giữ mặc định 0.1mm của Bambu (cân bằng — đủ dính neo mép, vẫn "
                   "bóc được). Khó gỡ thì TỰ tăng 0.2–0.4mm trong Studio (Others ▸ Bed adhension, dễ "
                   "tách hơn, wiki OrcaSlicer) NHƯNG bám kém đi. Nếu để 0 mà brim vẫn hở → do "
                   "'Elephant foot compensation' đang bật.")
        if emit_tips:
            r["tips"].append(
                "🩹 Brim khó gỡ / để lại via mép? (1) Tăng Brim-object gap lên 0.2–0.4mm (Others ▸ Bed "
                "adhension) — dễ tách hơn. (2) Chỉ vài GÓC NHỌN bị vênh: dùng 'Painted' + Brim Ears (sơn "
                "tai brim tại góc) → neo đúng chỗ, gỡ cực dễ, khỏi brim cả vòng (wiki Bambu). (3) Đế bo "
                "cong: cách triệt để nhất vẫn là úp mặt phẳng nhất xuống bàn thay vì phủ brim.")
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

    # 5b) MAT TREN LẤM TẤM / LỖ LI TI / VÂN THƯA — dong thuan forum Bambu (thread
    #     "Top surface has tiny holes and gaps", 14.7k views): thu pham la duong in
    #     tron dau, cac khuc queo + dau mut de lai khe. Bo cach ha theo thu tu tac dong:
    #       1. bề rộng đường mặt trên hẹp lại (0.25 cho nozzle 0.4) — de nhet kin khe
    #       2. monotonic line (da bat) + Arachne (da bat: bien thien do rong nhet goc nhon)
    #       3. cham lai o mat tren (da co: top_surface_speed <= 150)
    #       4. hieu chinh Flow + PA cho tung cuon (KHONG phai key preset — phai calib that)
    nz = fl.get("nozzle") or 0.4
    narrow = round(nz * 0.62, 2)           # ~0.25 cho nozzle 0.4 (forum: 0.25/0.4)
    # RANG BUOC: duong in KHONG duoc HEP hon chieu cao lop (bead vuong) — neu khong
    # Bambu bao "incorrect slicing parameters" (return_code -51). O che do Nhanh
    # (layer 0.28) 0.25 < 0.28 -> vo hieu; giu mac dinh. Chi hep khi van >= layer.
    if narrow >= lh:
        tslw = narrow
        p["top_surface_line_width"] = str(tslw)
        why.append(f"Mặt trên đường in HẸP {tslw}mm (mặc định {round(nz*1.05,2)}mm): fix lấm tấm / "
                   f"lỗ li ti / vân thưa — đường mảnh nhét kín khe ở khúc queo và đầu mút, kết hợp "
                   f"monotonic line + Arachne (đã bật). Nguồn: đồng thuận forum Bambu (thread top "
                   f"surface tiny holes). Root cause thật là chưa hiệu chỉnh Flow/PA — xem tip.")
    else:
        why.append(f"Mặt trên giữ đường in mặc định (~{round(nz*1.05,2)}mm): chế độ này layer {lh}mm "
                   f"CAO hơn mức hẹp {narrow}mm, không thu hẹp được (đường in phải ≥ chiều cao lớp, "
                   f"nếu không Bambu báo lỗi tham số). Mặt trên mịn hơn thì dùng chế độ Cân bằng/Đẹp "
                   f"(layer ≤0.20mm) để hẹp đường về {narrow}mm.")
    if emit_tips:      # chi emit o lan EXPORT chinh — make_preset goi 4 lan (export+3 mode)
        r["tips"].append(
            "🔧 Mặt trên còn lấm tấm sau khi in? Nguyên nhân GỐC thường là dòng chảy chưa chuẩn — "
            "chạy Calibration ▸ Flow Dynamics (PA) + Flow Rate cho ĐÚNG cuộn nhựa đang dùng (mỗi "
            "cuộn/màu một giá trị). Preset chỉ giảm được lỗ; calib mới hết hẳn (forum Bambu). "
            "Muốn phẳng bóng tuyệt đối: bật Ironing = 'Top surfaces' (đánh đổi thêm thời gian).")

    # 5c) BRIDGE — dong thuan wiki chinh thuc Bambu (wiki.bambulab.com/.../parameter/bridge,
    #     dua tren thi nghiem "unsupported bridge" cua Make Wonderful Things tren MakerWorld):
    #     mac dinh bridge flow 1.0 lam soi bridge tron, KHONG cham nhau -> khe/vong. Nang
    #     flow 1.4-1.7 (PLA) cho soi no ra dinh nhau -> mat bridge min + LAP DAY internal
    #     bridge (lop solid dau tien bac qua ruot thua) = mat tren bot lam tam. Bridge cham
    #     lai cho soi kip nguoi (wiki chot 1.5@40mm/s la can bang tot). Ap MOI che do vi
    #     internal bridge co o moi model co mat tren tren ruot thua.
    # THEO LOAI NHUA — gia tri THANG BAMBU (bridge_flow default 1.0), tra cong dong:
    #   PLA : 1.5  — wiki Bambu (1.4-1.7) + FB maker xac nhan before/after
    #   PETG: 1.05 — FB maker: PETG chay/von cuc khi flow cao -> chi nhich TREN default 1.0
    #   ABS/ASA: 1.0 (GIU mac dinh) — Prusa con GIAM flow cho ABS; bridge ABS kem la do
    #            CO NGOT + lam mat (A1 khung ho), KHONG phai do flow -> tang cooling/giam
    #            toc thay vi tang flow. (Luu y: thang Prusa 0.8 != thang Bambu 1.0.)
    #   Khac/STL khong ro: gia dinh PLA 1.5 + note.
    BFLOW = {"PLA":  ("1.5",  "wiki Bambu 1.4–1.7 + maker xác nhận (thang Bambu, default 1.0)"),
             "PETG": ("1.05", "FB maker: PETG vón cục khi flow cao → chỉ nhích trên default 1.0, TEST 1.0–1.1"),
             "ABS":  ("1.0",  "GIỮ mặc định: ABS bridge kém do co ngót/làm mát chứ không phải flow (Prusa còn giảm); sửa bằng tăng quạt + giảm tốc, TEST"),
             "ASA":  ("1.0",  "GIỮ mặc định: ASA bridge kém do co ngót/làm mát chứ không phải flow; sửa bằng tăng quạt + giảm tốc, TEST")}
    bflow, bnote = BFLOW.get(fam, ("1.5", "giả định PLA (file không khai báo nhựa) — TEST nếu nhựa khác"))
    bspeed = "25" if fam in ("", "PLA", "PETG") else "20"   # nhua co ngot: cham hon chut cho kip nguoi
    p["bridge_flow"] = bflow
    p["bridge_speed"] = [bspeed]
    why.append(f"Bridge flow {bflow} + tốc độ bridge {bspeed} mm/s ({'nhựa '+fam if fam else 'STL — giả định PLA'}): "
               f"flow cao cho sợi bắc cầu nở ra DÍNH NHAU → mặt bridge/overhang mịn KHÔNG cần support, và "
               f"lấp đầy internal bridge (lớp solid bắc qua ruột thưa) → mặt trên bớt lấm tấm; tốc độ chậm "
               f"cho sợi kịp nguội, bớt võng. Cơ sở: {bnote}. Nguồn: wiki chính thức Bambu (thí nghiệm "
               f"unsupported-bridge). Vị trí: Bridge flow → Quality ▸ Advanced; Bridge speed → Speed (dưới Overhang speed).")
    if emit_tips:
        r["tips"].append(
            f"🌉 Bridge flow {bflow} đặt theo nhựa {fam or '(giả định PLA)'} — wiki Bambu CẢNH BÁO: giá trị tốt "
            f"phụ thuộc NHỰA + máy + làm mát, 'chỉnh đại hiếm khi đẹp'. Bridge còn võng/khe? Mở model test "
            f"'Unsupported Bridge Experiments' (MakerWorld), in dải flow 1.4–1.7 (PLA) hoặc 1.1–1.4 (PETG/ABS) "
            f"bằng CHÍNH cuộn nhựa của bạn rồi chọn ô mịn nhất. Bridge dài >10mm vẫn có thể võng dù chỉnh đúng.")

    # 5d) SLOW DOWN FOR OVERHANGS — ep BAT o MOI che do (ke ca Nhanh). Day la cach giu
    #     THAM MY overhang khi in nhanh: THAN in van chay het toc, RIENG duong hang
    #     >45deg tu ha toc theo 4 muc -> mat duoi/doc min ma KHONG can support.
    #     Nguon: wiki chinh thuc Bambu (slow-down-for-overhang) — mac dinh 0/50/30/10/10.
    #     Draft preset (0.28 Extra Draft) co the TAT san de nhanh -> set tuong minh de
    #     Nhanh cung co overhang dep. Gia tri = default Bambu (da chung minh tot).
    #     Muc do hang (%) = ti le be rong soi KHONG duoc lop duoi do (L1/L2), 100% = bridge.
    p["enable_overhang_speed"] = ["1"]
    p["overhang_1_4_speed"] = ["0"]        # 10-25%: gan nhu khong hang -> giu toc (0 = khong ham)
    p["overhang_2_4_speed"] = ["50"]       # 25-50%
    p["overhang_3_4_speed"] = ["30"]       # 50-75%
    p["overhang_4_4_speed"] = ["10"]       # 75-100%
    p["overhang_totally_speed"] = ["10"]   # 100% (hang hoan toan ~ bridge)
    why.append("BẬT 'Slow down for overhangs' + tốc độ hẫng 0/50/30/10/10 mm/s (mặc định Bambu, "
               "wiki xác nhận cho chất lượng tốt hơn hẳn): thân in chạy hết tốc, RIÊNG đường hẫng "
               ">45° tự hạ tốc theo 4 mức độ hẫng → mặt dưới/dốc mịn KHÔNG cần support. Đây là lý do "
               "chế độ Nhanh vẫn giữ được overhang đẹp (chỉ mm/s tổng nhanh, đường hẫng vẫn chậm). "
               "Vị trí: tab Speed ▸ Overhang speed. 0 mm/s ở mức 10-25% = không hãm (gần như không hẫng).")
    if emit_tips:
        r["tips"].append(
            "🪂 Overhang: nếu mặt hẫng vẫn xấu dù đã bật slow-down → (1) model đang bật Arachne nên MẤT "
            "'smooth overhang transition' (nội suy tốc mượt giữa 4 mức — wiki: chỉ có ở wall generator "
            "'classic'), overhang chuyển tốc theo BẬC; đổi Wall generator = Classic nếu ưu tiên mặt hẫng "
            "mượt hơn thin-wall. (2) Hẫng chạm 100% sẽ dùng Bridge speed — chỉnh ở mục Bridge. (3) Cách "
            "chắc nhất cho hẫng lớn vẫn là xoay mặt hẫng lên trên hoặc thêm support.")

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
        if emit_tips:      # scarf o preset process CO THE bi filament preset ghi de am tham
            r["tips"].append(
                "⚠️ Scarf (vát seam) vừa bật ở process — NHƯNG nếu filament preset đang chọn có "
                "'Override filament scarf seam setting' (tab Filament ▸ Advanced) thì nó THẮNG, "
                "scarf bị tắt âm thầm. Kiểm tra ô đó = tắt, hoặc để 'Scarf seam type' của filament "
                "khớp với process.")

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

    # 8b) INFILL THEO KHOI DAC / MONG — infill chi la LOI, thanh + vo moi ganh luc chinh
    #     (Sandwich Panel Theory, Hubs). Do "khoi" bang kich thuoc nho nhat + ti le mong:
    #       - Chi tiet MONG/nho (thanh chiem phan lon) -> infill gan nhu vo nghia, giu thap.
    #       - Khoi DAC lon -> infill la loi chiu luc; van giu thap vi thanh sandwich ganh,
    #         chi tang tay khi chiu luc nang. Bambu auto doi vung ruot <15mm2 thanh dac.
    dims_i = m.get("dims") or []
    min_dim = min([d for d in dims_i if d], default=0)
    thin_frac_i = (r.get("thin") or {}).get("thin_frac", 0)
    if thin_frac_i >= 0.15 or (min_dim and min_dim < 12):
        why.append(f"Ruột giữ {M['infill']} (KHÔNG cần cao): chi tiết mỏng/nhỏ (cạnh nhỏ nhất "
                   f"{min_dim:.0f}mm, {int(thin_frac_i*100)}% bề mặt là thành) → thành + vỏ đã "
                   f"gánh gần hết lực, tăng infill chỉ tốn nhựa + thời gian mà không chắc thêm "
                   f"(Sandwich Panel Theory). Muốn chắc hơn: tăng Wall loops, đừng tăng infill.")
    else:
        why.append(f"Ruột {M['infill']} cho khối đặc (cạnh nhỏ nhất {min_dim:.0f}mm): đây là lõi — "
                   f"thành sandwich vẫn gánh lực chính nên {M['infill']} là đủ cho vật trang trí/"
                   f"thường. CHỊU LỰC NẶNG (bản lề, giá đỡ tải): tự nâng Sparse infill density lên "
                   f"15–25% trong tab Strength; Bambu tự biến vùng ruột <15mm² thành đặc sẵn.")

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
        # Set TUONG MINH = layer height chinh (khong de base preset ke thua quyet dinh)
        # -> JSON xuat ra khop dung voi cau why, khong lech base "0.28 Extra Draft"...
        p["initial_layer_print_height"] = f"{lh:g}"
        why.append(f"Lớp đầu giữ 50 mm/s / {lh:g}mm (chuẩn A1): đáy {bed} cm² bám thoải mái trên "
                   f"bàn PEI nhám. 25 mm/s là số cũ cho máy bàn kính — chỉ chậm thêm chứ "
                   f"không bám thêm.")

    vl = r.get("variable_layer")
    if vl and vl["extra_layers"] > VLH_WARN_LAYERS:
        why.append(f"Gỡ Variable Layer Height: nó đang âm thầm cộng {vl['extra_layers']} lớp "
                   f"(+{vl['extra_pct']}%). Server tự gỡ khi slice — không nhét được vào preset "
                   f"vì nó gắn theo vật thể trong .3mf.")

    return {"preset": p, "why": why, "mode": mode, "mode_label": M["label"],
            "guide": config_guide(p, r)}


def analyze(path: str, mode: str = "balanced", ams: list | None = None,
            color: str | None = None) -> dict:
    """ams: loai nhua THAT trong khay AMS (tu MQTT, vd ['PLA LITE','PETG BASIC']).
    None/[] = khong sync duoc may -> chi suy theo khai bao trong file."""
    r = (analyze_stl(path, color) if path.lower().endswith(".stl")
         else analyze_3mf(path, color))
    r["ams"] = [str(t).upper() for t in (ams or []) if t]
    import os as _os
    nm = _os.path.splitext(_os.path.basename(path))[0][:20]
    r["export"] = make_preset(r, nm, mode)
    # Build preset cho 3 mode (cho E2E/so sanh) NHUNG khong emit tips — tranh trung
    # tip 4 lan vao r["tips"] chung (bug trung du lieu).
    r["presets"] = {k: make_preset(r, nm, k, emit_tips=False) for k in MODES}
    return r


if __name__ == "__main__":
    import sys
    print(json.dumps(analyze(sys.argv[1]), ensure_ascii=False, indent=2))
