#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
analyze_print.py - Phan tich file in Bambu (.3mf / .gcode.3mf / .gcode)
Doc toan bo setting Process + Filament + du bao slice, cham diem & canh bao loi,
xuat bao cao HTML (mo tu dong).

Dung:  python analyze_print.py "duong_dan_file"
Hoac:  keo-tha file vao "Phan-Tich-File-In.bat"
Chi dung thu vien chuan Python - khong can cai them.
"""
import sys, os, json, zipfile, re, html, webbrowser, datetime, math
import xml.etree.ElementTree as ET

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

# ---------------- doc file ----------------
def first(v):
    if isinstance(v, list):
        return v[0] if v else ""
    return v

def load_project_settings(zf):
    for n in zf.namelist():
        if n.lower().endswith("project_settings.config"):
            try:
                return json.loads(zf.read(n).decode("utf-8", "ignore"))
            except Exception:
                return {}
    return {}

def load_slice_info(zf):
    out = {"plates": []}
    for n in zf.namelist():
        if n.lower().endswith("slice_info.config"):
            try:
                root = ET.fromstring(zf.read(n).decode("utf-8", "ignore"))
            except Exception:
                return out
            for plate in root.iter("plate"):
                p = {"meta": {}, "filaments": []}
                for m in plate.findall("metadata"):
                    p["meta"][m.get("key", "")] = m.get("value", "")
                for f in plate.findall("filament"):
                    p["filaments"].append(dict(f.attrib))
                out["plates"].append(p)
    return out

def parse_gcode_config(text):
    """Doc block ; key = value trong gcode (Bambu/Orca)."""
    s = {}
    for line in text.splitlines():
        m = re.match(r"^;\s*([a-zA-Z0-9_\. ]+?)\s*=\s*(.*?)\s*$", line)
        if m:
            k = m.group(1).strip()
            v = m.group(2).strip()
            if k and k not in s:
                s[k] = v
    return s

def gcode_summary(text):
    info = {}
    for pat, key in [
        (r";\s*total estimated time\s*[:=]\s*(.+)", "time"),
        (r";\s*model printing time\s*[:=]\s*(.+)", "time"),
        (r";\s*filament used \[g\]\s*=\s*(.+)", "weight_g"),
        (r";\s*total filament used \[g\]\s*[:=]\s*(.+)", "weight_g"),
        (r";\s*filament used \[mm\]\s*=\s*(.+)", "len_mm"),
        (r";\s*nozzle_diameter\s*[:=]\s*(.+)", "nozzle"),
    ]:
        m = re.search(pat, text, re.I)
        if m and key not in info:
            info[key] = m.group(1).strip()
    return info

def _strip(t):
    return t.split("}")[-1]

def mesh_stats(zf):
    """Tinh THAT tu mesh 3MF: bbox, the tich, dien tich, % mat huong xuong."""
    def parseT(sv):
        if not sv:
            return None
        v = [float(x) for x in sv.split()]
        return v if len(v) == 12 else None
    meshes, comps, builds = {}, {}, []
    for n in zf.namelist():
        if not n.lower().endswith(".model"):
            continue
        try:
            root = ET.fromstring(zf.read(n))
        except Exception:
            continue
        for obj in root.iter():
            if _strip(obj.tag) != "object":
                continue
            oid = obj.get("id"); mesh = None; cl = []
            for ch in obj:
                if _strip(ch.tag) == "mesh":
                    mesh = ch
                elif _strip(ch.tag) == "components":
                    for c in ch:
                        if _strip(c.tag) == "component":
                            cl.append((c.get("objectid"), parseT(c.get("transform"))))
            if mesh is not None:
                vs, ts = [], []
                for e in mesh:
                    if _strip(e.tag) == "vertices":
                        for vv in e:
                            vs.append((float(vv.get("x")), float(vv.get("y")), float(vv.get("z"))))
                    elif _strip(e.tag) == "triangles":
                        for tt in e:
                            ts.append((int(tt.get("v1")), int(tt.get("v2")), int(tt.get("v3"))))
                meshes[oid] = (vs, ts)
            if cl:
                comps[oid] = cl
        for b in root.iter():
            if _strip(b.tag) == "item":
                builds.append((b.get("objectid"), parseT(b.get("transform"))))
    if not meshes:
        return None

    def apply(T, p):
        if not T:
            return p
        x, y, z = p
        return (x*T[0]+y*T[3]+z*T[6]+T[9], x*T[1]+y*T[4]+z*T[7]+T[10], x*T[2]+y*T[5]+z*T[8]+T[11])

    def mul(A, B):
        if not A:
            return B
        if not B:
            return A
        r = [0.0]*12
        for i in range(3):
            for j in range(3):
                r[i*3+j] = A[j]*B[i*3] + A[3+j]*B[i*3+1] + A[6+j]*B[i*3+2]
        for j in range(3):
            r[9+j] = A[j]*B[9] + A[3+j]*B[10] + A[6+j]*B[11] + A[9+j]
        return r

    world = []
    def emit(oid, T, depth=0):
        if depth > 8:
            return
        if oid in meshes:
            vs, ts = meshes[oid]
            wv = [apply(T, v) for v in vs]
            for a, b, c in ts:
                if a < len(wv) and b < len(wv) and c < len(wv):
                    world.append((wv[a], wv[b], wv[c]))
        for cid, ct in comps.get(oid, []):
            emit(cid, mul(T, ct), depth+1)
    obj_dims = []
    for oid, T in builds:
        before = len(world)
        emit(oid, T)
        seg = world[before:]
        if seg:
            sx = [p[0] for tr in seg for p in tr]
            sy = [p[1] for tr in seg for p in tr]
            sz = [p[2] for tr in seg for p in tr]
            obj_dims.append(max(max(sx)-min(sx), max(sy)-min(sy), max(sz)-min(sz)))
    if not world:
        for oid in meshes:
            emit(oid, None)
    if not world:
        return None

    xs, ys, zs = [], [], []
    vol = area = down = top = vert = slope = 0.0
    fpx = fnx = fpy = fny = fpz = fnz = 0.0   # dien tich phang theo 6 huong ±X ±Y ±Z
    cos45 = math.cos(math.radians(45))
    for p1, p2, p3 in world:
        for p in (p1, p2, p3):
            xs.append(p[0]); ys.append(p[1]); zs.append(p[2])
        vol += (p1[0]*(p2[1]*p3[2]-p3[1]*p2[2]) - p1[1]*(p2[0]*p3[2]-p3[0]*p2[2]) + p1[2]*(p2[0]*p3[1]-p3[0]*p2[1]))/6.0
        ux, uy, uz = (p2[0]-p1[0], p2[1]-p1[1], p2[2]-p1[2])
        vx, vy, vz = (p3[0]-p1[0], p3[1]-p1[1], p3[2]-p1[2])
        nx, ny, nz = (uy*vz-uz*vy, uz*vx-ux*vz, ux*vy-uy*vx)
        a = math.sqrt(nx*nx+ny*ny+nz*nz)/2.0
        if a < 1e-9:
            continue
        area += a
        cx, cy, cz = nx/(2*a), ny/(2*a), nz/(2*a)
        if cz > 0.985:
            top += a
        elif cz < -cos45:
            down += a
        elif abs(cz) < 0.15:
            vert += a
        else:
            slope += a
        if cx > 0.966: fpx += a
        elif cx < -0.966: fnx += a
        if cy > 0.966: fpy += a
        elif cy < -0.966: fny += a
        if cz > 0.966: fpz += a
        elif cz < -0.966: fnz += a
    dx = max(xs)-min(xs) if xs else 0
    dy = max(ys)-min(ys) if ys else 0
    dz = max(zs)-min(zs) if zs else 0
    pct = lambda v: (v/area*100 if area else 0.0)
    return {"objects": len(builds) or len(meshes), "tris": len(world),
            "dx": dx, "dy": dy, "dz": dz,
            "vol_cm3": abs(vol)/1000.0, "area_cm2": area/100.0,
            "solid_g": abs(vol)*0.00124,
            "down_ratio": pct(down), "top_ratio": pct(top),
            "vert_ratio": pct(vert), "slope_ratio": pct(slope),
            "aspect": (dz/min(dx, dy) if min(dx, dy) > 0 else 0),
            "n_placed": len(obj_dims) or 1,
            "max_obj_dim": max(obj_dims) if obj_dims else max(dx, dy, dz),
            "flat": {"+X": pct(fpx), "-X": pct(fnx), "+Y": pct(fpy),
                     "-Y": pct(fny), "+Z": pct(fpz), "-Z": pct(fnz)}}

def gcode_toolpath(text):
    """Tinh THAT tu g-code: so lop, max volumetric flow, feed, retract, temp, fan."""
    area = math.pi*(1.75/2.0)**2
    relE = True
    x = y = z = f = 0.0
    e_abs = 0.0
    e_total = maxvol = maxfeed = 0.0
    retr = travel = layers = 0
    ntemp = btemp = fan = 0.0
    for line in text.splitlines():
        ls = line.strip()
        if not ls:
            continue
        if ls.startswith(";"):
            up = ls.upper()
            if "CHANGE_LAYER" in up or up.startswith(";LAYER:") or "LAYER_CHANGE" in up:
                layers += 1
            continue
        head = ls.split(";", 1)[0].strip()
        parts = head.split()
        if not parts:
            continue
        cmd = parts[0].upper()
        vals = {p[0].upper(): p[1:] for p in parts[1:] if len(p) > 1}
        if cmd == "M83":
            relE = True
        elif cmd == "M82":
            relE = False
        elif cmd in ("M104", "M109") and "S" in vals:
            ntemp = max(ntemp, num(vals["S"], 0) or 0)
        elif cmd in ("M140", "M190") and "S" in vals:
            btemp = max(btemp, num(vals["S"], 0) or 0)
        elif cmd == "M106" and "S" in vals:
            fan = max(fan, num(vals["S"], 0) or 0)
        elif cmd in ("G0", "G1"):
            nx = num(vals.get("X"), x) if "X" in vals else x
            ny = num(vals.get("Y"), y) if "Y" in vals else y
            nz = num(vals.get("Z"), z) if "Z" in vals else z
            if "F" in vals:
                f = num(vals["F"], f) or f
            ed = 0.0
            if "E" in vals:
                ev = num(vals["E"], 0) or 0
                if relE:
                    ed = ev
                else:
                    ed = ev - e_abs; e_abs = ev
            dist = math.sqrt((nx-x)**2 + (ny-y)**2 + (nz-z)**2)
            if f/60.0 > maxfeed:
                maxfeed = f/60.0
            if ed > 0:
                e_total += ed
                if dist > 0 and f > 0:
                    t = dist/(f/60.0)
                    if t > 0:
                        maxvol = max(maxvol, ed*area/t)
            elif ed < 0:
                retr += 1
            elif dist > 0:
                travel += 1
            x, y, z = nx, ny, nz
    return {"layers": layers, "z_max": z, "e_total_m": e_total/1000.0,
            "max_vol": maxvol, "max_feed": maxfeed, "retractions": retr, "travels": travel,
            "nozzle_temp": ntemp, "bed_temp": btemp, "fan_pct": round(fan/255*100)}

def read_any(path):
    """Tra ve (settings, slice_info, source, geo, gstats)."""
    low = path.lower()
    if zipfile.is_zipfile(path):
        with zipfile.ZipFile(path) as zf:
            ps = load_project_settings(zf)
            si = load_slice_info(zf)
            try:
                geo = mesh_stats(zf)
            except Exception:
                geo = None
            gtext = None
            for n in zf.namelist():
                if n.lower().endswith(".gcode"):
                    gtext = zf.read(n).decode("utf-8", "ignore"); break
            gstats = None
            if gtext:
                try:
                    gstats = gcode_toolpath(gtext)
                except Exception:
                    gstats = None
            if ps:
                return ps, si, "3mf:project_settings", geo, gstats
            if gtext:
                s = parse_gcode_config(gtext)
                s["__summary__"] = gcode_summary(gtext)
                return s, si, "3mf:gcode", geo, gstats
            return {}, si, "3mf:nodata", geo, gstats
    if low.endswith(".gcode"):
        txt = open(path, encoding="utf-8", errors="ignore").read()
        s = parse_gcode_config(txt)
        s["__summary__"] = gcode_summary(txt)
        gstats = None
        try:
            gstats = gcode_toolpath(txt)
        except Exception:
            gstats = None
        return s, {"plates": []}, "gcode", None, gstats
    raise SystemExit("File khong ho tro. Can .3mf / .gcode.3mf / .gcode")

# ---------------- helpers ----------------
def g(s, *keys, default=""):
    for k in keys:
        if k in s and s[k] not in (None, "", []):
            return first(s[k])
    return default

def num(x, d=None):
    try:
        return float(str(x).replace("%", "").replace("mm/s", "").strip())
    except Exception:
        return d

def material_density(s):
    """Khoi luong rieng (g/cm3) theo loai nhua — nguon: OrcaSlicer-bambulab profiles."""
    name = (g(s, "filament_settings_id", default="") + " " + g(s, "filament_type", default="")).lower()
    if "matte" in name:
        return 1.32
    if "petg" in name:
        return 1.27
    if "abs" in name:
        return 1.04
    if "asa" in name:
        return 1.07
    if "tpu" in name:
        return 1.21
    if "pa" in name or "nylon" in name:
        return 1.15
    return 1.24  # PLA Basic mac dinh

def fmt_time(sec):
    try:
        sec = int(float(sec))
        h, r = divmod(sec, 3600); m, s = divmod(r, 60)
        return (f"{h}h " if h else "") + f"{m}m {s}s"
    except Exception:
        return str(sec)

# ---------------- audit rules ----------------
def audit(s, slice_info):
    F = []  # (level, title, detail)  level: bad/warn/ok/info
    def add(l, t, d): F.append((l, t, d))

    ftype = (g(s, "filament_type") or "").upper()
    nozzle = num(g(s, "nozzle_diameter", default="0.4"), 0.4) or 0.4
    lh = num(g(s, "layer_height"), None)
    ow = num(g(s, "outer_wall_speed"), None)
    walls = num(g(s, "wall_loops"), None)
    infill = num(g(s, "sparse_infill_density"), None)
    flow = num(g(s, "filament_flow_ratio"), None)
    bed_t = num(g(s, "textured_plate_temp", "hot_plate_temp", "cool_plate_temp",
                   "hot_plate_temp_initial_layer"), None)
    noz_t = num(g(s, "nozzle_temperature"), None)
    maxvol = num(g(s, "filament_max_volumetric_speed"), None)
    sup = g(s, "enable_support", default="0")
    sup_thr = num(g(s, "support_threshold_angle"), None)
    sup_z = num(g(s, "support_top_z_distance", "support_object_first_layer_gap"), None)
    brim = g(s, "brim_type", default="")
    n_fil = 0
    try:
        nt = s.get("nozzle_temperature")
        n_fil = len(nt) if isinstance(nt, list) else 1
    except Exception:
        n_fil = 1

    # layer height vs nozzle
    if lh is not None:
        if lh > 0.75 * nozzle:
            add("warn", "Layer height qua day", f"{lh}mm > 75% nozzle ({nozzle}mm). Lien ket lop kem; giam ve <= {round(0.7*nozzle,2)}mm.")
        elif lh < 0.25 * nozzle:
            add("info", "Layer height rat mong", f"{lh}mm — net cao nhung CHAM. OK cho chi tiet, khong nen cho do thuong.")
        else:
            add("ok", "Layer height hop ly", f"{lh}mm voi nozzle {nozzle}mm (25–75%).")

    # outer wall speed (belt artifact ~120 tren A1)
    if ow is not None:
        if 100 <= ow <= 145:
            add("warn", "Toc do outer wall vung 'van belt'", f"{ow}mm/s nam ~120mm/s — A1 de in ra van song. Giam <100 (mat dep) hoac tang >160.")
        elif ow > 250:
            add("warn", "Outer wall qua nhanh", f"{ow}mm/s — de mat net & rung.")
        else:
            add("ok", "Toc do outer wall on", f"{ow}mm/s.")

    # walls
    if walls is not None:
        if walls <= 1:
            add("warn", "Thanh qua mong", "wall_loops=1 → rat yeu. Do thuong 2, chiu luc 3–5.")
        elif walls >= 6:
            add("info", "Nhieu thanh", f"wall_loops={int(walls)} → ben nhung lau & ton nhua.")
        else:
            add("ok", "So thanh hop ly", f"wall_loops={int(walls)}.")

    # infill
    if infill is not None:
        if infill > 50:
            add("warn", "Infill qua cao", f"{infill}% → de cong venh & ton nhua/thoi gian. It khi can >50%.")
        elif infill < 5:
            add("info", "Infill rat thap", f"{infill}% → nhe, chi cho trang tri.")
        else:
            add("ok", "Infill hop ly", f"{infill}%.")

    # flow ratio (PETG)
    if "PETG" in ftype and flow is not None:
        if 0.93 <= flow <= 0.96:
            add("ok", "Flow ratio PETG dung", f"{flow} (khuyen nghi 0.93–0.96).")
        else:
            add("warn", "Flow ratio PETG lech", f"{flow} — PETG nen 0.93–0.96 (cao hon de un/tac, thap hon thieu nhua).")

    # temperatures sanity
    if "PLA" in ftype and bed_t is not None and bed_t >= 60:
        add("warn", "Bed nong cho PLA (rui ro heat-creep)", f"bed {bed_t}°C — VN nong nen ha ve 45–55°C, mo thoang de tranh tac PLA (HDT 57°C).")
    if "PETG" in ftype and bed_t is not None and bed_t < 60:
        add("warn", "Bed thap cho PETG", f"bed {bed_t}°C — PETG nen 60–80°C de bam & chong cong.")
    if noz_t is not None:
        if "PLA" in ftype and not (190 <= noz_t <= 235):
            add("warn", "Nhiet nozzle PLA bat thuong", f"{noz_t}°C — PLA thuong 190–230°C.")
        if "PETG" in ftype and not (220 <= noz_t <= 265):
            add("warn", "Nhiet nozzle PETG bat thuong", f"{noz_t}°C — PETG thuong 230–260°C.")

    # support
    if str(sup) in ("1", "true", "True"):
        if sup_thr is not None and sup_thr < 15:
            add("info", "Threshold support thap", f"{sup_thr}° → it sinh do (chi cho phan rat doc).")
        if sup_z is not None and sup_z == 0:
            add("info", "Top Z distance = 0", "Chi nen 0 khi dung NHUA DO RIENG. Cung nhua → de 0.2mm cho de go.")
        add("ok", "Support dang BAT", f"threshold={sup_thr}°, topZ={sup_z}mm.")
    else:
        add("info", "Support dang TAT", "Neu mau co phan dua/treo > 45° → can bat support.")

    # PETG warp -> brim
    if "PETG" in ftype and brim in ("", "no_brim", "auto_brim"):
        add("info", "PETG nen co Brim", "PETG de cong goc → bat Brim (outer) + keo.")

    # multi-color prime tower
    if n_fil > 1:
        wt = g(s, "enable_prime_tower", "prime_tower_enable", default="")
        if str(wt) in ("0", "false", "False", ""):
            add("warn", "In nhieu mau nhung chua bat Prime tower", f"{n_fil} filament → can Prime tower de xa mau lan.")
        else:
            add("ok", "Prime tower BAT (da mau)", f"{n_fil} filament.")

    # max volumetric
    if maxvol is not None:
        add("info", "Max volumetric speed", f"{maxvol} mm³/s — tran luu luong (A1 PLA ~21, PETG ~12–16, nozzle 0.2 ~2).")

    # --- Quality: ironing / top surface / wall generator ---
    iron = (g(s, "ironing_type") or "").lower()
    if iron and iron not in ("no ironing", "none", "0", ""):
        add("ok", "Ironing dang BAT", f"'{g(s,'ironing_type')}' — mat tren muot/bong (in cham hon).")
    else:
        add("info", "Ironing dang TAT", "Bat Ironing = 'Top surfaces' neu muon mat tren PHANG BONG (hop mat phang lon, +thoi gian). PLA Matte thuong KHONG can (mat da nham dep).")
    tsp = (g(s, "top_surface_pattern") or "").lower()
    if tsp and "monotonic" not in tsp:
        add("info", "Top surface pattern", f"'{g(s,'top_surface_pattern')}' — dung 'Monotonic' cho mat tren deu & net hon.")
    wg = (g(s, "wall_generator") or "").lower()
    if wg == "classic":
        add("info", "Wall generator = Classic", "Doi 'Arachne' de xu ly thanh bien thien / chi tiet mong tot hon (mac dinh nen Arachne).")

    # --- Order of walls (wall_sequence) ---
    wseq = (g(s, "wall_sequence") or "").lower()
    wl = num(g(s, "wall_loops"), None)
    if wseq:
        if "inner-outer-inner" in wseq or "inner/outer/inner" in wseq:
            add("ok", "Order of walls = Inner/Outer/Inner", "TOI UU NHAT: mat ngoai dep + dung sai chuan + overhang tot (can >=3 wall).")
        elif wseq.startswith("outer") or "outer wall/inner" in wseq or "outer/inner" in wseq:
            add("ok", "Order of walls = Outer/Inner", "Mat ngoai DEP + dung sai chuan; luu y overhang co the hoi sag.")
        else:  # inner/outer (mac dinh)
            if wl and wl >= 3:
                add("warn", "Order of walls = Inner/Outer (chua toi uu mat ngoai)", "Ban co >=3 wall → doi 'Inner/Outer/Inner' de MAT NGOAI DEP hon ma van du overhang; hoac 'Outer/Inner' cho mat dep nhat.")
            else:
                add("info", "Order of walls = Inner/Outer", "Mac dinh (overhang it sag). Muon mat ngoai dep hon → 'Outer/Inner'.")

    # --- First layer (lop dau) ---
    ils = num(g(s, "initial_layer_speed"), None)
    ilh = num(g(s, "initial_layer_print_height"), None)
    if ils is not None:
        if ils > 60:
            add("warn", "Toc do lop 1 qua nhanh", f"{ils}mm/s — lop dau nen ~20–50mm/s de bam ban CHAC (tot nhat 30–50, chi tiet nho 20–30).")
        elif ils <= 50:
            add("ok", "Toc do lop 1 tot", f"{ils}mm/s (≤50 → bam ban tot).")
    if ilh is not None and lh is not None and ilh < lh:
        add("info", "Lop dau mong hon lop thuong", f"initial {ilh} < layer {lh}mm — nen de lop dau DAY BANG hoac >layer (0.2–0.28) de chiu sai so leveling.")

    # --- Filament profile / PLA Matte ---
    fname = g(s, "filament_settings_id") or ""
    if "PLA" in ftype:
        low = fname.lower()
        if "matte" in low:
            add("ok", "Nhua PLA Matte (da nhan dung)", "Matte: mat nham dep, KHONG can ironing; nhung GION hon Basic → lien ket lop yeu hon 1 chut → giu wall ≥3, toc do vua phai, nhiet 210–220°C, fan 100%.")
        elif "basic" in low or "generic" in low:
            add("warn", "Kiem tra dung profile nhua", f"Profile = '{fname}'. Neu spool THUC TE la PLA MATTE (hoac Silk/Wood/CF...), PHAI chon dung profile (vd 'Bambu PLA Matte @BBL A1') — sai profile → flow/nhiet/pressure-advance sai → mat net & sai dung sai.")

    return F

# ---------------- form hien thi kieu Bambu Studio ----------------
BOOL_KEYS = {
    "enable_support", "enable_prime_tower", "is_infill_first", "thick_bridges",
    "only_one_wall_first_layer", "detect_thin_wall", "detect_overhang_wall",
    "support_on_build_plate_only", "spiral_mode", "reduce_crossing_wall",
    "enable_overhang_speed", "smooth_speed_discontinuity_area", "fuzzy_skin",
}

def fmt_field(key, val):
    v = first(val)
    if v in ("", None):
        return ""
    if key in BOOL_KEYS:
        return "ON" if str(v).lower() in ("1", "true", "on") else "OFF"
    return str(v)

# (Tab, mau, [ (Muc con, [ (Ten UI tieng Anh, key/keys, don vi) ]) ]) — bam sat panel Bambu Studio
GROUPS = [
    ("Quality", "#16a34a", [
        ("Layer height", [
            ("Layer height", "layer_height", "mm"),
            ("Initial layer height", "initial_layer_print_height", "mm"),
        ]),
        ("Line width", [
            ("Default", "line_width", "mm"),
            ("Initial layer", "initial_layer_line_width", "mm"),
            ("Outer wall", "outer_wall_line_width", "mm"),
            ("Inner wall", "inner_wall_line_width", "mm"),
            ("Top surface", "top_surface_line_width", "mm"),
            ("Sparse infill", "sparse_infill_line_width", "mm"),
            ("Internal solid infill", "internal_solid_infill_line_width", "mm"),
            ("Support", "support_line_width", "mm"),
        ]),
        ("Seam", [("Seam position", "seam_position", "")]),
        ("Precision", [
            ("Slice gap closing radius", "slice_closing_radius", "mm"),
            ("Resolution", "resolution", "mm"),
            ("XY hole compensation", "xy_hole_compensation", "mm"),
            ("XY contour compensation", "xy_contour_compensation", "mm"),
            ("Elephant foot compensation", "elefant_foot_compensation", "mm"),
        ]),
        ("Ironing", [
            ("Ironing type", "ironing_type", ""),
            ("Ironing speed", "ironing_speed", "mm/s"),
            ("Ironing flow", "ironing_flow", "%"),
            ("Ironing spacing", "ironing_spacing", "mm"),
        ]),
        ("Advanced", [
            ("Wall generator", "wall_generator", ""),
        ]),
    ]),
    ("Strength", "#2563eb", [
        ("Walls", [("Wall loops", "wall_loops", "")]),
        ("Top/Bottom shell", [
            ("Top shell layers", "top_shell_layers", ""),
            ("Top shell thickness", "top_shell_thickness", "mm"),
            ("Bottom shell layers", "bottom_shell_layers", ""),
            ("Bottom shell thickness", "bottom_shell_thickness", "mm"),
        ]),
        ("Infill", [
            ("Sparse infill density", "sparse_infill_density", ""),
            ("Sparse infill pattern", "sparse_infill_pattern", ""),
            ("Top surface pattern", "top_surface_pattern", ""),
            ("Infill/wall overlap", "infill_wall_overlap", "%"),
        ]),
        ("Advanced", [
            ("Order of walls", "wall_sequence", ""),
            ("Print infill first", "is_infill_first", ""),
            ("Bridge flow", "bridge_flow", ""),
            ("Thick bridges", "thick_bridges", ""),
            ("Only one wall on top surfaces", "top_one_wall_type", ""),
            ("Only one wall on first layer", "only_one_wall_first_layer", ""),
        ]),
    ]),
    ("Speed", "#d97706", [
        ("Initial layer speed", [
            ("Initial layer", "initial_layer_speed", "mm/s"),
            ("Initial layer infill", "initial_layer_infill_speed", "mm/s"),
        ]),
        ("Other layers speed", [
            ("Outer wall", "outer_wall_speed", "mm/s"),
            ("Inner wall", "inner_wall_speed", "mm/s"),
            ("Small perimeters", "small_perimeter_speed", ""),
            ("Small perimeter threshold", "small_perimeter_threshold", "mm"),
            ("Sparse infill", "sparse_infill_speed", "mm/s"),
            ("Internal solid infill", "internal_solid_infill_speed", "mm/s"),
            ("Top surface", "top_surface_speed", "mm/s"),
            ("Gap infill", "gap_infill_speed", "mm/s"),
        ]),
        ("Overhang speed", [
            ("Slow down for overhangs", "enable_overhang_speed", ""),
            ("Bridge", "bridge_speed", "mm/s"),
        ]),
        ("Travel speed", [("Travel", "travel_speed", "mm/s")]),
        ("Advanced", [
            ("Smooth speed discontinuity area", "smooth_speed_discontinuity_area", ""),
            ("Smooth coefficient", "smooth_coefficient", ""),
            ("Default acceleration", "default_acceleration", "mm/s²"),
            ("Outer wall acceleration", "outer_wall_acceleration", "mm/s²"),
        ]),
    ]),
    ("Support", "#7c3aed", [
        ("Support", [
            ("Enable support", "enable_support", ""),
            ("Type", "support_type", ""),
            ("Threshold angle", "support_threshold_angle", "°"),
            ("On build plate only", "support_on_build_plate_only", ""),
        ]),
        ("Options", [
            ("Top Z distance", "support_top_z_distance", "mm"),
            ("Bottom Z distance", "support_bottom_z_distance", "mm"),
            ("Base pattern", "support_base_pattern", ""),
            ("Top interface layers", "support_interface_top_layers", ""),
            ("Support/object XY", "support_object_xy_distance", "mm"),
        ]),
    ]),
    ("Others", "#0891b2", [
        ("Skirt / Brim", [
            ("Skirt loops", "skirt_loops", ""),
            ("Brim type", "brim_type", ""),
            ("Brim width", "brim_width", "mm"),
            ("Brim object gap", "brim_object_gap", "mm"),
        ]),
        ("Prime tower", [
            ("Enable prime tower", "enable_prime_tower", ""),
            ("Prime tower width", "prime_tower_width", "mm"),
        ]),
        ("Special", [
            ("Fuzzy skin", "fuzzy_skin", ""),
            ("Timelapse", "timelapse_type", ""),
            ("Print sequence", "print_sequence", ""),
            ("Spiral vase", "spiral_mode", ""),
        ]),
    ]),
    ("Filament", "#db2777", [
        ("Material", [
            ("Type", "filament_type", ""),
            ("Profile", "filament_settings_id", ""),
        ]),
        ("Temperature", [
            ("Nozzle (other layers)", "nozzle_temperature", "°C"),
            ("Nozzle (initial layer)", "nozzle_temperature_initial_layer", "°C"),
            ("Bed (textured PEI)", ("textured_plate_temp", "hot_plate_temp"), "°C"),
        ]),
        ("Flow & cooling", [
            ("Flow ratio", "filament_flow_ratio", ""),
            ("Max volumetric speed", "filament_max_volumetric_speed", "mm³/s"),
            ("Fan max speed", "fan_max_speed", "%"),
            ("Fan off first N layers", "close_fan_the_first_x_layers", ""),
        ]),
    ]),
]

LV = {
    "bad":  ("#dc2626", "LOI"),
    "warn": ("#d97706", "CANH BAO"),
    "ok":   ("#16a34a", "OK"),
    "info": ("#2563eb", "INFO"),
}

# Huong dan dieu chinh tung setting (tieng Viet co dau) — key = config key
GUIDE = {
    # Quality
    "layer_height": "KN 0.20mm · ↓0.08–0.12 = nét/mịn hơn nhưng chậm · ↑0.28 = nhanh, thô",
    "initial_layer_print_height": "KN 0.20–0.25 · ↑ dày = bám bàn tốt hơn · đừng để < layer height",
    "line_width": "≈1.05–1.1× nozzle · ↑ = bám/bền hơn, mất nét · ↓ = nét hơn",
    "initial_layer_line_width": "KN 0.50 · ↑ = 'squish' nhiều → bám lớp 1 tốt",
    "outer_wall_line_width": "KN 0.42 · ↓ = mặt ngoài nét hơn",
    "inner_wall_line_width": "KN 0.45 · ↑ = liên kết bền hơn",
    "seam_position": "Aligned = giấu 1 cột · Nearest = ngắn nhất · TRÁNH đặt ở overhang",
    "wall_generator": "KN Arachne (thành biến thiên mượt) · Classic cho vase mode",
    "ironing_type": "Mặc định No ironing · bật 'All/Topmost top surfaces' nếu cần mặt trên phẳng bóng",
    "ironing_speed": "↓ = mịn hơn (KN 15–30)",
    "ironing_flow": "↑ = tràn · ↓ = không mịn (KN 10–20%)",
    "ironing_spacing": "Nên NHỎ hơn ⌀nozzle (KN 0.10–0.15)",
    # Strength
    "wall_loops": "KN 2–3 · ↑4–5 = BỀN hơn (đồ chịu lực) · ↓ = nhanh, yếu",
    "top_shell_layers": "KN 4–5 · ↑ = mặt trên kín & phẳng hơn",
    "bottom_shell_layers": "KN 3–4 · ↑ = đáy kín hơn",
    "sparse_infill_density": "KN 15% · ↑25–40 = bền/nặng/chậm · ↓ = nhẹ/nhanh · TRÁNH >50 (cong vênh)",
    "sparse_infill_pattern": "Gyroid = đều mọi hướng (bền) · Grid = nhanh",
    "top_surface_pattern": "Monotonic = mặt trên đều & đẹp nhất",
    "infill_wall_overlap": "↑ = ruột–thành dính chắc hơn",
    "wall_sequence": "Inner/Outer = overhang ít sag · Outer/Inner = mặt NGOÀI đẹp nhất · Inner/Outer/Inner = TỐI ƯU (cần ≥3 wall)",
    "is_infill_first": "Thường TẮT",
    "bridge_flow": "↑ nếu cầu bị hở · ↓ nếu cầu bị xệ/thừa",
    "thick_bridges": "Bật nếu cầu (bridge) xấu",
    "top_one_wall_type": "Chỉ 1 thành ở mặt trên → mịn hơn",
    "only_one_wall_first_layer": "Thường TẮT",
    # Speed
    "initial_layer_speed": "KN 30–50 · ↓30 = bám bàn CHẮC (lớp 1 quyết định) · ↑ dễ bong",
    "initial_layer_infill_speed": "KN 80–105 (ruột lớp 1)",
    "outer_wall_speed": "Mặt đẹp ↓50–120 · TRÁNH ~120 (vân belt) → ≤100 hoặc ≥160 · ↑ nhanh, thô",
    "inner_wall_speed": "↑ = nhanh (không lộ ra ngoài)",
    "small_perimeter_speed": "% · chi tiết nhỏ chạy chậm → nét hơn",
    "small_perimeter_threshold": "0 = auto",
    "sparse_infill_speed": "↑ = nhanh nhưng bị trần Max volumetric",
    "internal_solid_infill_speed": "↑ = nhanh",
    "top_surface_speed": "↓100–150 = mặt trên đẹp hơn · ↑ nhanh",
    "enable_overhang_speed": "BẬT = giảm tốc phần đua → bớt rủ",
    "bridge_speed": "↓ = cầu ít xệ hơn",
    "travel_speed": "↑ = di chuyển nhanh (bớt oozing) · quá cao dễ va",
    "smooth_speed_discontinuity_area": "BẬT = bớt lằn ở chỗ đổi tốc",
    "smooth_coefficient": "PETG bề mặt lồi lõm → ↓ về 0.1",
    "default_acceleration": "↓ = êm/đẹp hơn nhưng chậm · ↑ = nhanh, dễ ringing/rung",
    "outer_wall_acceleration": "↓ = mặt ngoài mịn hơn (bớt rung)",
    # Support
    "enable_support": "Bật khi có mặt đua/treo dốc > threshold",
    "support_type": "Tree = ít nhựa, dễ gỡ · Normal = mặt đỡ phẳng rộng",
    "support_threshold_angle": "KN 30° · ↑ = SINH nhiều đỡ hơn · ↓ = ít đỡ (chỉ chỗ rất dốc)",
    "support_on_build_plate_only": "BẬT = chỉ đỡ từ bàn (không đỡ trên vật)",
    "support_top_z_distance": "KN 0.2 (cùng nhựa) · 0 (nhựa đỡ riêng) · ↑ dễ gỡ/mặt xấu · ↓ mặt đẹp/khó gỡ",
    "support_base_pattern": "Hollow/Lightning = nhẹ · Rectilinear = chắc",
    "support_interface_top_layers": "↑ = mặt đỡ phẳng, ít rủ (tốn hơn)",
    "support_object_xy_distance": "↑ = dễ gỡ ngang · ↓ = sát vật",
    # Filament
    "filament_settings_id": "Chọn ĐÚNG loại nhựa (Matte/Lite/Basic/PETG) để flow/nhiệt/PA khớp",
    "nozzle_temperature": "PLA 220 · ↑5–10 nếu tắc/lớp tách · ↓ nếu stringing/rủ",
    "nozzle_temperature_initial_layer": "≈ nozzle other · ↑ giúp lớp 1 bám",
    "textured_plate_temp": "PLA 55 (hè VN ↓45–50) · PETG 70 · ↑ bám hơn nhưng elephant-foot",
    "hot_plate_temp": "PLA 55 · PETG 70 · ↑ bám hơn",
    "filament_flow_ratio": "↑ = đầy/khít hơn (tràn nếu quá) · ↓ = bớt over-extrude (lắp khít) · PETG 0.93–0.96",
    "filament_max_volumetric_speed": "Trần lưu lượng · ↓ nếu thiếu nhựa/tắc · quá thấp = in chậm",
    "fan_max_speed": "PLA 100% · PETG 30–50% · ↑ overhang đẹp · ↓ bền lớp hơn",
    "close_fan_the_first_x_layers": "↑ = lớp đầu bám tốt hơn",
    # Others
    "brim_type": "Chống cong đế nhỏ · PETG nên bật (outer)",
    "brim_width": "↑ = bám mạnh hơn (tốn nhựa, phải cắt)",
    "enable_prime_tower": "BẬT khi >1 màu · 1 màu → TẮT (đỡ tốn)",
    "fuzzy_skin": "Bật = bề mặt nhám chống trơn/giấu vân",
    "timelapse_type": "Smooth (Traditional dễ lỗi mặt)",
    "print_sequence": "By object khi cần tránh va chạm/nhiều vật",
    "spiral_mode": "Vase: 1 thành liền, rỗng — cho lọ/vỏ",
}

def goal_advisor(geo):
    """Tu van theo MUC TIEU + tu goi y preset phu hop hinh hoc file."""
    goals = [
        ("Chi tiết cao / nét đẹp", "#7c3aed", "Mini, mô hình trưng bày, chữ/hoa văn nhỏ — IN CHẬM, LÂU.",
         [("Layer height", "0.08–0.12"), ("Initial layer speed", "25–30"), ("Outer wall", "50–100"),
          ("Wall loops", "3"), ("Top shell", "5"), ("Fan", "100%"),
          ("Wall generator", "Arachne"), ("Order of walls", "Inner/Outer/Inner"),
          ("Ironing", "All top surfaces (nếu mặt phẳng)")]),
        ("Cân bằng (mặc định)", "#16a34a", "Đa số nhu cầu — cân nét, tốc độ, độ bền.",
         [("Layer height", "0.20"), ("Initial layer speed", "40–50"), ("Outer wall", "150–200"),
          ("Wall loops", "2–3"), ("Sparse infill", "15%"), ("Fan", "100%")]),
        ("Nhanh / nháp", "#d97706", "Không cần nét: prototype, đồ thử, vật lớn.",
         [("Layer height", "0.28"), ("Initial layer speed", "50"), ("Outer wall", "250+"),
          ("Wall loops", "2"), ("Sparse infill", "10%"), ("Top/Bottom shell", "3 / 2")]),
        ("Bền / chức năng", "#2563eb", "Đồ chịu lực, bản lề, snap-fit, lắp ghép.",
         [("Wall loops", "4–5"), ("Sparse infill", "30–40% Gyroid"), ("Order of walls", "Inner/Outer"),
          ("Layer height", "0.16–0.20"), ("Outer wall", "≤150"), ("Flow ratio", "0.96 (lắp khít)")]),
    ]
    sug, reason = 1, "phù hợp đa số mô hình"
    if geo and geo.get("area_cm2"):
        maxdim = max(geo["dx"], geo["dy"], geo["dz"])
        dens = geo["tris"] / geo["area_cm2"]
        if dens > 150 or maxdim < 60:
            sug, reason = 0, f"mô hình NHIỀU chi tiết (mật độ {dens:.0f} tam giác/cm², kích thước {maxdim:.0f}mm) → nên in nét/chậm"
        elif dens < 40 and maxdim > 120:
            sug, reason = 2, f"mô hình ĐƠN GIẢN & lớn (mật độ {dens:.0f} tam giác/cm², {maxdim:.0f}mm) → in nhanh được"
        else:
            reason = f"mật độ chi tiết trung bình ({dens:.0f} tam giác/cm², {maxdim:.0f}mm)"
    cards = ""
    for i, (name, color, who, rows) in enumerate(goals):
        badge = f'<span class="goal" style="background:{color}">GỢI Ý CHO FILE NÀY</span>' if i == sug else ""
        ring = f";box-shadow:0 0 0 2px {color}" if i == sug else ""
        tr = "".join(f'<tr><td>{a}</td><td class="val">{b}</td></tr>' for a, b in rows)
        cards += (f'<div class="card" style="border-top:3px solid {color}{ring}">'
                  f'<h3 style="color:{color}">{name}{badge}</h3>'
                  f'<div class="sub" style="margin:0 0 6px">{who}</div><table>{tr}</table></div>')
    note = (f'<div style="background:#fff;border:1px solid #e2e8f0;border-left:5px solid {goals[sug][1]};'
            f'border-radius:12px;padding:12px 16px;margin-bottom:14px;font-size:14px">'
            f'Gợi ý cho file này: <b style="color:{goals[sug][1]}">{goals[sug][0]}</b> — {reason}.</div>') if geo else ""
    return f'<div class="section-title">Tư vấn theo MỤC TIÊU (như chuyên gia)</div>{note}<div class="grid">{cards}</div>'

def symptom_advisor():
    """Bang tu van theo TRIEU CHUNG (chuyen gia) — nguon: wiki Bambu + cong dong."""
    rows = [
        ("Lớp 1 không bám", "Bàn bẩn / Z cao / sai loại tấm", "Rửa bàn + Bed Leveling; ↓ Initial layer speed 25–30; ↑ Initial layer height; TẮT fan lớp 1–3; hạ Z (G29.1 −0.04)"),
        ("Kéo râu (stringing)", "Nhựa ẩm / nhiệt cao / retract thiếu", "SẤY nhựa; ↓ Nozzle temp 5–10°C; ↑ Retraction length; ↑ Travel speed"),
        ("Thiếu nhựa (under-extrusion)", "Vượt Max volumetric / flow thấp / tắc", "↓ Speed hoặc ↓ Max volumetric; ↑ Nozzle temp 5–10°C; ↑ Flow ratio; chạy Flow Dynamics"),
        ("Hở/rỗ ngay sau overhang", "Đổi tốc đột ngột ở outer wall", "BẬT 'Slow down for overhangs'; ↓ Smooth coefficient (0.1)"),
        ("Mặt đua (overhang) rủ", "Làm mát kém / in nhanh", "↑ Fan 100%; ↓ Outer wall speed; BẬT slow-down overhang; Order Inner/Outer"),
        ("Tách lớp / dễ gãy", "Nhiệt thấp / fan cao / nhanh", "↑ Nozzle temp 5–10°C; ↓ Fan; ↓ Speed; ↑ Wall loops"),
        ("Cong vênh / bong góc", "Co rút / bám bàn kém", "↑ Bed temp; BẬT Brim + keo; ↓ Sparse infill; tránh gió lùa"),
        ("Mặt trên hở / rỗ", "Top shell mỏng / infill thấp", "↑ Top shell layers 5; ↑ Sparse infill; BẬT Ironing (top surfaces)"),
        ("Vân sóng mặt ngoài (ringing)", "Gia tốc cao / rung", "↓ Acceleration; ↓ Outer wall speed"),
        ("Lắp khít quá chặt / kẹt", "Over-extrude / flow cao", "↓ Flow ratio (0.96); ↑ XY hole compensation; chừa dung sai +0.2mm"),
        ("Màu lẫn (đa màu)", "Flush ít / thiếu prime tower", "↑ Flushing volume; BẬT Prime tower"),
    ]
    tr = "".join(f'<tr><td><b>{a}</b></td><td>{b}</td><td class="gd">{c}</td></tr>' for a, b, c in rows)
    return ('<div class="section-title">Bảng tư vấn theo TRIỆU CHỨNG (symptom → chỉnh gì)</div>'
            '<div class="card"><table><tr><th>Triệu chứng</th><th>Nguyên nhân</th>'
            '<th>Chỉnh gì (↑ tăng / ↓ giảm)</th></tr>' + tr + '</table></div>')

def geometry_advice(geo):
    """Tu hinh hoc mesh (mat cong/phang/dung/overhang) -> thong so nen chinh."""
    if not geo:
        return ""
    dx, dy, dz = geo["dx"], geo["dy"], geo["dz"]
    top = geo.get("top_ratio", 0); slope = geo.get("slope_ratio", 0)
    vert = geo.get("vert_ratio", 0); down = geo.get("down_ratio", 0)
    aspect = geo.get("aspect", 0)
    items = []
    if slope > 25:
        items.append(("Nhiều mặt CONG / DỐC (~%.0f%%)" % slope, "#7c3aed",
            "Mặt cong dễ bị 'bậc thang' theo lớp → <b>↓ Layer height 0.08–0.12</b> hoặc bật <b>Adaptive/Variable layer height</b> (mỏng chỗ cong, dày chỗ phẳng). Bật <b>Slow down for overhangs</b>. Wall generator = Arachne."))
    else:
        items.append(("Ít mặt cong (~%.0f%%)" % slope, "#16a34a",
            "Chủ yếu mặt phẳng/đứng → Layer <b>0.20 vẫn đẹp</b>, không cần lớp mỏng → in nhanh hơn."))
    if top > 12:
        items.append(("Mặt TRÊN phẳng lớn (~%.0f%%)" % top, "#0d9488",
            "Hưởng lợi từ <b>Ironing = All/Topmost top surfaces</b> (mịn/bóng). <b>↑ Top shell layers 5</b>, Top surface pattern = Monotonic. (PLA Matte thì bỏ ironing.)"))
    else:
        items.append(("Ít mặt phẳng trên (~%.0f%%)" % top, "#64748b",
            "Không cần Ironing (tốn thời gian, ít tác dụng trên mặt cong/nhỏ)."))
    if down > 8:
        items.append(("Overhang / mặt hướng xuống (~%.0f%%)" % down, "#dc2626",
            "Cần <b>Support</b> (Tree/auto, threshold 30°) + <b>↑ Fan 100%</b> + <b>↓ Outer wall speed</b> ở vùng đua. Nếu in-place → dùng Support blocker để không kẹt khớp."))
    else:
        items.append(("Ít overhang (~%.0f%%)" % down, "#16a34a",
            "Gần như <b>không cần support</b> → tiết kiệm nhựa &amp; thời gian."))
    if vert > 40:
        items.append(("Nhiều thành ĐỨNG (~%.0f%%)" % vert, "#d97706",
            "Thành đứng in nhanh &amp; đẹp → có thể <b>↑ Inner/Outer wall speed</b>; ít bậc thang."))
    if aspect > 3:
        items.append(("Cao &amp; MẢNH (tỉ lệ %.1f)" % aspect, "#2563eb",
            "Dễ rung/đổ → <b>↓ tốc độ</b>, <b>BẬT Brim</b>, giảm acceleration; cân nhắc in kèm giá đỡ."))
    if dx*dy > 10000:
        items.append(("Đế RỘNG (%.0f×%.0f mm)" % (dx, dy), "#16a34a",
            "Đế rộng bám tốt → có thể in nhanh hơn phần thân; vẫn giữ <b>lớp 1 chậm 25–30</b>."))
    cards = "".join(
        f'<div class="card" style="border-top:3px solid {c}"><h3 style="color:{c}">{f}</h3>'
        f'<div class="gd" style="max-width:none">{a}</div></div>' for f, c, a in items)
    return f'<div class="section-title">Phân tích HÌNH HỌC → thông số nên chỉnh</div><div class="grid">{cards}</div>'

def render_material_ref():
    rows = [
        ("PLA Basic", "220", "55 (Cool 35)", "~21", "0.98", "100%", "De nhat, ben tot, mat bong nhe"),
        ("PLA Matte", "220 (215-230)", "55-60", "~18-21", "0.98", "100%", "Mat nham mo; GION hon -> wall>=3; +5-15C neu tac; KHONG can ironing; lop 1 kho bam -> 30mm/s"),
        ("PLA Lite", "210-220", "55", "~15-20", "0.98", "100%", "Kinh te / in nhap; ben & be mat thap hon Basic 1 chut"),
        ("PETG", "250-255", "70", "~12-16", "0.95", "30-50%", "BAT BUOC say; bat Brim chong cong; flow 0.93-0.96"),
        ("TPU (deo)", "220-240", "35-45", "thap", "-", "0-30%", "In cham, luu luong thap; gioang / op deo"),
    ]
    tr = "".join(
        f'<tr><td><b>{a}</b></td><td class="val">{b}</td><td class="val">{c}</td><td class="val">{d}</td>'
        f'<td class="val">{e}</td><td class="val">{fn}</td><td style="color:#475569;font-size:12px">{gg}</td></tr>'
        for a, b, c, d, e, fn, gg in rows)
    return ('<div class="card"><table><tr><th>Nhua</th><th>Nozzle C</th><th>Bed C</th>'
            '<th>Max vol</th><th>Flow</th><th>Fan</th><th>Ghi chu</th></tr>' + tr + '</table></div>')

def audit_real(geo, gstats, s, slice_info):
    """Cac phat hien tinh THAT tu mesh + g-code."""
    F = []
    def add(l, t, d): F.append((l, t, d))
    if geo:
        dx, dy, dz = geo["dx"], geo["dy"], geo["dz"]
        maxobj = geo.get("max_obj_dim", max(dx, dy, dz))
        n = geo.get("n_placed", 1)
        if maxobj > 256:
            add("bad", "Vật đơn lẻ VƯỢT khổ A1 (256mm)", f"Vật lớn nhất {maxobj:.0f}mm > 256 → phải cắt nhỏ hoặc thu nhỏ.")
        else:
            extra = f" · {n} vật xếp trên khay (union toàn khay {dx:.0f}×{dy:.0f}mm — KHÔNG phải 1 vật)" if n > 1 else ""
            add("ok", "Kích thước vừa khổ A1", f"Vật lớn nhất {maxobj:.0f}mm < 256{extra}.")
        dr = geo["down_ratio"]
        sup = str(g(s, "enable_support", default="0")).lower() in ("1", "true")
        if dr > 8 and not sup:
            add("warn", "Có mặt hướng xuống nhưng Support ĐANG TẮT", f"~{dr:.0f}% diện tích hướng xuống (>45°) → có thể cần support.")
        elif dr > 8 and sup:
            add("ok", "Support hợp lý với overhang", f"~{dr:.0f}% mặt hướng xuống; support đang bật → phù hợp.")
        dens = material_density(s)
        sg = geo["vol_cm3"] * dens
        pw = num(slice_info["plates"][0]["meta"].get("weight"), None) if slice_info.get("plates") else None
        if pw and sg > 0:
            add("info", "Tỷ lệ đặc (real)", f"Nhựa thực {pw:.0f}g / khối đặc {sg:.0f}g (khối lượng riêng {dens} g/cm³) = {pw/sg*100:.0f}% — còn lại là rỗng/infill + support.")
    if gstats:
        mv = gstats["max_vol"]; setmv = num(g(s, "filament_max_volumetric_speed"), None)
        if setmv and mv > setmv*1.03:
            add("warn", "Flow THỰC vượt trần cài đặt", f"Max volumetric thực ~{mv:.1f} > cài đặt {setmv} mm³/s → nguy cơ thiếu nhựa/tắc.")
        elif mv > 0:
            add("ok", "Flow thực trong giới hạn", f"Max volumetric thực ~{mv:.1f} mm³/s.")
        add("info", "Toolpath (real)", f"{gstats['layers']} lớp · max feed {gstats['max_feed']:.0f}mm/s · {gstats['retractions']} retract · nozzle {gstats['nozzle_temp']:.0f}/bed {gstats['bed_temp']:.0f}°C · fan {gstats['fan_pct']}%.")
    return F

def render_html(path, s, slice_info, findings, source, geo=None, gstats=None):
    name = os.path.basename(path)
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    # summary tu slice_info hoac gcode
    sm = s.get("__summary__", {})
    plate = slice_info["plates"][0] if slice_info.get("plates") else None
    time_s = (plate["meta"].get("prediction") if plate else None) or sm.get("time", "")
    weight = (plate["meta"].get("weight") if plate else None) or sm.get("weight_g", "")
    fils = plate["filaments"] if plate else []
    time_disp = fmt_time(time_s) if str(time_s).isdigit() else (time_s or "—")

    def chip(label, val):
        return f'<div class="stat"><div class="l">{html.escape(label)}</div><div class="v">{html.escape(str(val) or "—")}</div></div>'

    stats = chip("File", name) + chip("Nguồn đọc", source) + chip("Thời gian in", time_disp) \
        + chip("Khối lượng (g)", weight or "—") + chip("Số filament", str(len(fils) or 0)) \
        + chip("Nozzle", g(s, "nozzle_diameter", default="?") + " mm")

    # findings
    order = {"bad": 0, "warn": 1, "info": 2, "ok": 3}
    findings = sorted(findings, key=lambda x: order.get(x[0], 9))
    frows = ""
    for lv, t, d in findings:
        c, lab = LV.get(lv, ("#64748b", lv.upper()))
        frows += f'<div class="find"><span class="badge" style="background:{c}">{lab}</span><div><b>{html.escape(t)}</b><div class="fd">{html.escape(d)}</div></div></div>'

    # groups (form kieu Bambu Studio: tab -> muc con -> truong)
    # Ironing: cac tham so con CHI hien khi Ironing type khac "No ironing" (giong UI Bambu)
    iron_on = (g(s, "ironing_type", default="") or "").lower() not in ("", "no ironing", "none", "0")
    IRON_DEP = {"ironing_speed", "ironing_flow", "ironing_spacing",
                "ironing_pattern", "ironing_inset", "ironing_direction"}
    gcards = ""
    for title, color, subs in GROUPS:
        body = ""
        for subname, fields in subs:
            trs = ""
            for label, k, unit in fields:
                keys = k if isinstance(k, tuple) else (k,)
                if not iron_on and keys[0] in IRON_DEP:
                    continue  # an tham so ironing khi dang tat
                raw = g(s, *keys, default="")
                if raw == "":
                    continue
                shown = fmt_field(keys[0], raw)
                gd = GUIDE.get(keys[0], "")
                trs += (f'<tr><td>{html.escape(label)}</td><td class="val">{html.escape(shown)} {unit}</td>'
                        f'<td class="gd">{html.escape(gd)}</td></tr>')
            if trs:
                body += f'<tr class="sub"><td colspan="3">{html.escape(subname)}</td></tr>{trs}'
        if body:
            gcards += f'<div class="card" style="border-top:3px solid {color}"><h3 style="color:{color}">{title}</h3><table>{body}</table></div>'

    # filament list
    filrows = ""
    for f in fils:
        col = f.get("color", "#ccc")
        filrows += f'<tr><td><span class="sw" style="background:{html.escape(col)}"></span>{html.escape(f.get("type","?"))}</td><td>{html.escape(f.get("used_g","?"))} g</td><td>{html.escape(f.get("used_m","?"))} m</td></tr>'
    filblock = f'<div class="card"><h3>Filament da dung</h3><table><tr><th>Loai</th><th>g</th><th>m</th></tr>{filrows}</table></div>' if filrows else ""

    nbad = sum(1 for f in findings if f[0] == "bad")
    nwarn = sum(1 for f in findings if f[0] == "warn")
    verdict = "Co LOI can sua" if nbad else ("Co canh bao nen xem" if nwarn else "On - khong canh bao lon")
    vcolor = "#dc2626" if nbad else ("#d97706" if nwarn else "#16a34a")

    # --- Khoi tinh toan THAT (Slice result + Mesh + Toolpath) ---
    lh = num(g(s, "layer_height"), 0.2) or 0.2
    fils_p = slice_info["plates"][0]["filaments"] if slice_info.get("plates") else []
    tot_m = sum(num(fp.get("used_m"), 0) or 0 for fp in fils_p)
    tot_g = sum(num(fp.get("used_g"), 0) or 0 for fp in fils_p) or (num(weight, 0) or 0)
    height = (geo["dz"] if geo else None) or (gstats["z_max"] if gstats else None)
    n_layers = (gstats["layers"] if gstats and gstats["layers"] else (int(height/lh) if height else None))
    PRICE = 0.025  # USD/g (uoc tinh, chinh theo gia nhua thuc)
    cost = tot_g * PRICE if tot_g else None

    def rrow(k, v): return f'<tr><td>{k}</td><td class="val">{v}</td></tr>'
    realcards = ""
    if tot_g or n_layers or height:
        sr = rrow("Filament tong", f"{tot_m:.2f} m / {tot_g:.1f} g") if tot_g else ""
        for i, fp in enumerate(fils_p, 1):
            sw = fp.get("color", "#ccc")
            sr += rrow(f'<span class="sw" style="background:{html.escape(sw)}"></span>Filament {i} ({html.escape(fp.get("type","?"))})',
                       f'{num(fp.get("used_m"),0) or 0:.2f} m / {num(fp.get("used_g"),0) or 0:.1f} g')
        sr += rrow("Model printing time", time_disp)
        sr += rrow("So lop", n_layers if n_layers else "—")
        sr += rrow("Chieu cao", f"{height:.2f} mm" if height else "—")
        if cost:
            sr += rrow("Chi phi uoc tinh", f"~{cost:.2f} (@{PRICE}/g)")
        realcards += f'<div class="card" style="border-top:3px solid #16a34a"><h3>Ket qua slice (tinh tu file)</h3><table>{sr}</table></div>'
    if geo:
        realcards += ('<div class="card" style="border-top:3px solid #2563eb"><h3>Hinh hoc mo hinh (mesh THAT)</h3><table>'
            + rrow("So object", geo["objects"])
            + rrow("So tam giac", f'{geo["tris"]:,}')
            + rrow("Kich thuoc X&times;Y&times;Z", f'{geo["dx"]:.1f} &times; {geo["dy"]:.1f} &times; {geo["dz"]:.1f} mm')
            + rrow("The tich khoi", f'{geo["vol_cm3"]:.1f} cm&sup3;')
            + rrow("Dien tich be mat", f'{geo["area_cm2"]:.0f} cm&sup2;')
            + rrow("KL neu DAC (PLA 1.24)", f'{geo["solid_g"]:.0f} g')
            + rrow("Mat huong xuong &gt;45&deg;", f'{geo["down_ratio"]:.0f} %')
            + '</table></div>')
    if gstats:
        realcards += ('<div class="card" style="border-top:3px solid #d97706"><h3>Toolpath G-code (THAT)</h3><table>'
            + rrow("So lop (dem)", gstats["layers"])
            + rrow("Max volumetric THUC", f'{gstats["max_vol"]:.1f} mm&sup3;/s')
            + rrow("Max feedrate", f'{gstats["max_feed"]:.0f} mm/s')
            + rrow("So lan retract", gstats["retractions"])
            + rrow("Travel move", f'{gstats["travels"]:,}')
            + rrow("Nozzle / Bed", f'{gstats["nozzle_temp"]:.0f} / {gstats["bed_temp"]:.0f} &deg;C')
            + rrow("Fan toi da", f'{gstats["fan_pct"]} %')
            + '</table></div>')
    realblock = f'<div class="section-title">Tính toán THẬT (real) từ dữ liệu mô hình</div><div class="grid">{realcards}</div>' if realcards else ""
    advblock = goal_advisor(geo)
    geoblock = geometry_advice(geo)
    sympblock = symptom_advisor()
    matref = render_material_ref()

    out = f"""<!DOCTYPE html><html lang="vi"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Phan tich: {html.escape(name)}</title>
<style>
:root{{--ink:#0f172a;--muted:#475569;--line:#e2e8f0;--bg:#eef1f5}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--ink);font-family:Inter,"Segoe UI",system-ui,sans-serif;line-height:1.55}}
.wrap{{max-width:1080px;margin:0 auto;padding:24px 18px 60px}}
h1{{font-size:24px;margin:0 0 4px}} .sub{{color:var(--muted);font-size:13px;margin-bottom:18px}}
.verdict{{display:flex;align-items:center;gap:12px;background:#fff;border:1px solid var(--line);border-left:5px solid {vcolor};border-radius:12px;padding:14px 16px;margin-bottom:18px;box-shadow:0 8px 24px rgba(15,23,42,.06)}}
.verdict b{{font-size:18px;color:{vcolor}}}
.stats{{display:grid;grid-template-columns:repeat(6,1fr);gap:10px;margin-bottom:20px}}
.stat{{background:#fff;border:1px solid var(--line);border-radius:10px;padding:10px}}
.stat .l{{color:#64748b;font-size:11px;font-weight:600}} .stat .v{{font-weight:800;margin-top:3px;font-size:14px;word-break:break-word}}
.grid{{display:grid;grid-template-columns:1fr 1fr;gap:14px;align-items:start}}
.card{{background:#fff;border:1px solid var(--line);border-radius:12px;padding:14px 16px;box-shadow:0 8px 24px rgba(15,23,42,.05)}}
.card h3{{font-size:15px;margin:0 0 8px}}
table{{width:100%;border-collapse:collapse;font-size:13px}}
td,th{{text-align:left;padding:6px 6px;border-bottom:1px solid var(--line)}} th{{color:#64748b;font-size:11px;text-transform:uppercase}}
td.val{{font-weight:700;text-align:right;white-space:nowrap}}
td.gd{{color:#475569;font-size:11px;line-height:1.35;max-width:280px}}
tr.sub td{{background:#eef2f6;font-weight:800;color:#334155;font-size:10.5px;text-transform:uppercase;letter-spacing:.5px;padding:5px 6px}}
.card table{{margin-bottom:2px}}
.goal{{display:inline-block;color:#fff;border-radius:6px;padding:1px 8px;font-size:10px;font-weight:800;margin-left:6px}}
.sw{{display:inline-block;width:12px;height:12px;border-radius:3px;margin-right:6px;vertical-align:-1px;border:1px solid rgba(0,0,0,.15)}}
.section-title{{font-size:18px;font-weight:800;margin:26px 0 12px}}
.find{{display:flex;gap:12px;align-items:flex-start;background:#fff;border:1px solid var(--line);border-radius:10px;padding:11px 13px;margin-bottom:8px}}
.badge{{color:#fff;font-size:10px;font-weight:800;border-radius:6px;padding:3px 9px;flex:none;margin-top:2px;min-width:74px;text-align:center}}
.fd{{color:var(--muted);font-size:12.5px;margin-top:2px}}
@media(max-width:860px){{.stats,.grid{{grid-template-columns:1fr 1fr}}}}
</style></head><body><div class="wrap">
<h1>Phan tich file in</h1><div class="sub">{html.escape(name)} · {now}</div>
<div class="verdict"><b>{verdict}</b><span class="sub" style="margin:0">({nbad} loi · {nwarn} canh bao · {len(findings)} muc kiem tra)</span></div>
<div class="stats">{stats}</div>
{realblock}
<div class="section-title">Cảnh báo &amp; gợi ý (tính từ file)</div>
{frows or '<div class="sub">Không có mục nào.</div>'}
{advblock}
{geoblock}
{sympblock}
<div class="section-title">Thông số chi tiết (form Bambu Studio) — cột phải: ý nghĩa &amp; điều chỉnh ↑↓</div>
<div class="grid">{gcards}{filblock}</div>
<div class="section-title">Cấu hình CHUẨN theo nhựa (tham khảo)</div>
{matref}
<div class="sub" style="margin-top:24px">Tao boi analyze_print.py — phan tich offline + tinh REAL tu mesh/g-code, doi chieu wiki Bambu Lab. Gia tri huong dan; chay Flow Dynamics + tinh chinh theo nhua thuc te.</div>
</div></body></html>"""
    rep = os.path.splitext(path)[0] + "_analysis.html"
    open(rep, "w", encoding="utf-8").write(out)
    return rep, verdict, nbad, nwarn

def print_console(s, findings, verdict):
    print("=" * 56)
    print(" PHAN TICH FILE IN — ket qua:", verdict)
    print("=" * 56)
    for lv, t, d in sorted(findings, key=lambda x: {"bad":0,"warn":1,"info":2,"ok":3}.get(x[0],9)):
        print(f"[{LV.get(lv,('','?'))[1]:8}] {t}")
        print(f"           {d}")
    print("-" * 56)

def main():
    if len(sys.argv) < 2:
        # Khong co file -> van xuat tham chieu cau hinh theo nhua
        base = os.path.dirname(os.path.abspath(__file__))
        rep = os.path.join(base, "cau-hinh-theo-nhua.html")
        out = ("<!DOCTYPE html><meta charset='utf-8'><title>Cau hinh theo nhua</title>"
               "<style>body{font-family:Segoe UI,Inter,sans-serif;max-width:1000px;margin:24px auto;"
               "padding:0 16px;background:#eef1f5;color:#0f172a}h1{font-size:22px}"
               ".card{background:#fff;border:1px solid #e2e8f0;border-radius:12px;padding:8px 14px}"
               "table{width:100%;border-collapse:collapse}td,th{padding:8px 10px;border-bottom:1px solid #e2e8f0;"
               "font-size:13px;text-align:left}th{background:#f8fafc;color:#475569;text-transform:uppercase;font-size:11px}"
               "td.val{font-weight:800}</style>"
               "<h1>Cau hinh CHUAN theo nhua — Bambu Lab A1 (nozzle 0.4)</h1>"
               "<p style='color:#475569'>Doi chieu wiki Bambu + forum. Chay <b>Flow Dynamics calibration</b> va tinh chinh theo nhua thuc te.</p>"
               + render_material_ref()
               + "<p style='color:#475569;margin-top:16px'>De PHAN TICH 1 mau in: keo file .3mf / .gcode.3mf / .gcode vao <b>Phan-Tich-File-In.bat</b>.</p>")
        open(rep, "w", encoding="utf-8").write(out)
        print("Khong co file -> da xuat tham chieu cau hinh theo nhua:", rep)
        try:
            webbrowser.open("file:///" + rep.replace("\\", "/"))
        except Exception:
            pass
        return
    path = sys.argv[1].strip('"')
    if not os.path.isfile(path):
        print("Khong tim thay file:", path); return
    s, slice_info, source, geo, gstats = read_any(path)
    if not s or (len(s) == 1 and "__summary__" in s):
        print("LUU Y: file khong co thong so process (Project/STL) -> van tinh REAL tu mesh + tham chieu theo nhua.")
    findings = audit(s, slice_info) + audit_real(geo, gstats, s, slice_info)
    rep, verdict, nbad, nwarn = render_html(path, s, slice_info, findings, source, geo, gstats)
    print_console(s, findings, verdict)
    print("Bao cao HTML:", rep)
    try:
        webbrowser.open("file:///" + rep.replace("\\", "/"))
    except Exception:
        pass

if __name__ == "__main__":
    main()
