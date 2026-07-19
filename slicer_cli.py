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
import time
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
# File DA MAU ghi nhieu so tren 1 dong, phan cach phay: "106.56,12.77" (khay 1
# BUCKET.3mf = nhua #1 + nhua #3). Regex cu ([\d.]+) dung o dau phay -> chi lay
# nhua dau tien, thieu ~11%. Phai bat ca chuoi roi CONG het.
# [\d., ] (space, KHONG \s): chiu duoc "106.56, 12.77" ma khong an sang dong sau
_WEIGHT_PAT = re.compile(r";\s*total filament weight \[g\]\s*:\s*([\d., ]+)", re.I)


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
                    out["weight_g"] = round(sum(
                        float(x) for x in m.group(1).split(",") if x.strip()), 2)
                break
    return out


def _kill_tree(pid: int) -> None:
    """Kill ca cay process (CLI co the con chau giu handle)."""
    subprocess.run(["taskkill", "/F", "/T", "/PID", str(pid)],
                   capture_output=True, check=False)


def _gui_running() -> bool:
    """Bambu Studio GUI dang mo? CLI dung CHUNG exe voi GUI -> mo GUI luc slice hay
    lam CLI conflict/treo/crash (return_code=None). Detect de bao user DONG Studio."""
    try:
        out = subprocess.run(
            ["tasklist", "/FI", "IMAGENAME eq bambu-studio.exe", "/NH"],
            capture_output=True, text=True, timeout=10, check=False).stdout or ""
        return "bambu-studio.exe" in out.lower()
    except (OSError, subprocess.SubprocessError):
        return False


# Goi y chung khi slice loi return_code=None (nguyen nhan #1 la GUI dang mo).
GUI_HINT = ("Bambu Studio (giao diện) đang MỞ — CLI dùng chung file exe với giao diện "
            "nên slice hay lỗi. ĐÓNG hẳn Bambu Studio rồi bấm lại.")


def slice_3mf(src: str, workdir: str, timeout: int = 1800,
              plate: int = 0, retries: int = 2) -> tuple[bool, str, dict]:
    """Slice `src` -> (ok, duong_dan_gcode3mf_hoac_loi, stats).

    plate: 0 = slice HET cac khay (mac dinh cu); N>0 = chi khay N (--slice N,
    nhanh hon nhieu voi file da khay — dung cho A/B so sanh tung khay).

    Chi tinh toan tren may tinh — KHONG cham gi toi may in.

    2 QUIRK DA GAP THAT (2026-07-16, do A/B BUCKET.3mf):
      - CLI thi thoang TREO O BUOC THOAT sau khi DA ghi xong result.json + file xuat
        (hay gap khi Bambu Studio GUI dang mo cung luc). capture_output pipe lam
        subprocess cho den timeout 30' du viec da xong -> ghi log RA FILE + poll:
        thay du output la kill cay process, lay ket qua.
      - CLI doi khi crash ngau nhien (reslice-benchmark.ps1 cung ghi nhan) -> retry.
    """
    exe = find_exe()
    if not exe:
        return False, "Khong tim thay bambu-studio.exe (dat bien BAMBU_STUDIO_EXE)", {}
    os.makedirs(workdir, exist_ok=True)
    out_name = "sliced.gcode.3mf"
    out_path = os.path.join(workdir, out_name)
    res_path = os.path.join(workdir, "result.json")
    err_last = "?"
    for _try in range(max(1, retries)):
        for p in (out_path, res_path):
            try:
                os.remove(p)
            except OSError:
                pass
        def _read_result():
            """Doc result.json -> dict, hoac None neu chua ghi xong / JSON do dang."""
            try:
                with open(res_path, encoding="utf-8") as f:
                    return json.load(f)
            except (OSError, ValueError):
                return None

        try:
            with CLI_LOCK, open(os.path.join(workdir, "cli.log"), "w") as logf:
                proc = subprocess.Popen(
                    [exe, "--slice", str(plate), "--export-3mf", out_name,
                     "--outputdir", workdir, src],
                    stdout=logf, stderr=subprocess.STDOUT)
                t0 = time.time()
                while proc.poll() is None:
                    if os.path.isfile(res_path) and os.path.isfile(out_path):
                        # CLI hay TREO O BUOC THOAT du da ghi xong. TRUOC day sleep(3)
                        # roi kill ngay -> co luc result.json con do dang -> doc ra
                        # return_code=None GIA (bug that: mode 'quality' fail 2026-07-19).
                        # Nay cho result.json PARSE duoc (co return_code) roi moi kill.
                        for _ in range(12):
                            if proc.poll() is not None:
                                break
                            rr = _read_result()
                            if rr and rr.get("return_code") is not None:
                                break
                            time.sleep(1)
                        if proc.poll() is None:  # van treo du da ghi xong -> quirk 1
                            _kill_tree(proc.pid)
                        break
                    if time.time() - t0 > timeout:
                        _kill_tree(proc.pid)
                        return False, f"Slice qua {timeout // 60} phut — huy", {}
                    time.sleep(1)
        except OSError as e:
            return False, f"Khong chay duoc CLI: {e}", {}

        # result.json co the con dang flush sau khi process thoat/bi kill -> doc lai
        # vai lan truoc khi ket luan loi (chong return_code=None gia do doc som).
        r = None
        for _ in range(6):
            r = _read_result()
            if r is not None:
                break
            time.sleep(1)
        rc, err = (r.get("return_code"), r.get("error_string") or "") if r else (None, "")
        if rc == 0 and os.path.isfile(out_path):
            st = stats_from_gcode3mf(out_path, plate=plate or 1)
            # total_predication = so GUI hien thi (gom flush/moi) — dung de doi chieu
            # ngan sach thoi gian voi so user thay trong Bambu Studio.
            sp = (r.get("sliced_plates") or [{}])[0]
            if sp.get("total_predication"):
                st["total_secs"] = int(sp["total_predication"])
            return True, out_path, st
        err_last = f"return_code={rc}: {err}"     # quirk 2: crash ngau nhien -> retry
        if _try < max(1, retries) - 1:
            time.sleep(5)                          # cho exe ranh truoc khi thu lai
    msg = f"Slice lỗi ({err_last})"
    if _gui_running():                             # nguyen nhan #1: GUI dang mo
        msg += " — " + GUI_HINT
    return False, msg, {}


if __name__ == "__main__":
    import sys
    src = sys.argv[1] if len(sys.argv) > 1 else r"D:\123\makep.3mf"
    ok, res, st = slice_3mf(src, os.path.join(os.path.dirname(src), "out_cli"))
    print("ok =", ok)
    print("res =", res)
    print("stats =", st)
