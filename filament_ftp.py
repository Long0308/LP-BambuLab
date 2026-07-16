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
import threading
import zipfile

# May in Bambu chi chiu ~1 ket noi FTPS mot luc. Khoa DAT TAI DAY (tang module)
# de moi ham mo ket noi tu tuan tu hoa — khong phu thuoc ky luat cua caller.
# (Truoc day chi 2/5 diem goi qua THUMB_LOCK ben bambu_web -> co the mo 2 ket noi.)
FTP_LOCK = threading.Lock()

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

    def storbinary(self, cmd, fp, blocksize=8192, callback=None, rest=None):
        """Nhu ftplib nhung KHONG goi conn.unwrap() o cuoi.

        ftplib goc dong TLS bang unwrap(), tuc cho may in tra lai `close_notify`.
        FTP server cua Bambu KHONG BAO GIO tra -> unwrap() treo vinh vien, upload
        dung o 100%. Tai xuong khong dinh vi luc do MAY IN la ben dong ket noi.
        """
        self.voidcmd("TYPE I")
        with self.transfercmd(cmd, rest) as conn:
            while True:
                buf = fp.read(blocksize)
                if not buf:
                    break
                conn.sendall(buf)
                if callback:
                    callback(buf)
            # co y BO conn.unwrap() — xem docstring
        return self.voidresp()


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
        with FTP_LOCK:
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
    except Exception:                       # may in tat / sai code -> None, dung crash
        return None
    finally:
        if ftp:
            try:
                ftp.quit()
            except Exception:
                pass


_USED_G = re.compile(r'used_g="([\d.]+)"')
# File DA MAU: Bambu ghi nhieu so tren 1 dong phan cach phay ("106.56,12.77")
# -> capture ca chuoi roi cong; ([\d.]+) cu dung o dau phay, thieu nhua #2+.
# File DA MAU: nhieu so 1 dong phan cach phay ("106.56,12.77", co the co space
# sau phay) -> capture ca chuoi roi CONG. [\d., ] khong co \n nen khong an sang
# dong sau. CUNG do dung sai voi slicer_cli._WEIGHT_PAT + hub HTML (review MEDIUM-6).
_HDR_PATS = (
    re.compile(r"total filament weight \[g\]\s*[:=]\s*([\d., ]+)", re.I),
    re.compile(r"filament used \[g\]\s*[:=]\s*([\d., ]+)", re.I),
    re.compile(r"total filament used \[g\]\s*[:=]\s*([\d., ]+)", re.I),
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
                        return round(sum(float(x) for m in ms
                                         for x in m.split(",") if x.strip()), 2)
    return None


def list_files(host: str, code: str) -> list:
    """Liet ke cac file .3mf tren may (root + /cache). Chi doc, khong tai."""
    try:
        with FTP_LOCK:
            return _list_files_locked(host, code)
    except Exception:                       # may in tat -> danh sach rong, dung crash
        return []


def _list_files_locked(host: str, code: str) -> list:
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
                # Mau THAT SU dung: slice_info liet ke tung cuon kem color + used_g.
                # Day moi la nguon chuan — filament_colour trong project_settings liet ke
                # ca 4 khe AMS ke ca khe khong dung trong ban in nay.
                fils = []
                for m in re.finditer(r"<filament\b([^>]*)/?>", txt):
                    at = m.group(1)
                    def _a(k):
                        mm = re.search(k + r'="([^"]*)"', at)
                        return mm.group(1) if mm else None
                    g = _a("used_g")
                    try:
                        g = float(g) if g else 0.0
                    except ValueError:
                        g = 0.0
                    if g <= 0:                       # cuon khong dung trong ban in nay
                        continue
                    fils.append({"id": _a("id"), "color": _a("color"),
                                 "type": _a("type"), "used_g": round(g, 2)})
                if fils:
                    info["slice"]["filaments"] = fils
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


def _tmp_3mf(data: bytes) -> str:
    """Ghi bytes ra file tam DUY NHAT (khong dung ten co dinh -> tranh dam nhau)."""
    fd, path = tempfile.mkstemp(suffix=".3mf", prefix="bambu_")
    with os.fdopen(fd, "wb") as f:
        f.write(data)
    return path


def fetch_job(host: str, code: str, gcode_file: str) -> dict:
    """Tai file dang in 1 lan -> tra {weight, thumb, info}. Rong neu that bai."""
    data = _download(host, code, gcode_file)
    if not data:
        return {}
    tmp = _tmp_3mf(data)
    try:
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
        with FTP_LOCK:
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


_PLATE_GCODE = re.compile(r"Metadata/plate_\d+\.gcode$", re.I)


def parse_is_sliced(zip_path) -> bool:
    """File .3mf nay da co G-code ben trong chua? -> may in duoc ngay.

    KHONG the doan bang duoi ten file: Bambu Studio khi bam Print day file DA SLICE
    xuong /cache/<ten>.3mf — van la ".3mf" chu khong phai ".gcode.3mf". Cach duy nhat
    dung la mo zip ra xem co Metadata/plate_N.gcode hay khong.
    """
    try:
        z = zipfile.ZipFile(zip_path)
    except (zipfile.BadZipFile, OSError):
        return False
    with z:
        return any(_PLATE_GCODE.search(n) for n in z.namelist())


def fetch_file_meta(host: str, code: str, path: str) -> dict:
    """Tai file tai `path` 1 lan -> {thumb: PNG|None, sliced: bool}. Rong neu that bai."""
    data = _download_exact(host, code, path)
    if not data:
        return {}
    tmp = _tmp_3mf(data)
    try:
        return {"thumb": parse_thumbnail(tmp), "sliced": parse_is_sliced(tmp)}
    finally:
        try:
            os.remove(tmp)
        except OSError:
            pass


def fetch_thumb_for(host: str, code: str, path: str) -> bytes | None:
    """Tai file tai `path` -> tra anh preview (PNG). Dung cho danh sach file."""
    return fetch_file_meta(host, code, path).get("thumb")


def probe_sliced(host: str, code: str, path: str, tail: int = 96 * 1024) -> bool | None:
    """Kiem tra 'da slice chua' bang cach doc DUOI file qua FTP REST.

    Zip luu muc luc (central directory, chua TEN entry dang plain text) o CUOI file
    -> chi can tai ~96KB cuoi roi tim 'Metadata/plate_N.gcode', thay vi tai ca file
    30MB chi de tra loi 1 bit. Tra None neu khong doc duoc (UI hien 'khong ro').
    """
    ftp = None
    try:
        with FTP_LOCK:
            ftp = _connect(host, code)
            ftp.voidcmd("TYPE I")            # SIZE/REST can binary mode
            size = ftp.size(path)
            if not size:
                return None
            buf = io.BytesIO()
            ftp.retrbinary("RETR " + path, buf.write, rest=max(0, size - tail))
            return bool(re.search(rb"Metadata/plate_\d+\.gcode", buf.getvalue()))
    except Exception:
        return None
    finally:
        if ftp:
            try:
                ftp.quit()
            except Exception:
                pass


def upload_file(host: str, code: str, data: bytes, remote_name: str,
                remote_dir: str = "/") -> tuple[bool, str]:
    """Day 1 file .3mf len the SD cua may qua FTPS (STOR).

    Mac dinh len goc "/" — cung noi Bambu Studio day xuong, va la noi
    cmd_project_file(url=file:///sdcard/<ten>) doc duoc de in ngay sau do.
    Tra (ok, duong_dan_hoac_loi).
    """
    ftp = None
    try:
        with FTP_LOCK:
            ftp = _connect(host, code, timeout=180.0)   # file vai chuc MB qua wifi
            try:
                ftp.cwd(remote_dir)
            except ftplib.error_perm:
                remote_dir = "/"
                ftp.cwd("/")
            ftp.storbinary("STOR " + remote_name, io.BytesIO(data))
            return True, remote_dir.rstrip("/") + "/" + remote_name
    except Exception as e:                          # noqa: BLE001 - bao loi len UI
        return False, str(e)
    finally:
        if ftp:
            try:
                ftp.quit()
            except Exception:
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
