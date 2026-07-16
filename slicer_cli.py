#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Slice file .3mf bang Bambu Studio CLI (headless), khong can mo giao dien.

Da kiem chung tren Bambu Studio 2.7.1 (2026-07-11):
  bambu-studio.exe --slice 0 --export-3mf <ten-file> --outputdir <dir> <input.3mf>
Quirk cua CLI:
  - --export-3mf phai la TEN FILE TRAN (khong kem duong dan), no tu ghi vao --outputdir;
    dua duong dan tuyet doi vao la loi -13 "Failed exporting 3mf files".
  - Ket qua may/loi nam trong <outputdir>/result.json (return_code 0 = OK).
  - File .3mf dau vao phai co san cau hinh nhung ben trong (project_settings.config) —
    file xuat tu Bambu Studio / OrcaSlicer nao cung co.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import threading
import zipfile

# CLI ngon RAM/CPU nhu mo ca Bambu Studio. UPJOB va OPTJOB la 2 khoa RIENG o tang web
# -> co the kich 2 job cung luc. Khoa DAT TAI DAY dam bao chi 1 tien trinh CLI chay,
# bat ke ai goi.
CLI_LOCK = threading.Lock()

EXE_CANDIDATES = (
    r"D:\Bambu Studio\bambu-studio.exe",
    r"C:\Program Files\Bambu Studio\bambu-studio.exe",
    r"C:\Program Files (x86)\Bambu Studio\bambu-studio.exe",
)


def find_exe() -> str | None:
    p = os.environ.get("BAMBU_STUDIO_EXE")
    if p and os.path.isfile(p):
        return p
    for c in EXE_CANDIDATES:
        if os.path.isfile(c):
            return c
    return None


_TIME_PAT = re.compile(r";\s*model printing time:\s*([^;\n]+)", re.I)
_LAYER_PAT = re.compile(r";\s*total layer number:\s*(\d+)", re.I)
_WEIGHT_PAT = re.compile(r";\s*total filament weight \[g\]\s*:\s*([\d.]+)", re.I)


def stats_from_gcode3mf(path: str, plate: int = 1) -> dict:
    """Doc thoi gian in / so lop / gam nhua tu header G-code trong .gcode.3mf.

    plate: lay dung KHAY nao (1-based).

    BUG DA SUA: truoc day duyet z.namelist() roi lay gcode DAU TIEN gap. Nhung
    --slice 0 = slice HET cac khay, va zip xep NGUOC (plate_3, plate_2, plate_1)
    -> luon bao so cua khay CUOI. Vd BUCKET.3mf: hub bao 1h29m (khay 3, cai de
    be ti) trong khi user in khay 1 that = 3h16m. Moi con so time/gam deu sai khay.
    """
    out: dict = {}
    try:
        z = zipfile.ZipFile(path)
    except (zipfile.BadZipFile, OSError):
        return out
    with z:
        gcodes = sorted(
            (n for n in z.namelist() if re.search(r"Metadata/plate_\d+\.gcode$", n, re.I)),
            key=lambda n: int(re.search(r"plate_(\d+)\.gcode$", n, re.I).group(1)))
        if not gcodes:
            return out
        want = next((n for n in gcodes
                     if int(re.search(r"plate_(\d+)", n, re.I).group(1)) == plate), gcodes[0])
        out["plate"] = int(re.search(r"plate_(\d+)", want, re.I).group(1))
        out["plates_total"] = len(gcodes)
        for n in (want,):
            if True:
                with z.open(n) as fp:
                    head = fp.read(500 * 1024).decode("utf-8", "ignore")
                m = _TIME_PAT.search(head)
                if m:
                    out["time"] = m.group(1).strip()
                m = _LAYER_PAT.search(head)
                if m:
                    out["layers"] = int(m.group(1))
                m = _WEIGHT_PAT.search(head)
                if m:
                    out["weight_g"] = float(m.group(1))
                break
    return out


def slice_3mf(src: str, workdir: str, timeout: int = 1800) -> tuple[bool, str, dict]:
    """Slice `src` -> (ok, duong_dan_gcode3mf_hoac_loi, stats).

    Chi tinh toan tren may tinh — KHONG cham gi toi may in.
    """
    exe = find_exe()
    if not exe:
        return False, "Khong tim thay bambu-studio.exe (dat bien BAMBU_STUDIO_EXE)", {}
    os.makedirs(workdir, exist_ok=True)
    out_name = "sliced.gcode.3mf"
    out_path = os.path.join(workdir, out_name)
    try:
        os.remove(out_path)
    except OSError:
        pass
    try:
        with CLI_LOCK:
            subprocess.run(
                [exe, "--slice", "0", "--export-3mf", out_name,
                 "--outputdir", workdir, src],
                capture_output=True, timeout=timeout, check=False)
    except subprocess.TimeoutExpired:
        return False, f"Slice qua {timeout // 60} phut — huy", {}
    except OSError as e:
        return False, f"Khong chay duoc CLI: {e}", {}

    rc, err = None, ""
    try:
        with open(os.path.join(workdir, "result.json"), encoding="utf-8") as f:
            r = json.load(f)
        rc, err = r.get("return_code"), r.get("error_string") or ""
    except (OSError, ValueError):
        pass
    if rc != 0 or not os.path.isfile(out_path):
        return False, f"Slice loi (return_code={rc}): {err}", {}
    return True, out_path, stats_from_gcode3mf(out_path)


if __name__ == "__main__":
    import sys
    src = sys.argv[1] if len(sys.argv) > 1 else r"D:\123\makep.3mf"
    ok, res, st = slice_3mf(src, os.path.join(os.path.dirname(src), "out_cli"))
    print("ok =", ok)
    print("res =", res)
    print("stats =", st)
