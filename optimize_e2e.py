#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""E2E: slice BASELINE -> phan tich -> slice TOI UU -> so sanh bang SO THAT.

Triet ly: khong tuyen bo "tiet kiem X%" neu chua slice ca hai. Moi con so trong
bao cao deu la ket qua slice that tu Bambu Studio CLI.

Luong:
  1. STL  -> boc vao slice_template.3mf (config AUTO-balanced-0.20mm chuan Bambu)
     3MF -> dung nguyen config nhung trong file
  2. Slice VONG 1 (BASELINE)      -> thoi gian / gam / so lop that
  3. analyzer.analyze()            -> tim van de (overhang, VLH, tran luu luong...)
  4. Ap preset toi uu vao 3mf      -> go VLH + vá config
  5. Slice VONG 2 (TOI UU)         -> thoi gian / gam / so lop that
  6. Doi chieu 1 vs 2, chi giu khuyen nghi NAO THUC SU CO LOI
"""
from __future__ import annotations

import json
import os
import re
import shutil
import zipfile

import analyzer
import slicer_cli

CFG = "Metadata/project_settings.config"
VLH = "metadata/layer_heights_profile.txt"

# Cac key preset an toan de ghi vao project_settings (da kiem chung tren A1 2.7.1)
SAFE_KEYS = (
    "layer_height", "wall_loops", "wall_generator", "wall_sequence",
    "sparse_infill_density", "sparse_infill_pattern",
    "top_shell_layers", "bottom_shell_layers",
    "enable_support", "support_type", "support_style", "bridge_no_support",
    "support_on_build_plate_only", "support_threshold_angle",
    "support_interface_filament", "support_top_z_distance", "support_bottom_z_distance",
    "support_interface_spacing", "support_interface_pattern",
    "independent_support_layer_height",
    "outer_wall_speed", "inner_wall_speed", "sparse_infill_speed",
    "internal_solid_infill_speed", "top_surface_speed",
    "seam_position", "seam_slope_type", "seam_gap", "brim_type", "brim_width",
    "skirt_loops",   # brim_object_gap CO TINH BO KHOI SAFE_KEYS: ghi key nay lam CLI crash
    "draft_shield", "enable_arc_fitting", "resolution",
    "ironing_type", "infill_wall_overlap", "initial_layer_speed",
    "initial_layer_print_height", "top_surface_pattern", "top_shell_thickness",
    "top_surface_line_width", "bridge_flow", "bridge_speed",
    "enable_overhang_speed", "overhang_1_4_speed", "overhang_2_4_speed",
    "overhang_3_4_speed", "overhang_4_4_speed", "overhang_totally_speed",
    "default_acceleration", "outer_wall_acceleration", "inner_wall_acceleration",
    "travel_speed",
)


# ===== NGAN SACH THOI GIAN (user chot 2026-07-16, dieu chinh cung ngay) =====
# MUC TIEU: preset khong vuot DEFAULT (0.20mm Standard @BBL A1) qua +1h30m.
# SAI SO CHAP NHAN: den +2h van OK — "dung co ep", chi cat khi vuot +2h.
# Cac fix loi KY THUAT (warping/keo soi/vat cao/brim/support hoc ranh) LUON giu,
# khong bao gio bi cat vi ngan sach. So sanh bang total_predication (result.json)
# — CUNG THANG voi so Bambu Studio GUI hien thi (gom flush/moi nhua).
BUDGET_S = 90 * 60          # muc tieu +1h30
BUDGET_TOL_S = 30 * 60      # sai so user cho phep: +1h30 den +2h


def _v1(v) -> str:
    """Gia tri config co the la list hoac scalar -> lay phan tu dau dang str."""
    return str(v[0] if isinstance(v, list) and v else v)


def trim_ladder(p: dict) -> list[tuple[str, dict]]:
    """Bac thang CAT de ep ngan sach — thu tu theo GIA DO THAT (bench_ab.py,
    BUCKET.3mf khay 1, baseline 3h22m54s, 2026-07-16): cat truoc cai TON GIO
    NHIEU nhung mat tham my IT.

    TUYET DOI KHONG cham lever KY THUAT (uu tien user > ngan sach):
      - tall_rules: default/outer_wall_acceleration, travel_speed (chong lech truc vat cao)
      - inner/sparse/solid speed (tran luu luong mvs — chong ket nhua Matte/Metal)
      - enable_overhang_speed + overhang_* (chong xau mat hang), bridge_flow/speed
      - support* (chong vong/hong hinh), initial_layer_* (bam ban), brim (bam ban)
    Ngoai le co chu dich o buoc layer-notch: initial_layer_print_height chi TANG
    theo layer moi (giu quy tac = layer chinh, bam ban khong yeu di) va cac speed
    mvs scale XUONG theo tran moi — la dong bo rang buoc, khong phai cat lever.
    """
    steps: list[tuple[str, dict]] = []
    if p.get("ironing_type") not in (None, "no ironing"):
        steps.append(("Tắt ủi mặt trên (giá đo: −19m28s)",
                      {"ironing_type": "no ironing"}))
    dens = re.sub(r"[^\d.]", "", _v1(p.get("sparse_infill_density") or ""))
    if dens and float(dens) > 8:
        steps.append((f"Ruột {dens}% → 8% (giá đo 12%→8%: −9m16s)",
                      {"sparse_infill_density": "8%"}))
    if _v1(p.get("sparse_infill_pattern")) == "gyroid":
        steps.append(("Ruột Gyroid → Adaptive Cubic (giá đo: −4m39s, −2.9g)",
                      {"sparse_infill_pattern": "adaptivecubic"}))
    if p.get("wall_loops") and int(_v1(p["wall_loops"])) >= 3:
        steps.append(("Tường 3 → 2 (giá đo: −32m07s; sandwich cần ≥3 nên về Inner/Outer)",
                      {"wall_loops": "2", "wall_sequence": "inner wall/outer wall"}))
    # Thanh ngoai/mat tren: tha ham THAM MY ve muc fast (van <= tran mvs vi lay theo
    # inner_wall_speed da bi chan boi tran) — KHONG dung den cac speed ky thuat khac.
    inner = p.get("inner_wall_speed")
    outer = p.get("outer_wall_speed")
    if inner and outer and int(_v1(outer)) < min(int(_v1(inner)), 180):
        v = min(int(_v1(inner)), 180)
        steps.append((f"Thành ngoài {_v1(outer)} → {v} mm/s (giá đo 200→150: −7m04s chiều ngược)",
                      {"outer_wall_speed": [str(v)],
                       "top_surface_speed": [str(min(v, 150))]}))
    tsl = int(_v1(p.get("top_shell_layers") or 0) or 0)
    bsl = int(_v1(p.get("bottom_shell_layers") or 0) or 0)
    if tsl > 5 or bsl > 3:
        # Ve thang san 5/3 trong 1 buoc — moi buoc cat = 1 lan slice CLI that,
        # giam 1 lop/lan la ton nhieu lan slice vo ich (review MEDIUM-4).
        steps.append((f"Vỏ trên/dưới {tsl}/{bsl} → {min(tsl, 5)}/{min(bsl, 3)} "
                      f"(giá đo 6/4→5/3: −6m07s)",
                      {"top_shell_layers": str(min(tsl, 5)),
                       "bottom_shell_layers": str(min(bsl, 3))}))
    # CUOI CUNG moi dung den layer height (danh doi van lop — ban chat che do):
    lh = float(_v1(p.get("layer_height") or 0.2))
    nxt = {0.12: 0.16, 0.16: 0.2, 0.2: 0.24}.get(lh)
    if nxt:
        ch = {"layer_height": f"{nxt:g}"}
        ilh = float(_v1(p.get("initial_layer_print_height") or lh))
        if ilh < nxt:
            ch["initial_layer_print_height"] = f"{nxt:g}"
        # duong in mat tren phai >= layer height, khong la CLI loi -51. Bump TOI
        # THIEU (= layer moi) de giu fix mat-tren-lam-tam cang hep cang tot
        # (review LOW-7 — khong nhay thang ve 0.42).
        tw = float(_v1(p.get("top_surface_line_width") or 9) or 9)
        if tw < nxt:
            ch["top_surface_line_width"] = f"{nxt:g}"
        # RANG BUOC KY THUAT (chong ket): toc do inner/sparse/solid/top duoc suy tu
        # tran mvs TAI layer CU — layer day len thi tran ha xuong (mvs / (lh x lw)).
        # Phai scale ve <= tran moi: v_new = v_old x lh_cu / lh_moi, khong la chinh
        # tay ngan sach lai VI PHAM luat chong ket cua hub. top_surface_speed CUNG
        # phai scale (review HIGH-1 — truoc thieu, giu so cu la vuot tran moi).
        for k in ("inner_wall_speed", "sparse_infill_speed",
                  "internal_solid_infill_speed", "top_surface_speed"):
            if p.get(k):
                ch[k] = [str(int(int(_v1(p[k])) * lh / nxt))]
        if p.get("outer_wall_speed") and ch.get("inner_wall_speed"):
            ch["outer_wall_speed"] = [str(min(int(_v1(p["outer_wall_speed"])),
                                              int(_v1(ch["inner_wall_speed"]))))]
        steps.append((f"Layer {lh:g} → {nxt:g}mm (giá đo 0.16→0.20: −45m34s; tốc độ scale "
                      f"theo trần mvs mới) — bước cuối cùng", ch))
    return steps


def _secs(t: str | None) -> int | None:
    """'9h 47m 18s' -> giay."""
    if not t:
        return None
    tot = 0
    for v, u in re.findall(r"(\d+)\s*([dhms])", t):
        tot += int(v) * {"d": 86400, "h": 3600, "m": 60, "s": 1}[u]
    return tot or None


def _hm(s: int | None) -> str:
    if not s:
        return "?"
    return f"{s // 3600}h {(s % 3600) // 60:02d}m"


# Cac key SUPPORT phu thuoc lan nhau + rieng theo file: interface da vat lieu
# (support_interface_filament tro toi 1 cuon cu the), tree, Z=0 thao de. File DA bat
# support (enable_support=1) thi GIU config support cua file — dung de mode preset ghi
# de sinh to hop khong slice duoc: file nhieu mau (tabletipad, prime tower + interface
# filament 3) -> -51/-101 (bug user 2026-07-19, xac minh: revert 6 key nay -> slice OK).
# File CHUA co support (enable_support=0) thi van cho analyzer them support binh thuong.
_SUPPORT_FILE_KEYS = (
    "support_type", "support_style", "support_interface_filament",
    "support_top_z_distance", "support_bottom_z_distance",
    "support_interface_spacing", "support_interface_pattern",
    "support_on_build_plate_only", "support_threshold_angle",
    "independent_support_layer_height", "enable_support",
)


def _file_has_support(cfg: dict) -> bool:
    es = cfg.get("enable_support")
    es = es[0] if isinstance(es, list) and es else es
    return str(es) in ("1", "True", "true")


def apply_preset(src: str, dst: str, preset: dict, drop_vlh: bool = True,
                 extra_cfg: dict | None = None, force_cfg: dict | None = None) -> None:
    """Ghi preset vao project_settings NHUNG trong .3mf + go Variable Layer Height.

    Phai sua config nhung, KHONG dung --load-settings: CLI doi 3 file config FULL
    tach roi, sai la segfault (BambuStudio issue #9968).

    extra_cfg: cac key config GHI TRUC TIEP ngoai SAFE_KEYS (vd filament_colour cho
    mau — #4 2026-07-19), moi gia tri la list dung schema Bambu.
    force_cfg: key GHI DE KE CA khi dang GIU support cua file (user CHU DONG chon cach
    lam support — 2026-07-19); thang cả logic preserve.
    """
    with zipfile.ZipFile(src) as zin:        # with: khong leak handle khi json/KeyError
        cfg = json.loads(zin.read(CFG).decode("utf-8", "ignore"))
        preset = dict(preset)                # khong sua ban goc nguoi goi
        _force = force_cfg or {}
        if _file_has_support(cfg):           # GIU support cua file -> khong ghi de gay -51/-101
            for k in _SUPPORT_FILE_KEYS:
                if k not in _force:          # tru khi user CHU DONG chon cach support khac
                    preset.pop(k, None)
        for k, v in preset.items():
            if k not in SAFE_KEYS:
                continue
            old = cfg.get(k)
            if isinstance(old, list) and not isinstance(v, list):
                v = [v] * max(len(old), 1)   # list rong (config la) -> van set 1 phan tu
            cfg[k] = v
        for k, v in _force.items():          # user chon cach support -> ghi de (thang preserve)
            old = cfg.get(k)
            if isinstance(old, list) and not isinstance(v, list):
                v = [v] * max(len(old), 1)
            cfg[k] = v
        for k, v in (extra_cfg or {}).items():
            old = cfg.get(k)
            # mau/gia tri per-filament: giu DU so cuon (file da mau) — set het cung mau
            if isinstance(old, list) and old:
                cfg[k] = [v[0] if isinstance(v, list) else v] * len(old)
            else:
                cfg[k] = v if isinstance(v, list) else [v]
        # RANG BUOC VAT LY: layer_height phai NHO HON moi line_width (CLI -51 neu >=;
        # 0.28==0.28 van fail). File tabletipad de top_surface_line_width 0.25 (hop le o
        # layer 0.20) nhung mode Nhanh day layer len 0.28 -> vuot -> -51 (bug user
        # 2026-07-19). CAP layer ve duoi line width NHO NHAT — giu line width tinh cua
        # file (mat tren dep) va NHANH hon la bump line width to (bump lam tut toc theo
        # tran mvs: fast 0.28+lw0.42 = 9450s > quality). Mode min (0.16) khong cham toi.
        try:
            _lh = float(cfg.get("layer_height"))
        except (TypeError, ValueError):
            _lh = None
        if _lh:
            _lws = []
            for _lwk in ("line_width", "inner_wall_line_width", "outer_wall_line_width",
                         "top_surface_line_width", "sparse_infill_line_width",
                         "internal_solid_infill_line_width"):
                _v = cfg.get(_lwk)
                try:
                    if _v not in (None, ""):
                        _lws.append(float(_v))
                except (TypeError, ValueError):
                    pass
            _minlw = min(_lws) if _lws else None
            if _minlw and _lh >= _minlw - 0.005:      # vuot/sat line width -> cap xuong
                _cap = round(_minlw - 0.01, 2)
                if _cap >= 0.08:                      # khong duoi kha nang may
                    cfg["layer_height"] = f"{_cap:g}"
                    _ilh = cfg.get("initial_layer_print_height")
                    try:
                        if _ilh not in (None, "") and float(_ilh) > _cap:
                            cfg["initial_layer_print_height"] = f"{_cap:g}"
                    except (TypeError, ValueError):
                        pass
        with zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED) as zout:
            for it in zin.infolist():
                if drop_vlh and it.filename.lower() == VLH:
                    continue                # go Variable Layer Height
                if it.filename == CFG:
                    zout.writestr(it, json.dumps(cfg, indent=4, ensure_ascii=False))
                else:
                    zout.writestr(it, zin.read(it.filename))


def run_modes(src: str, workdir: str, modes=("fast", "balanced", "quality"),
              plate: int = 1, fil_sel: str | None = None,
              color_sel: str | None = None) -> dict:
    """Slice BASELINE + tung che do -> bang so sanh bang SO THAT (khong doan).

    plate: khay de slice so sanh (file nhieu khay chon duoc khay — user 2026-07-16).
    fil_sel/color_sel: nhua NGUOI DUNG chon -> so sanh 3 che do dung CUNG nhua voi
    phan tich process (tran mvs/nhiet theo cuon do — #3 2026-07-19).
    Che do nao VUOT NGAN SACH (+1h30 so voi default, do bang total_predication =
    so GUI) thi tu CAT theo trim_ladder + slice lai den khi lot — moi buoc cat ghi
    ro da cat gi va tiet kiem BAO NHIEU do that.
    """
    os.makedirs(workdir, exist_ok=True)
    name = os.path.splitext(os.path.basename(src))[0]
    rep: dict = {"name": name, "modes": {}, "plate": plate}

    if src.lower().endswith(".stl"):
        import stl_to_3mf
        base = os.path.join(workdir, name + "__base.3mf")
        rep["mesh_from_stl"] = stl_to_3mf.wrap(src, base)
    else:
        base = os.path.join(workdir, name + "__base.3mf")
        shutil.copyfile(src, base)

    ok, res, st = slicer_cli.slice_3mf(base, os.path.join(workdir, "b0"), plate=plate)
    if not ok:
        return {"error": res}
    rep["baseline"] = {**st, "secs": st.get("total_secs") or _secs(st.get("time"))}

    an = analyzer.analyze(base, plate=plate, fil_sel=fil_sel, color_sel=color_sel)
    rep["analysis"] = {k: an.get(k) for k in
                       ("mesh", "flow", "variable_layer", "issues", "rotations")}
    rep["fil_sel"] = an.get("fil_sel")     # nhua dan dat so sanh -> UI hien ro

    b = rep["baseline"]
    tgt = (b["secs"] + BUDGET_S) if b.get("secs") else None        # muc tieu +1h30
    cap = (tgt + BUDGET_TOL_S) if tgt else None                    # sai so den +2h
    rep["budget"] = {"budget_s": BUDGET_S, "tol_s": BUDGET_TOL_S,
                     "target_secs": tgt, "cap_secs": cap}

    for mi, mode in enumerate(modes):
        ex = an["presets"][mode]
        p = dict(ex["preset"])
        f3 = os.path.join(workdir, f"{name}__{mode}.3mf")
        apply_preset(base, f3, p)
        ok2, res2, st2 = slicer_cli.slice_3mf(f3, os.path.join(workdir, f"m{mi}"),
                                              plate=plate)
        if not ok2:
            rep["modes"][mode] = {"error": res2}
            continue
        s2 = st2.get("total_secs") or _secs(st2.get("time"))

        # === GUARD NGAN SACH: vuot cap -> cat tung buoc theo gia do that ===
        trims: list[dict] = []
        # Chot an toan: moi buoc ladder ap xong deu tu bien mat khoi ladder, nhung
        # van can can tren phong sau nay sua ladder vo tinh tao buoc khong-tu-tat
        # (review MEDIUM-4) — moi vong = 1 lan slice CLI that, khong duoc quay vo han.
        for _guard in range(10):
            if not (cap and s2 and s2 > cap):
                break
            steps = trim_ladder(p)
            if not steps:
                break                        # het cai duoc phep cat (lever ky thuat giu)
            desc, changes = steps[0]
            p.update(changes)
            apply_preset(base, f3, p)
            ok3, res3, st3 = slicer_cli.slice_3mf(f3, os.path.join(workdir, f"m{mi}"),
                                                  plate=plate)
            if not ok3:
                trims.append({"step": desc, "error": res3})
                break
            s3 = st3.get("total_secs") or _secs(st3.get("time"))
            trims.append({"step": desc, "before_secs": s2, "after_secs": s3,
                          "saved_secs": (s2 - s3) if s2 and s3 else None})
            res2, st2, s2 = res3, st3, s3

        # Tu van khong cung nhac: lot muc tieu thi im; vuot muc tieu nhung trong
        # sai so thi GIU chat luong va noi ro; chi khi vuot sai so moi da cat o tren.
        note = None
        if tgt and s2:
            if s2 <= tgt:
                pass
            elif s2 <= cap:
                note = (f"Vượt mục tiêu +1h30 ({_hm(s2 - b['secs'])} so với default) nhưng "
                        f"trong sai số +2h bạn cho phép — GIỮ nguyên chất lượng, không cắt.")
            elif trims:
                # Nhanh nay chi vao khi s2 VAN > cap sau khi da cat het — noi that,
                # dung nhan "da ve trong sai so" (review HIGH-2: note cu noi doi).
                note = (f"Đã cắt {len(trims)} bước theo giá đo thật nhưng VẪN vượt sai số +2h "
                        f"({_hm(s2 - b['secs'])} so với default) — phần còn lại toàn lever kỹ thuật "
                        f"(warping/kéo sợi/vật cao/brim/support), giữ nguyên theo ưu tiên của bạn.")
            else:
                note = (f"Vượt sai số +2h ({_hm(s2 - b['secs'])} so với default) nhưng không có "
                        f"gì cắt được ngoài lever kỹ thuật — giữ nguyên theo ưu tiên của bạn.")
        rep["modes"][mode] = {
            **st2, "secs": s2, "label": ex["mode_label"], "why": ex["why"],
            "preset": p, "file": res2,
            "budget": {"target_secs": tgt, "cap_secs": cap,
                       "fits": bool(cap and s2 and s2 <= cap),
                       "within_target": bool(tgt and s2 and s2 <= tgt),
                       "over_secs": max(0, s2 - cap) if cap and s2 else None,
                       "note": note, "trims": trims},
            "time_pct": round((1 - s2 / b["secs"]) * 100, 1) if s2 and b.get("secs") else None,
            "weight_pct": round((1 - st2["weight_g"] / b["weight_g"]) * 100, 1)
                          if st2.get("weight_g") and b.get("weight_g") else None,
        }
    return rep


def run(src: str, workdir: str) -> dict:
    """Chay E2E. Tra bao cao day du (JSON-safe)."""
    os.makedirs(workdir, exist_ok=True)
    name = os.path.splitext(os.path.basename(src))[0]
    rep: dict = {"name": name, "steps": []}

    # --- 1. STL -> 3MF (mang config baseline AUTO-balanced-0.20mm) ---
    if src.lower().endswith(".stl"):
        import stl_to_3mf
        base_3mf = os.path.join(workdir, name + "__base.3mf")
        rep["mesh_from_stl"] = stl_to_3mf.wrap(src, base_3mf)
        rep["steps"].append("STL → bọc vào khung 3MF (config AUTO-balanced-0.20mm)")
    else:
        base_3mf = os.path.join(workdir, name + "__base.3mf")
        shutil.copyfile(src, base_3mf)
        rep["steps"].append("Dùng config có sẵn trong file .3mf")

    # --- 2. Slice VONG 1: BASELINE ---
    ok, res, st = slicer_cli.slice_3mf(base_3mf, os.path.join(workdir, "b1"))
    if not ok:
        rep["error"] = f"Slice baseline lỗi: {res}"
        return rep
    rep["baseline"] = {**st, "secs": _secs(st.get("time"))}
    rep["steps"].append(f"Slice BASELINE → {st.get('time')} · {st.get('weight_g')}g · {st.get('layers')} lớp")

    # --- 3. Phan tich ---
    an = analyzer.analyze(base_3mf)
    rep["analysis"] = {k: an.get(k) for k in
                       ("mesh", "rotations", "flow", "variable_layer", "config", "issues", "tips")}
    preset = an["export"]["preset"]
    rep["why"] = an["export"]["why"]
    rep["preset"] = preset
    rep["steps"].append(f"Phân tích → {len(an['issues'])} vấn đề")

    # --- 4+5. Ap preset -> Slice VONG 2 ---
    opt_3mf = os.path.join(workdir, name + "__opt.3mf")
    apply_preset(base_3mf, opt_3mf, preset)
    ok2, res2, st2 = slicer_cli.slice_3mf(opt_3mf, os.path.join(workdir, "b2"))
    if not ok2:
        rep["error_opt"] = f"Slice tối ưu lỗi: {res2}"
        return rep
    rep["optimized"] = {**st2, "secs": _secs(st2.get("time"))}
    rep["steps"].append(f"Slice TỐI ƯU → {st2.get('time')} · {st2.get('weight_g')}g · {st2.get('layers')} lớp")
    rep["out_file"] = res2

    # --- 6. Doi chieu bang SO THAT ---
    b, o = rep["baseline"], rep["optimized"]
    d: dict = {}
    if b.get("secs") and o.get("secs"):
        d["secs"] = b["secs"] - o["secs"]
        d["time_pct"] = round((1 - o["secs"] / b["secs"]) * 100, 1)
        d["time_text"] = f"{_hm(b['secs'])} → {_hm(o['secs'])}"
    if b.get("weight_g") and o.get("weight_g"):
        d["weight_g"] = round(b["weight_g"] - o["weight_g"], 2)
        d["weight_pct"] = round((1 - o["weight_g"] / b["weight_g"]) * 100, 1)
    if b.get("layers") and o.get("layers"):
        d["layers"] = b["layers"] - o["layers"]
    # Trung thuc: neu toi uu KHONG loi thi noi thang
    d["worth_it"] = bool(d.get("time_pct", 0) > 2 or d.get("weight_pct", 0) > 2)
    rep["delta"] = d
    rep["verdict"] = (
        f"Tối ưu tiết kiệm {d.get('time_pct', 0)}% thời gian "
        f"({d.get('time_text', '?')}) và {d.get('weight_pct', 0)}% nhựa."
        if d["worth_it"] else
        "Cấu hình mặc định đã hợp lý — tối ưu không mang lại lợi ích đáng kể (<2%). Cứ in bản gốc."
    )
    return rep


if __name__ == "__main__":
    import sys
    r = run(sys.argv[1], os.path.join(os.path.dirname(os.path.abspath(__file__)), "slice_jobs", "e2e"))
    print(json.dumps(r, ensure_ascii=False, indent=2)[:4000])
