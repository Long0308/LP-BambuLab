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
    "enable_support", "support_type", "support_style",
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


# ===== NGAN SACH THOI GIAN (user chot 2026-07-16) =====
# Preset khong duoc lam thoi gian in vuot qua DEFAULT (0.20mm Standard @BBL A1)
# qua 1h30m; cho phep sai so nho. So sanh bang total_predication (result.json) —
# CUNG THANG voi so Bambu Studio GUI hien thi (gom flush/moi nhua).
BUDGET_S = 90 * 60
BUDGET_TOL_S = 5 * 60


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
        steps.append((f"Vỏ trên/dưới {tsl}/{bsl} → {max(tsl - 1, 5)}/{max(bsl - 1, 3)} "
                      f"(giá đo 6/4: −6m07s chiều ngược)",
                      {"top_shell_layers": str(max(tsl - 1, 5)),
                       "bottom_shell_layers": str(max(bsl - 1, 3))}))
    # CUOI CUNG moi dung den layer height (danh doi van lop — ban chat che do):
    lh = float(_v1(p.get("layer_height") or 0.2))
    nxt = {0.12: 0.16, 0.16: 0.2, 0.2: 0.24}.get(lh)
    if nxt:
        ch = {"layer_height": f"{nxt:g}"}
        ilh = float(_v1(p.get("initial_layer_print_height") or lh))
        if ilh < nxt:
            ch["initial_layer_print_height"] = f"{nxt:g}"
        # duong in mat tren phai >= layer height, khong la CLI loi -51
        tw = float(_v1(p.get("top_surface_line_width") or 9) or 9)
        if tw < nxt:
            ch["top_surface_line_width"] = "0.42"
        steps.append((f"Layer {lh:g} → {nxt:g}mm (giá đo 0.16→0.20: −45m34s) — bước cuối cùng",
                      ch))
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


def apply_preset(src: str, dst: str, preset: dict, drop_vlh: bool = True) -> None:
    """Ghi preset vao project_settings NHUNG trong .3mf + go Variable Layer Height.

    Phai sua config nhung, KHONG dung --load-settings: CLI doi 3 file config FULL
    tach roi, sai la segfault (BambuStudio issue #9968).
    """
    with zipfile.ZipFile(src) as zin:        # with: khong leak handle khi json/KeyError
        cfg = json.loads(zin.read(CFG).decode("utf-8", "ignore"))
        for k, v in preset.items():
            if k not in SAFE_KEYS:
                continue
            old = cfg.get(k)
            if isinstance(old, list) and not isinstance(v, list):
                v = [v] * max(len(old), 1)   # list rong (config la) -> van set 1 phan tu
            cfg[k] = v
        with zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED) as zout:
            for it in zin.infolist():
                if drop_vlh and it.filename.lower() == VLH:
                    continue                # go Variable Layer Height
                if it.filename == CFG:
                    zout.writestr(it, json.dumps(cfg, indent=4, ensure_ascii=False))
                else:
                    zout.writestr(it, zin.read(it.filename))


def run_modes(src: str, workdir: str, modes=("fast", "balanced", "quality"),
              plate: int = 1) -> dict:
    """Slice BASELINE + tung che do -> bang so sanh bang SO THAT (khong doan).

    plate: khay de slice so sanh (file nhieu khay chon duoc khay — user 2026-07-16).
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

    an = analyzer.analyze(base, plate=plate)
    rep["analysis"] = {k: an.get(k) for k in
                       ("mesh", "flow", "variable_layer", "issues", "rotations")}

    b = rep["baseline"]
    cap = (b["secs"] + BUDGET_S + BUDGET_TOL_S) if b.get("secs") else None
    rep["budget"] = {"budget_s": BUDGET_S, "tol_s": BUDGET_TOL_S, "cap_secs": cap}

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
        while cap and s2 and s2 > cap:
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

        rep["modes"][mode] = {
            **st2, "secs": s2, "label": ex["mode_label"], "why": ex["why"],
            "preset": p, "file": res2,
            "budget": {"cap_secs": cap, "fits": bool(cap and s2 and s2 <= cap),
                       "over_secs": max(0, s2 - cap) if cap and s2 else None,
                       "trims": trims},
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
