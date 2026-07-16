#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""GOLD SET: chay run_modes (baseline + 3 che do + guard ngan sach +1h30) tren
TOAN BO file in duoc (.3mf/.stl) trong 1 thu muc — bang SO THAT tung file.

Muc dich: bo chuan hoi quy. Moi dong ket qua ghi ngay vao gold_results.jsonl
(checkpoint — chay lai tu dong bo qua file da xong). Cuoi cung xuat bang tong
ket markdown.

Dung: python gold_run.py [--dir <thu-muc>] [--out <out-dir>] [--limit N]
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import time
import traceback

import optimize_e2e


def _hms(s) -> str:
    if not s:
        return "?"
    s = int(s)
    return f"{s // 3600}h{(s % 3600) // 60:02d}m"


def run_one(src: str, work: str) -> dict:
    """1 file -> dong ket qua gon (JSON-safe, khong mang preset day du)."""
    row: dict = {"file": os.path.basename(src),
                 "size_mb": round(os.path.getsize(src) / 1e6, 1)}
    t0 = time.time()
    try:
        rep = optimize_e2e.run_modes(src, work)
        if rep.get("error"):
            row["error"] = rep["error"]
            return row
        b = rep["baseline"]
        row["baseline"] = {"secs": b.get("secs"), "weight_g": b.get("weight_g"),
                           "layers": b.get("layers")}
        row["cap_secs"] = (rep.get("budget") or {}).get("cap_secs")
        row["modes"] = {}
        for m, d in rep["modes"].items():
            if "error" in d:
                row["modes"][m] = {"error": d["error"]}
                continue
            bud = d.get("budget") or {}
            row["modes"][m] = {
                "secs": d.get("secs"), "weight_g": d.get("weight_g"),
                "fits": bud.get("fits"), "over_secs": bud.get("over_secs"),
                "trims": [t.get("step") for t in bud.get("trims") or []],
            }
    except Exception as e:                                 # noqa: BLE001
        row["error"] = f"{type(e).__name__}: {e}"
        row["trace"] = traceback.format_exc()[-800:]
    finally:
        row["wall_s"] = int(time.time() - t0)
    return row


def summary_md(rows: list, path: str) -> None:
    L = ["# GOLD SET — run_modes + guard ngân sách (số thật)", "",
         f"> {time.strftime('%Y-%m-%d %H:%M')} · {len(rows)} file · "
         f"budget = default + {optimize_e2e.BUDGET_S // 60}m mục tiêu "
         f"(+{optimize_e2e.BUDGET_TOL_S // 60}m sai số)", "",
         "| File | Base | Nhanh | Cân bằng | Đẹp | Cắt (Đẹp) | Lỗi |",
         "|---|---|---|---|---|---|---|"]
    for r in rows:
        if r.get("error"):
            L.append(f"| {r['file']} | — | — | — | — | — | {r['error'][:80]} |")
            continue
        b = r.get("baseline") or {}
        cells, trims_q, err = [], "", ""
        for m in ("fast", "balanced", "quality"):
            d = (r.get("modes") or {}).get(m) or {}
            if "error" in d:
                cells.append("lỗi")
                err = d["error"][:60]
                continue
            mark = "✅" if d.get("fits") else ("⚠️" if d.get("over_secs") else "")
            cells.append(f"{_hms(d.get('secs'))}{mark}")
            if m == "quality":
                trims_q = str(len(d.get("trims") or []))
        L.append(f"| {r['file']} | {_hms(b.get('secs'))} | " + " | ".join(cells) +
                 f" | {trims_q} | {err} |")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(L) + "\n")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default=r"C:\Users\Admin\Downloads")
    ap.add_argument("--out", default=os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "slice_jobs", "gold"))
    ap.add_argument("--limit", type=int, default=0)
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    work = os.path.join(a.out, "work")
    jl = os.path.join(a.out, "gold_results.jsonl")

    done = set()
    if os.path.isfile(jl):
        with open(jl, encoding="utf-8") as f:
            for line in f:
                try:
                    done.add(json.loads(line)["file"])
                except (ValueError, KeyError):
                    pass

    files = sorted(glob.glob(os.path.join(a.dir, "*.3mf")) +
                   glob.glob(os.path.join(a.dir, "*.stl")),
                   key=os.path.getsize)          # nho truoc -> co ket qua som
    if a.limit:
        files = files[:a.limit]
    print(f"GOLD SET: {len(files)} file, da xong {len(done)}", flush=True)

    rows: list = []
    for i, src in enumerate(files, 1):
        name = os.path.basename(src)
        if name in done:
            continue
        print(f"[{i}/{len(files)}] {name} ({os.path.getsize(src) // 1024}KB)…", flush=True)
        row = run_one(src, work)
        with open(jl, "a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")
        st = ("ERR " + row["error"][:70]) if row.get("error") else " ".join(
            f"{m}={_hms((row['modes'].get(m) or {}).get('secs'))}"
            f"{'✅' if (row['modes'].get(m) or {}).get('fits') else '❌'}"
            for m in ("fast", "balanced", "quality") if row.get("modes"))
        print(f"    -> {st}  ({row['wall_s']}s)", flush=True)
        # don 3mf trung gian cua file nay (giu jsonl thoi — 80 file x vai chuc MB)
        stem = os.path.splitext(name)[0]
        for g in glob.glob(os.path.join(work, glob.escape(stem) + "__*.3mf")):
            try:
                os.remove(g)
            except OSError:
                pass

    with open(jl, encoding="utf-8") as f:
        rows = [json.loads(x) for x in f if x.strip()]
    summary_md(rows, os.path.join(a.out, "GOLD-SET.md"))
    print(f"XONG: {len(rows)} dong -> {os.path.join(a.out, 'GOLD-SET.md')}", flush=True)


if __name__ == "__main__":
    main()