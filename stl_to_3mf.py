#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Boc file STL vao khung 3MF Bambu (co san cau hinh A1) de CLI slice duoc.

Vi sao khong dua STL thang cho CLI: --load-settings doi 3 file config FULL
(machine/process/filament) tach roi, vi du tren wiki lai cho may P2S — sai la
segfault. Boc vao template 3MF (da slice OK tren may nay) thi dung 100% cau hinh
A1 + PLA da kiem chung.

Template: slice_template.3mf = project 3MF that (A1, PLA, toc do da toi uu)
bo phan hinh hoc + anh. Chi ~70KB, sinh boi build_template().
"""
from __future__ import annotations

import math
import os
import re
import struct
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
TEMPLATE = os.path.join(HERE, "slice_template.3mf")

OBJ_PATH = "3D/Objects/object_1.model"
ASM_PATH = "3D/3dmodel.model"
MS_PATH = "Metadata/model_settings.config"


def build_template(src_3mf: str) -> str:
    """Tao slice_template.3mf tu 1 project 3MF da slice OK (bo geometry + anh)."""
    zin = zipfile.ZipFile(src_3mf)
    with zipfile.ZipFile(TEMPLATE, "w", zipfile.ZIP_DEFLATED) as zout:
        for it in zin.infolist():
            low = it.filename.lower()
            if low == OBJ_PATH.lower() or low.endswith(".png"):
                continue
            if "layer_heights_profile" in low or ".gcode" in low:
                continue
            zout.writestr(it, zin.read(it.filename))
    zin.close()
    return TEMPLATE


def parse_stl(path: str):
    """Doc STL (binary hoac ASCII) -> list tam giac [(v1,v2,v3), ...] moi v=(x,y,z)."""
    with open(path, "rb") as f:
        head = f.read(84)
        if len(head) < 84:
            raise ValueError("File STL qua ngan")
        n = struct.unpack("<I", head[80:84])[0]
        size = os.path.getsize(path)
        if size == 84 + n * 50:                      # binary STL chuan
            tris = []
            data = f.read()
            for i in range(n):
                o = i * 50 + 12                      # bo normal 12 byte
                v = struct.unpack("<9f", data[o:o + 36])
                tris.append(((v[0], v[1], v[2]), (v[3], v[4], v[5]), (v[6], v[7], v[8])))
            return tris
    # ASCII STL
    txt = open(path, encoding="utf-8", errors="ignore").read()
    vs = re.findall(r"vertex\s+([-\d.eE+]+)\s+([-\d.eE+]+)\s+([-\d.eE+]+)", txt)
    if len(vs) < 3 or len(vs) % 3:
        raise ValueError("Khong doc duoc STL (khong phai binary chuan/ASCII)")
    pts = [(float(a), float(b), float(c)) for a, b, c in vs]
    return [tuple(pts[i:i + 3]) for i in range(0, len(pts), 3)]


def analyze(tris) -> dict:
    """Kich thuoc + overhang% (mat huong xuong >45deg, khong cham ban)."""
    xs = [v[0] for t in tris for v in t]
    ys = [v[1] for t in tris for v in t]
    zs = [v[2] for t in tris for v in t]
    zmin = min(zs)
    cos45 = math.cos(math.radians(45))
    tot = over = 0.0
    for p, q, r in tris:
        ux, uy, uz = q[0]-p[0], q[1]-p[1], q[2]-p[2]
        vx, vy, vz = r[0]-p[0], r[1]-p[1], r[2]-p[2]
        nx, ny, nz = uy*vz-uz*vy, uz*vx-ux*vz, ux*vy-uy*vx
        length = math.sqrt(nx*nx + ny*ny + nz*nz)
        if not length:
            continue
        a = length / 2
        tot += a
        if nz/length < -cos45 and max(p[2], q[2], r[2]) - zmin > 0.3:
            over += a
    return {"dims": [round(max(xs)-min(xs), 1), round(max(ys)-min(ys), 1),
                     round(max(zs)-min(zs), 1)],
            "triangles": len(tris),
            "overhang_pct": round(over/tot*100, 1) if tot else 0.0}


def wrap(stl_path: str, out_3mf: str) -> dict:
    """STL -> 3MF project (template A1) san sang slice. Tra ve ket qua analyze()."""
    if not os.path.isfile(TEMPLATE):
        raise FileNotFoundError("Thieu slice_template.3mf — chay build_template() truoc")
    tris = parse_stl(stl_path)
    if not tris:
        raise ValueError("STL rong")
    info = analyze(tris)

    # Doi mesh ve TAM (0,0,0): build item se dat vao giua ban (128,128,cao/2)
    xs = [v[0] for t in tris for v in t]; ys = [v[1] for t in tris for v in t]
    zs = [v[2] for t in tris for v in t]
    cx, cy, cz = (min(xs)+max(xs))/2, (min(ys)+max(ys))/2, (min(zs)+max(zs))/2
    h2 = (max(zs)-min(zs))/2

    verts: dict = {}
    order = []
    faces = []
    for t in tris:
        idx = []
        for v in t:
            key = (round(v[0]-cx, 4), round(v[1]-cy, 4), round(v[2]-cz, 4))
            i = verts.get(key)
            if i is None:
                i = len(order)
                verts[key] = i
                order.append(key)
            idx.append(i)
        if idx[0] != idx[1] and idx[1] != idx[2] and idx[0] != idx[2]:
            faces.append(idx)

    parts = ['<?xml version="1.0" encoding="UTF-8"?>\n'
             '<model unit="millimeter" xml:lang="en-US" '
             'xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02" '
             'xmlns:BambuStudio="http://schemas.bambulab.com/package/2021" '
             'xmlns:p="http://schemas.microsoft.com/3dmanufacturing/production/2015/06" '
             'requiredextensions="p">\n'
             ' <metadata name="BambuStudio:3mfVersion">1</metadata>\n <resources>\n'
             '  <object id="1" p:UUID="00010000-81cb-4c03-9d28-80fed5dfa1dc" type="model">\n'
             '   <mesh>\n    <vertices>\n']
    parts += [f'     <vertex x="{x}" y="{y}" z="{z}"/>\n' for x, y, z in order]
    parts.append('    </vertices>\n    <triangles>\n')
    parts += [f'     <triangle v1="{a}" v2="{b}" v3="{c}"/>\n' for a, b, c in faces]
    parts.append('    </triangles>\n   </mesh>\n  </object>\n </resources>\n</model>\n')
    obj_xml = "".join(parts)

    zin = zipfile.ZipFile(TEMPLATE)
    name = os.path.splitext(os.path.basename(stl_path))[0]
    with zipfile.ZipFile(out_3mf, "w", zipfile.ZIP_DEFLATED) as zout:
        for it in zin.infolist():
            data = zin.read(it.filename)
            if it.filename == ASM_PATH:
                txt = data.decode("utf-8", "ignore")
                txt = re.sub(r'(<item[^>]*transform=")[^"]*(")',
                             rf'\g<1>1 0 0 0 1 0 0 0 1 128 128 {h2:.6f}\g<2>', txt)
                data = txt.encode("utf-8")
            elif it.filename == MS_PATH:
                txt = data.decode("utf-8", "ignore")
                txt = re.sub(r'face_count="\d+"', f'face_count="{len(faces)}"', txt)
                txt = txt.replace("Body_02", name)
                data = txt.encode("utf-8")
            zout.writestr(it, data)
        zout.writestr(OBJ_PATH, obj_xml)
    zin.close()
    return info


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 2 and sys.argv[1] == "build":
        print("template:", build_template(sys.argv[2]))
    elif len(sys.argv) > 1:
        out = sys.argv[1] + ".wrapped.3mf"
        print("analyze:", wrap(sys.argv[1], out))
        print("out:", out)
