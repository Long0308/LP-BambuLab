#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Doc TONG GAM nhua cua ban in dang chay, tu file .gcode.3mf tren may qua FTPS.

HYBRID cho ca Bambu Studio va OrcaSlicer:
  1) Metadata/slice_info.config -> cong tat ca used_g (ca 2 slicer deu ghi). Nho, chac.
  2) Fallback: header trong Metadata/plate_*.gcode, nhieu mau:
       Bambu : "; total filament weight [g] : X"
       Orca  : "; filament used [g] = X"
Bambu FTPS la IMPLICIT TLS tren cong 990, cert tu ky -> phai tat verify.
"""
from __future__ import annotations

import ftplib
import io
import os
import re
import ssl
import sys
import tempfile
import zipfile

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


class ImplicitFTP_TLS(ftplib.FTP_TLS):
    """FTP_TLS boc SSL ngay khi connect (implicit) thay vi AUTH TLS (explicit)."""
    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self._sock = None

    @property
    def sock(self):
        return self._sock

    @sock.setter
    def sock(self, value):
        if value is not None and not isinstance(value, ssl.SSLSocket):
            value = self.context.wrap_socket(value, server_hostname=None)
        self._sock = value


def _connect(host: str, code: str, timeout: float = 20.0) -> ImplicitFTP_TLS:
    ctx = ssl._create_unverified_context()
    ftp = ImplicitFTP_TLS(context=ctx)
    ftp.connect(host, 990, timeout=timeout)
    ftp.login("bblp", code)
    ftp.prot_p()
    return ftp


def _candidates(gcode_file: str) -> list[str]:
    name = (gcode_file or "").lstrip("/")
    base = os.path.basename(name)
    out = []
    for p in (name, base, f"cache/{base}", f"model/{base}"):
        for pref in ("/", ""):
            cand = pref + p
            if cand not in out:
                out.append(cand)
    return out


def _download(host: str, code: str, gcode_file: str) -> bytes | None:
    ftp = None
    try:
        ftp = _connect(host, code)
        for path in _candidates(gcode_file):
            buf = io.BytesIO()
            try:
                ftp.retrbinary("RETR " + path, buf.write)
                data = buf.getvalue()
                if data:
                    return data
            except ftplib.error_perm:
                continue
        return None
    finally:
        if ftp:
            try:
                ftp.quit()
            except Exception:
                pass


_USED_G = re.compile(r'used_g="([\d.]+)"')
_HDR_PATS = (
    re.compile(r"total filament weight \[g\]\s*[:=]\s*([\d.]+)", re.I),
    re.compile(r"filament used \[g\]\s*[:=]\s*([\d.]+)", re.I),
    re.compile(r"total filament used \[g\]\s*[:=]\s*([\d.]+)", re.I),
)


def parse_weight(zip_bytes_or_path) -> float | None:
    """Tra ve tong gam (float) hoac None. Nhan bytes hoac duong dan file zip."""
    try:
        if isinstance(zip_bytes_or_path, (bytes, bytearray)):
            z = zipfile.ZipFile(io.BytesIO(zip_bytes_or_path))
        else:
            z = zipfile.ZipFile(zip_bytes_or_path)
    except (zipfile.BadZipFile, OSError):
        return None
    with z:
        names = z.namelist()
        # 1) slice_info.config — cong used_g (ca Bambu lan Orca)
        for n in names:
            if n.lower().endswith("slice_info.config"):
                try:
                    txt = z.read(n).decode("utf-8", "ignore")
                except Exception:
                    continue
                gs = [float(x) for x in _USED_G.findall(txt)]
                if gs:
                    return round(sum(gs), 2)
        # 2) header cua plate gcode — chi doc dau + cuoi (Orca ghi o cuoi)
        for n in names:
            if re.search(r"Metadata/plate_\d+\.gcode$", n):
                try:
                    with z.open(n) as fp:
                        head = fp.read(256 * 1024).decode("utf-8", "ignore")
                except Exception:
                    continue
                for pat in _HDR_PATS:
                    ms = pat.findall(head)
                    if ms:
                        return round(sum(float(x) for x in ms), 2)
    return None


def list_files(host: str, code: str) -> list:
    """Liet ke cac file .3mf tren may (root + /cache). Chi doc, khong tai."""
    ftp = None
    out = []
    seen = set()
    try:
        ftp = _connect(host, code)
        for d in ("/", "/cache", "/model"):
            try:
                names = ftp.nlst(d)
            except ftplib.error_perm:
                continue
            except Exception:
                continue
            for n in names:
                base = os.path.basename(n.rstrip("/"))
                if not base.lower().endswith(".3mf") or base in seen:
                    continue
                seen.add(base)
                path = n if n.startswith("/") else (d.rstrip("/") + "/" + base)
                size = None
                try:
                    size = ftp.size(path)
                except Exception:
                    pass
                out.append({"name": base, "path": path, "size": size})
        out.sort(key=lambda x: x["name"].lower())
        return out
    finally:
        if ftp:
            try:
                ftp.quit()
            except Exception:
                pass


def parse_thumbnail(zip_path) -> bytes | None:
    """Lay anh preview model (PNG) — uu tien plate_*.png (giong man hinh may)."""
    try:
        z = zipfile.ZipFile(zip_path)
    except (zipfile.BadZipFile, OSError):
        return None
    with z:
        names = [n for n in z.namelist() if n.lower().endswith(".png")]
        def rank(n):
            low = n.lower()
            if "plate_no_light" in low or "top_" in low or "pick_" in low:
                return 3
            if re.search(r"plate_\d+\.png$", low):
                return 0        # anh render dep nhat
            if "thumbnail" in low:
                return 1
            return 2
        for n in sorted(names, key=rank):
            try:
                b = z.read(n)
                if b and len(b) > 500:      # bo qua icon rong
                    return b
            except Exception:
                continue
    return None


_CMD_RE = re.compile(r"^([GMT]\d+)")


def parse_job_info(zip_path) -> dict:
    """Boc toan bo thong so + thong ke lenh G-code tu file .gcode.3mf."""
    info = {"config": None, "slice": {}, "commands": {}, "header": []}
    try:
        z = zipfile.ZipFile(zip_path)
    except (zipfile.BadZipFile, OSError):
        return info
    with z:
        names = z.namelist()
        # 1) project_settings.config — toan bo (~500 key)
        for n in names:
            if n.lower().endswith("project_settings.config"):
                try:
                    import json as _json
                    info["config"] = _json.loads(z.read(n).decode("utf-8", "ignore"))
                except Exception:
                    pass
                break
        # 2) slice_info.config — khoi luong / chieu dai / thoi gian du bao
        for n in names:
            if n.lower().endswith("slice_info.config"):
                txt = z.read(n).decode("utf-8", "ignore")
                gs = [float(x) for x in re.findall(r'used_g="([\d.]+)"', txt)]
                if gs:
                    info["slice"]["weight_g"] = round(sum(gs), 2)
                ms = [float(x) for x in re.findall(r'used_m="([\d.]+)"', txt)]
                if ms:
                    info["slice"]["length_m"] = round(sum(ms), 2)
                pr = re.search(r'key="prediction"\s+value="(\d+)"', txt)
                if pr:
                    info["slice"]["time_s"] = int(pr.group(1))
                break
        # 3) plate gcode: dong header (; key = value) + tan suat lenh
        for n in names:
            if re.search(r"Metadata/plate_\d+\.gcode$", n):
                try:
                    with z.open(n) as fp:
                        head = fp.read(800 * 1024).decode("utf-8", "ignore")
                except Exception:
                    break
                lines = head.splitlines()
                for line in lines[:600]:
                    s = line.strip()
                    if s.startswith(";") and "=" in s and len(s) < 200:
                        info["header"].append(s.lstrip("; ").strip())
                freq = {}
                for line in lines:
                    m = _CMD_RE.match(line.strip())
                    if m:
                        c = m.group(1)
                        freq[c] = freq.get(c, 0) + 1
                info["commands"] = freq
                break
    return info


def fetch_job(host: str, code: str, gcode_file: str) -> dict:
    """Tai file dang in 1 lan -> tra {weight, thumb, info}. Rong neu that bai."""
    data = _download(host, code, gcode_file)
    if not data:
        return {}
    tmp = os.path.join(tempfile.gettempdir(), "bambu_job.3mf")
    try:
        with open(tmp, "wb") as f:
            f.write(data)
        return {"weight": parse_weight(tmp), "thumb": parse_thumbnail(tmp),
                "info": parse_job_info(tmp)}
    finally:
        try:
            os.remove(tmp)
        except OSError:
            pass


def job_weight(host: str, code: str, gcode_file: str) -> float | None:
    return fetch_job(host, code, gcode_file).get("weight")


def _download_exact(host: str, code: str, path: str) -> bytes | None:
    """Tai dung 1 duong dan file (khong doan candidate)."""
    ftp = None
    try:
        ftp = _connect(host, code)
        buf = io.BytesIO()
        ftp.retrbinary("RETR " + path, buf.write)
        return buf.getvalue()
    except Exception:
        return None
    finally:
        if ftp:
            try:
                ftp.quit()
            except Exception:
                pass


def fetch_thumb_for(host: str, code: str, path: str) -> bytes | None:
    """Tai file tai `path` -> tra anh preview (PNG). Dung cho danh sach file."""
    data = _download_exact(host, code, path)
    if not data:
        return None
    tmp = os.path.join(tempfile.gettempdir(), "bambu_thumb.3mf")
    try:
        with open(tmp, "wb") as f:
            f.write(data)
        return parse_thumbnail(tmp)
    finally:
        try:
            os.remove(tmp)
        except OSError:
            pass


def _main():
    import printer_config
    host, _serial, code = printer_config.load([])
    gcode_file = sys.argv[1] if len(sys.argv) > 1 else "Organic Support.3mf"
    print(f"Tai file dang in: {gcode_file} tu {host}:990 ...")
    data = _download(host, code, gcode_file)
    if not data:
        print("KHONG tai duoc file (sai duong dan / FTPS tu choi).")
        return
    print(f"  Tai xong: {len(data)} bytes")
    w = parse_weight(data)
    print(f"  TONG GAM ban in: {w if w is not None else 'khong doc duoc'} g")


if __name__ == "__main__":
    _main()
