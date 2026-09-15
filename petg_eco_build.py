# -*- coding: utf-8 -*-
"""Build bo cau hinh PETG ECO (Tinmorry) cho model gia do iPad "tabletipad-pink".

Vi sao script nay ton tai: model la cum co khi (khung voronoi day 3.5mm + worm gear
+ banh rang + vit) — nhua PETG Eco hay keo soi / ket / bong ban. So lieu lay TU
`analyzer.py` (bang FIL_EXPORT["PETG ECO"] da kiem chung), KHONG bia.

Xuat ra OUT/:
  1.Filament/LP_PETG_Eco_FILAMENT.json                — import tab Filament
  2.Process/LP_PETG_Eco_{FAST,BALANCED,QUALITY}.json  — import tab Process
  tablet-ipad-pink-PETG-Eco.3mf                       — project nhung config PETG Eco

Ghi config bang cach sua THANG Metadata/project_settings.config trong .3mf
(--load-settings cua CLI khong chay: return_code -5).

Chay: python petg_eco_build.py
"""
from __future__ import annotations

import copy
import json
import os
import re
import zipfile

import analyzer
from optimize_e2e import SAFE_KEYS

HERE = os.path.dirname(os.path.abspath(__file__))
BASE = os.path.join(HERE, "slice_jobs", "e2e", "opt_tabletipad-pink__base.3mf")
OUT = os.path.join(HERE, "PETG-Eco-tabletipad")

FIL = "PETG ECO"                       # ten trong bang FIL_EXPORT cua analyzer
MODES = ("fast", "balanced", "quality")
CFG = "Metadata/project_settings.config"
MS = "Metadata/model_settings.config"

# KHE AMS THAT cua cuon PETG gray (user khai 2026-09-13) + cung la FILAMENT SLOT
# ma project "tabletipad-pink" dang gan cho main_voronoi + 2 Generic-Cube.
# Ep MOI object ve slot nay -> file va AMS khop 1:1, khong phu thuoc auto-map.
TARGET_SLOT = 4

# ---- Key FILAMENT ghi de cho MOI khe (ca 6 khe -> cung 1 cuon PETG Eco) ----
# Nguon so: analyzer.FIL_EXPORT["PETG ECO"]["safe"] + cac key chong keo soi
# (wipe/z_hop) ma file goc dang de "nil" (ke thua default PLA).
ECO_PER_FIL = {
    "filament_type": "PETG",
    "filament_settings_id": "LP-PETG-Eco-safe",
    "filament_ids": "GFG02",              # Bambu PETG Basic (profile ma Eco ke thua)
    # CUON THAT cua user nam o AMS KHE 4, mau GRAY (#808080). Set HET 6 khe cung
    # mau/loai -> (a) Studio auto-map ve dung khe 4 khi gui lenh, (b) banner in
    # bang 'use_ams' + ams_mapping=[3] trong hub cung tro dung 1 cuon.
    "filament_colour": "#808080",
    "nozzle_temperature": "240",
    "nozzle_temperature_initial_layer": "240",
    "nozzle_temperature_range_low": "230",
    "nozzle_temperature_range_high": "270",
    # 12, KHONG phai 14: ban in THAT ngay 13/09 bi ket nhua o mvs 14
    # (tuong/ruot 161mm/s = 13.5mm3/s sat tran -> banh rang extruder nghien soi).
    # Ha ve 12 thi moi toc do tu tut theo (Xem analyzer.FIL_EXPORT["PETG ECO"]["why"]).
    "filament_max_volumetric_speed": "12",
    "filament_flow_ratio": "0.94",
    "filament_density": "1.27",
    "hot_plate_temp": "80",
    "hot_plate_temp_initial_layer": "80",
    "textured_plate_temp": "80",
    "textured_plate_temp_initial_layer": "80",
    "eng_plate_temp": "80",
    "eng_plate_temp_initial_layer": "80",
    "supertack_plate_temp": "80",
    "supertack_plate_temp_initial_layer": "80",
    "filament_retraction_length": "1.2",
    "filament_retraction_speed": "30",
    "filament_wipe": "1",
    "filament_wipe_distance": "2",
    "filament_z_hop": "0.4",
    "close_fan_the_first_x_layers": "1",
    "fan_min_speed": "30",
    "fan_max_speed": "50",
    "overhang_fan_speed": "100",
}


def _as_list(old, val):
    """Gia tri per-filament: giu DUNG so khe cua file (6), set het cung gia tri."""
    if isinstance(old, list) and old:
        return [val] * len(old)
    return [val]


def build_filament_preset() -> dict:
    p = copy.deepcopy(analyzer.filament_preset(FIL)["preset"])
    name = "LP-PETG-Eco-safe"
    p["name"] = name
    p["filament_settings_id"] = [name]
    # key chong keo soi khong nam trong bang "safe" -> bo sung tuong minh
    p["filament_wipe"] = ["1"]
    p["filament_wipe_distance"] = ["2"]
    p["filament_z_hop"] = ["0.4"]
    p["fan_min_speed"] = ["30"]
    p["fan_max_speed"] = ["50"]
    p["overhang_fan_speed"] = ["100"]
    p["filament_density"] = ["1.27"]
    return p


def build_process_presets() -> dict:
    """3 che do cho KHAY 3 (tam voronoi — khay kho nhat: chi 46% dien tich bam ban)."""
    r = analyzer.analyze(BASE, mode="balanced", ams=[FIL], plate=3, fil_sel=FIL)
    out = {}
    for m in MODES:
        ex = analyzer.make_preset(r, mode=m, emit_tips=False)
        p = copy.deepcopy(ex["preset"])
        name = f"LP-PETG-Eco-{m.capitalize()}-{p['layer_height']}mm"
        p["name"] = name
        p["print_settings_id"] = name
        out[m] = p
    return out


def write_preset(path: str, obj: dict) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)


def build_3mf(dst: str, process: dict, extra_cfg: dict | None = None) -> dict:
    """Ghi config PETG Eco vao project_settings nhung trong .3mf.

    Tra ve dict tom tat cac thay doi de kiem chung.
    """
    changed = {"filament": {}, "process": {}}
    with zipfile.ZipFile(BASE) as zin:
        cfg = json.loads(zin.read(CFG).decode("utf-8", "ignore"))
        ms = zin.read(MS).decode("utf-8", "ignore")
        # 0) ep MOI object ve TARGET_SLOT (khop layout that trong Studio cua user:
        #    Plate 3 = main_voronoi.stl + 2 Generic-Cube, "Fila." = 4)
        ms_new, n_swap = re.subn(r'(<metadata key="extruder" value=")(\d+)(")',
                                 lambda m: m.group(1) + str(TARGET_SLOT) + m.group(3), ms)
        changed["object_extruder"] = f"{n_swap} object -> filament {TARGET_SLOT}"
        # 1) per-filament: moi khe -> PETG Eco
        for k, v in ECO_PER_FIL.items():
            old = cfg.get(k)
            cfg[k] = _as_list(old, v)
            changed["filament"][k] = f"{old} -> {cfg[k]}"
        # 2) process: chi ghi key nam trong SAFE_KEYS (ghi key la lam CLI -51)
        for k, v in process.items():
            if k not in SAFE_KEYS:
                continue
            old = cfg.get(k)
            if isinstance(old, list) and not isinstance(v, list):
                v = [v] * max(len(old), 1)
            cfg[k] = v
            changed["process"][k] = f"{old} -> {v}"
        for k, v in (extra_cfg or {}).items():
            old = cfg.get(k)
            cfg[k] = _as_list(old, v) if isinstance(old, list) else v
            changed["process"][k] = f"{old} -> {cfg[k]}"
        # 3) ten hien thi
        cfg["print_settings_id"] = process.get("print_settings_id", "")
        with zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED) as zout:
            for it in zin.infolist():
                if it.filename.lower() == "metadata/layer_heights_profile.txt":
                    continue                      # go Variable Layer Height
                if it.filename == CFG:
                    zout.writestr(it, json.dumps(cfg, indent=4, ensure_ascii=False))
                elif it.filename == MS:
                    zout.writestr(it, ms_new)
                else:
                    zout.writestr(it, zin.read(it.filename))
    return changed


def main():
    print("=" * 74)
    print("BASE :", BASE)
    print("NHUA :", FIL, "->", analyzer.FIL_EXPORT[FIL]["inherits"])
    for k in ("nozzle_temperature", "filament_max_volumetric_speed",
              "filament_flow_ratio", "hot_plate_temp",
              "filament_retraction_length", "filament_retraction_speed"):
        print(f"       {k:34} = {analyzer.FIL_EXPORT[FIL]['safe'][k]}")
    print("=" * 74)

    fp = build_filament_preset()
    write_preset(os.path.join(OUT, "1.Filament", "LP_PETG_Eco_FILAMENT.json"), fp)
    print("[ok] 1.Filament/LP_PETG_Eco_FILAMENT.json")

    procs = build_process_presets()
    for m, p in procs.items():
        write_preset(os.path.join(OUT, "2.Process",
                                  f"LP_PETG_Eco_{m.upper()}.json"), p)
        print(f"[ok] 2.Process/LP_PETG_Eco_{m.upper()}.json   layer={p['layer_height']} "
              f"walls={p['wall_loops']} inner={p['inner_wall_speed']} "
              f"top={p['top_surface_speed']} brim={p['brim_width']}")

    dst = os.path.join(OUT, "tablet-ipad-pink-PETG-Eco.3mf")
    ch = build_3mf(dst, procs["balanced"])
    print(f"[ok] {os.path.relpath(dst, HERE)}  ({os.path.getsize(dst)/1e6:.2f} MB)")
    print("\n--- " + ch["object_extruder"] + " ---")
    print("\n--- FILAMENT thay doi ---")
    for k, v in ch["filament"].items():
        print(f"  {k:34} {v[:110]}")
    print("\n--- PROCESS thay doi ---")
    for k, v in ch["process"].items():
        print(f"  {k:34} {str(v)[:110]}")
    return dst


if __name__ == "__main__":
    main()
