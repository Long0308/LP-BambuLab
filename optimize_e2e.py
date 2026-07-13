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
    "brim_object_gap", "skirt_loops",
    "draft_shield", "enable_arc_fitting", "resolution",
    "ironing_type", "infill_wall_overlap", "initial_layer_speed",
    "initial_layer_print_height", "top_surface_pattern", "top_shell_thickness",
    "top_surface_line_width", "bridge_flow", "bridge_speed",
    "enable_overhang_speed", "overhang_1_4_speed", "overhang_2_4_speed",
    "overhang_3_4_speed", "overhang_4_4_speed", "overhang_totally_speed",
)


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


def run_modes(src: str, workdir: str, modes=("fast", "balanced", "quality")) -> dict:
    """Slice BASELINE + tung che do -> bang so sanh bang SO THAT (khong doan)."""
    os.makedirs(workdir, exist_ok=True)
    name = os.path.splitext(os.path.basename(src))[0]
    rep: dict = {"name": name, "modes": {}}

    if src.lower().endswith(".stl"):
        import stl_to_3mf
        base = os.path.join(workdir, name + "__base.3mf")
        rep["mesh_from_stl"] = stl_to_3mf.wrap(src, base)
    else:
        base = os.path.join(workdir, name + "__base.3mf")
        shutil.copyfile(src, base)

    ok, res, st = slicer_cli.slice_3mf(base, os.path.join(workdir, "b0"))
    if not ok:
        return {"error": res}
    rep["baseline"] = {**st, "secs": _secs(st.get("time"))}

    an = analyzer.analyze(base)
    rep["analysis"] = {k: an.get(k) for k in
                       ("mesh", "flow", "variable_layer", "issues", "rotations")}

    for mi, mode in enumerate(modes):
        ex = an["presets"][mode]
        f3 = os.path.join(workdir, f"{name}__{mode}.3mf")
        apply_preset(base, f3, ex["preset"])
        ok2, res2, st2 = slicer_cli.slice_3mf(f3, os.path.join(workdir, f"m{mi}"))
        if not ok2:
            rep["modes"][mode] = {"error": res2}
            continue
        b = rep["baseline"]
        s2 = _secs(st2.get("time"))
        rep["modes"][mode] = {
            **st2, "secs": s2, "label": ex["mode_label"], "why": ex["why"],
            "preset": ex["preset"], "file": res2,
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
