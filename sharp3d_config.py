# -*- coding: utf-8 -*-
"""Sinh bo cau hinh PETG an toan chong ket cho thu vien D:\\16.Sharp3D\\Congfig.

VI SAO CO SCRIPT NAY:
  Thu muc Sharp3D la noi chua preset de nguoi dung import vao Bambu Studio. Truoc day
  no duoc sua TAY -> lech han voi analyzer.py: filament ghi mvs 13 (analyzer ep 12),
  con process "SAFE" dat 149 mm/s @0.2mm = 12.5 mm3/s - VUOT tran 12 mm3/s, tuc la
  nam dung vung da lam KET NHUA ngay 13/09 (13.5 mm3/s).
  => Nay sinh TU DONG tu analyzer.py: 1 nguon so duy nhat, khong the lech lai.

Xuat ra (ca 3 CAP toc do deu mang cung bien an toan 85%):
  1.Filament : LP-PETG-ECO-Tinmorry-safe.json + LP-PETG-<mau>-safe.json (giu nguyen mau)
  2.Process  : LP-Process-PETG-{FAST,BALANCED,QUALITY}-<lop>mm-SAFE.json

Chay: python sharp3d_config.py
"""
from __future__ import annotations

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import analyzer                                              # noqa: E402
import petg_eco_build as B                                   # noqa: E402

DEST = r"D:\16.Sharp3D\Congfig\02.Filament_PETG_Matte_Black&Grey"

# Chung keo soi / ket dau in cho PETG.
# 🩸 17/09/2026: wipe 1 -> 2 mm (handover 17/09 + Reddit r/BambuLab: giau to thua
# vao trong ruot). SUA O DAY va o petg_eco_build.ECO_PER_FIL — hai cho phai khop,
# lech mot cho la file xuat ra mang so cu (da bi mot lan voi mvs 14).
ANTI_STRING = {
    "filament_wipe": ["2"],
    "filament_wipe_distance": ["2"],
    "filament_z_hop": ["0.4"],
    "fan_min_speed": ["30"],
    "fan_max_speed": ["50"],
    "overhang_fan_speed": ["100"],
}

# Key LOI lay TU analyzer (1 nguon duy nhat) - ghi de moi lan chay.
CORE = ("nozzle_temperature", "filament_max_volumetric_speed", "filament_flow_ratio",
        "hot_plate_temp", "filament_retraction_length", "filament_retraction_speed",
        "close_fan_the_first_x_layers")


def _fil_key(fname: str) -> str:
    """Chon dong nhua trong FIL_EXPORT theo ten file (eco khac PETG thuong)."""
    up = fname.upper()
    return "PETG ECO" if ("ECO" in up or "TINMORRY" in up) else "PETG BASIC"


def update_filament(path: str) -> dict:
    """Cap nhat 1 file filament: giu mau/ten, ep so an toan tu analyzer."""
    with open(path, encoding="utf-8") as f:
        p = json.load(f)
    key = _fil_key(os.path.basename(path))
    safe = analyzer.FIL_EXPORT[key]["safe"]
    for k in CORE:
        if k in safe:
            p[k] = [safe[k]]
    # lop dau = lop thuong (tranh under-melt lop 1 - nguyen nhan ket som)
    p["nozzle_temperature_initial_layer"] = [safe["nozzle_temperature"]]
    p["hot_plate_temp_initial_layer"] = [safe["hot_plate_temp"]]
    p["textured_plate_temp"] = [safe["hot_plate_temp"]]
    p["textured_plate_temp_initial_layer"] = [safe["hot_plate_temp"]]
    p.update(ANTI_STRING)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(p, f, ensure_ascii=False, indent=4)
    return {k: p[k][0] for k in CORE if k in p}


def build_process() -> dict:
    """3 cap toc do, TAT CA deu theo bien an toan 85% (analyzer.SAFE_MARGIN)."""
    r = analyzer.analyze(B.BASE, mode="balanced", ams=[B.FIL], plate=3, fil_sel=B.FIL)
    lw, mvs = r["flow"]["line_width"], r["flow"]["mvs"]
    out = {}
    for m in ("fast", "balanced", "quality"):
        p = dict(analyzer.make_preset(r, mode=m, emit_tips=False)["preset"])
        lh = float(p["layer_height"])
        name = f"LP-Process-PETG-{m.upper()}-{lh:g}mm-SAFE"
        p["name"] = name
        p["print_settings_id"] = name
        out[m] = (p, lh, float(p["inner_wall_speed"][0]), mvs, lw)
    return out


QD = r"D:\16.Sharp3D\Congfig\LP_QuocDan"

# Key TOC DO / KIỂU RUỘT lấy từ chế độ BALANCED khi ghi đè các file cũ.
SPEED_KEYS = ("layer_height", "inner_wall_speed", "outer_wall_speed", "sparse_infill_speed",
              "internal_solid_infill_speed", "top_surface_speed",
              "sparse_infill_pattern", "wall_sequence")


def update_quocdan(procs: dict) -> list:
    """Cap nhat bo LP_QuocDan (03/08/2026) — dang o THE HE CU, rat nguy hiem.

    🩸 Bo nay ghi filament mvs 14 VA process tuong/ruot 161 mm/s
    (= 13.5 mm3/s voi be rong that 0.45) — DUNG cau hinh da lam KET NHUA ngay 13/09.
    """
    done = []
    # 1) Filament PETG (dung so cua PETG BASIC trong analyzer)
    fp = os.path.join(QD, "1.Filament", "PETG", "LP_PETG_FILAMENT.json")
    if os.path.isfile(fp):
        with open(fp, encoding="utf-8") as f:
            p = json.load(f)
        safe = analyzer.FIL_EXPORT["PETG BASIC"]["safe"]
        for k in CORE:
            if k in safe:
                p[k] = [safe[k]]
        p["nozzle_temperature_initial_layer"] = [safe["nozzle_temperature"]]
        p["hot_plate_temp_initial_layer"] = [safe["hot_plate_temp"]]
        p["textured_plate_temp"] = [safe["hot_plate_temp"]]
        p["textured_plate_temp_initial_layer"] = [safe["hot_plate_temp"]]
        p.update(ANTI_STRING)
        with open(fp, "w", encoding="utf-8") as f:
            json.dump(p, f, ensure_ascii=False, indent=2)
        done.append((r"1.Filament\PETG\LP_PETG_FILAMENT.json",
                     f"mvs={safe['filament_max_volumetric_speed']} "
                     f"ban={safe['hot_plate_temp']} flow={safe['filament_flow_ratio']}"))

    pd = os.path.join(QD, "2.Process_Base", "PETG")
    os.makedirs(pd, exist_ok=True)
    # 2) Ba che do moi
    for m, (p, lh, iw, mvs, lw) in procs.items():
        q = dict(p)
        nm = f"LP_PETG_{m.upper()}"
        q["name"] = nm
        q["print_settings_id"] = nm
        with open(os.path.join(pd, nm + ".json"), "w", encoding="utf-8") as f:
            json.dump(q, f, ensure_ascii=False, indent=2)
        fl = iw * lh * lw * (0.45 / 0.42)
        done.append((rf"2.Process_Base\PETG\{nm}.json",
                     f"trong={iw:.0f} -> {fl:.2f} mm3/s"))
    # 3) Hai file DEFAUT cu -> ghi de toc do/ruot bang so cua BALANCED
    b = procs["balanced"][0]
    for old in ("LP_PETG_DEFAUT.json", "LP_PETG_DEFAUT_IRONING.json"):
        op = os.path.join(pd, old)
        if not os.path.isfile(op):
            continue
        with open(op, encoding="utf-8") as f:
            oc = json.load(f)
        for k in SPEED_KEYS:
            if k in b:
                oc[k] = b[k]
        with open(op, "w", encoding="utf-8") as f:
            json.dump(oc, f, ensure_ascii=False, indent=2)
        done.append((rf"2.Process_Base\PETG\{old}", "cap nhat tu BALANCED"))
    return done


def main() -> int:
    os.makedirs(DEST, exist_ok=True)
    print("=" * 78)
    print("NGUON SO : analyzer.py  (SAFE_MARGIN =",
          f"{analyzer.SAFE_MARGIN}, nguong PETG = {analyzer.FAMILY_SAFE_MVS['PETG']} mm3/s)")
    print("DICH     :", DEST)
    print("=" * 78)

    print("\n--- 1. FILAMENT ---")
    n = 0
    for fn in sorted(os.listdir(DEST)):
        if not (fn.startswith("LP-PETG-") and fn.endswith("-safe.json")):
            continue
        info = update_filament(os.path.join(DEST, fn))
        print(f"  [ok] {fn:36} mvs={info.get('filament_max_volumetric_speed')} "
              f"temp={info.get('nozzle_temperature')} ban={info.get('hot_plate_temp')} "
              f"({_fil_key(fn)})")
        n += 1

    print("\n--- 2. PROCESS (3 cap, cung bien an toan) ---")
    procs = build_process()
    for m, (p, lh, iw, mvs, lw) in procs.items():
        with open(os.path.join(DEST, p["name"] + ".json"), "w", encoding="utf-8") as f:
            json.dump(p, f, ensure_ascii=False, indent=4)
        # Be rong THAT cua tuong trong la 0.45 (Bambu mac dinh), khong phai 0.42 —
        # xem analyzer.make_preset. In theo 0.42 la bao thap hon thuc te.
        fl = iw * lh * lw * (0.45 / 0.42)
        print(f"  [ok] {p['name']:38} trong={iw:.0f} ngoai={p['outer_wall_speed'][0]} "
              f"top={p['top_surface_speed'][0]}  -> {fl:.2f} mm3/s = {fl/mvs*100:.0f}% tran")

    # File cu dat ten theo model - ghi de bang so an toan (truoc day 149 mm/s = 12.5 mm3/s)
    old = os.path.join(DEST, "LP-Process-PETG-tabletipad-Balanced-0.2mm-SAFE.json")
    if os.path.isfile(old):
        p = dict(procs["balanced"][0])
        p["name"] = "LP-PETG-tabletipad-Balanced-0.2mm-SAFE"
        p["print_settings_id"] = "LP-PETG-tabletipad-Balanced-0.2mm-SAFE"
        with open(old, "w", encoding="utf-8") as f:
            json.dump(p, f, ensure_ascii=False, indent=4)
        print(f"  [ok] {'LP-Process-PETG-tabletipad-Balanced-0.2mm-SAFE.json':38} "
              f"(cap nhat: 149 -> {p['inner_wall_speed'][0]} mm/s)")

    print(f"\n  Xong: {n} filament + {len(procs)} process.")

    print("\n" + "=" * 78)
    print("THU VIEN LP_QuocDan :", QD)
    print("=" * 78)
    if os.path.isdir(QD):
        for rel, note in update_quocdan(procs):
            print(f"  [ok] {rel:44} {note}")
    else:
        print("  (khong co thu muc — bo qua)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
