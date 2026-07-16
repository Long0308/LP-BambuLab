#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""A/B slice tung LEVER tren 1 KHAY chi dinh — SO THAT cho ngan sach thoi gian.

Vi sao ton tai: TODO T1 cam "doan %". Moi quyet dinh cat/giu lever trong preset
phai co gia do bang slice that. Script nay slice baseline + tung variant roi in
bang delta so voi baseline.

Dung: python bench_ab.py <file.3mf> [--plate N] [--only ten1,ten2]
  - File nhieu khay: --plate chon khay de slice so sanh (mac dinh 1).
  - Thoi gian dung total_predication tu result.json — CUNG THANG voi so
    Bambu Studio GUI hien thi (gom flush/moi), khong phai "model printing time".
  - Can nang = TONG moi filament trong header gcode (file da mau co n so).
"""
from __future__ import annotations

import argparse
import os
import sys

import analyzer
import optimize_e2e
import slicer_cli

# --- Cac lever don le, ap len config DEFAULT nhung trong file (khong qua mode) ---
# Ten lever -> preset overrides. Gia tri list vi apply_preset tu nhan doi theo config cu.
LEVERS: dict[str, dict] = {
    # 1. Support — dung block y het make_preset sinh cho model hop/phang (normal auto,
    #    chi tu ban, interface cung vat lieu Z 0.2). Nguon ton gio #1 theo TODO.
    "support": {
        "enable_support": "1", "support_on_build_plate_only": "1",
        "support_threshold_angle": "30", "support_type": "normal(auto)",
        "support_style": "default", "support_interface_filament": "1",
        "support_top_z_distance": "0.2", "support_bottom_z_distance": "0.2",
        "support_interface_spacing": "0.5",
        "support_interface_pattern": "rectilinear_interlaced",
    },
    # 2. Tuong 2 -> 3
    "walls3": {"wall_loops": "3"},
    # 3. Toc do thanh ngoai / mat tren 200 -> 150
    "outer150": {"outer_wall_speed": "150", "top_surface_speed": "150"},
    # 3b. Toc do ruot/solid ha ve tran luu luong PLA Matte (mvs 12 -> ~138 mm/s)
    "inner138": {"inner_wall_speed": "138", "sparse_infill_speed": "138",
                 "internal_solid_infill_speed": "138"},
    # 4. Vo tren/duoi 5/3 -> 6/4
    "shells64": {"top_shell_layers": "6", "bottom_shell_layers": "4"},
    # 5. Layer height — don bay lon nhat
    "layer016": {"layer_height": "0.16", "initial_layer_print_height": "0.16"},
    "layer028": {"layer_height": "0.28", "initial_layer_print_height": "0.28"},
    # 6. Vat cao: giam gia toc + travel (tall_rules balanced / quality)
    "tall_bal": {"default_acceleration": "4000", "outer_wall_acceleration": "3000",
                 "travel_speed": "380"},
    "tall_qual": {"default_acceleration": "3000", "outer_wall_acceleration": "3000",
                  "travel_speed": "380"},
    # 7. Cac lever tham my le
    "ironing": {"ironing_type": "top"},
    "narrow_top": {"top_surface_line_width": "0.25"},
    "infill12": {"sparse_infill_density": "12%"},
    "arachne": {"wall_generator": "arachne"},
    "adaptcubic": {"sparse_infill_pattern": "adaptivecubic"},
    "sandwich3": {"wall_loops": "3", "wall_sequence": "inner-outer-inner wall"},
}

def slice_plate(src: str, workdir: str, plate: int, timeout: int = 600) -> dict:
    """Slice DUNG 1 khay -> {'secs','weight_g','layers'} hoac {'error'}.

    secs = total_predication (so GUI hien thi); weight/layers tu header gcode
    (slicer_cli da tu cong file da mau).
    """
    ok, res, st = slicer_cli.slice_3mf(src, workdir, timeout=timeout, plate=plate)
    if not ok:
        return {"error": res}
    return {"secs": st.get("total_secs") or 0,
            "weight_g": st.get("weight_g") or 0, "layers": st.get("layers") or 0}


def _hms(s: int) -> str:
    return f"{s // 3600}h{(s % 3600) // 60:02d}m{s % 60:02d}s"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("src")
    ap.add_argument("--plate", type=int, default=1, help="khay de slice so sanh (1-based)")
    ap.add_argument("--only", default="", help="chi chay cac lever nay (phay), them 'modes' de slice 3 che do")
    ap.add_argument("--workdir", default=os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                                      "slice_jobs", "ab"))
    a = ap.parse_args()
    os.makedirs(a.workdir, exist_ok=True)
    only = [s.strip() for s in a.only.split(",") if s.strip()]

    rows: list[tuple[str, dict]] = []
    print(f"== BASELINE (config nhung trong file, khay {a.plate}) ==", flush=True)
    base = slice_plate(a.src, os.path.join(a.workdir, "base"), a.plate)
    rows.append(("baseline", base))
    print("  ", base, flush=True)
    if "error" in base:
        sys.exit(1)

    todo = {k: v for k, v in LEVERS.items() if not only or k in only}
    for name, pre in todo.items():
        v3 = os.path.join(a.workdir, f"v_{name}.3mf")
        optimize_e2e.apply_preset(a.src, v3, pre)
        st = slice_plate(v3, os.path.join(a.workdir, f"w_{name}"), a.plate)
        rows.append((name, st))
        print(f"  {name}: {st}", flush=True)

    if not only or "modes" in only:
        an = analyzer.analyze(a.src, plate=a.plate)
        for mode in ("fast", "balanced", "quality"):
            pre = an["presets"][mode]["preset"]
            v3 = os.path.join(a.workdir, f"m_{mode}.3mf")
            optimize_e2e.apply_preset(a.src, v3, pre)
            st = slice_plate(v3, os.path.join(a.workdir, f"wm_{mode}"), a.plate)
            rows.append((f"mode:{mode}", st))
            print(f"  mode:{mode}: {st}", flush=True)

    b = base.get("secs") or 1
    bw = base.get("weight_g") or 0
    print(f"\n{'variant':<16}{'time':>10}{'d_time':>10}{'d%':>7}{'gram':>9}{'d_g':>8}{'layers':>8}")
    for name, st in rows:
        if "error" in st:
            print(f"{name:<16}  ERROR: {st['error']}")
            continue
        s, w = st.get("secs", 0), st.get("weight_g", 0)
        print(f"{name:<16}{_hms(s):>10}{('+' if s >= b else '-') + _hms(abs(s - b)):>10}"
              f"{(s - b) / b * 100:>+6.1f}%{w:>9.2f}{w - bw:>+8.2f}{st.get('layers', 0):>8}")


if __name__ == "__main__":
    main()