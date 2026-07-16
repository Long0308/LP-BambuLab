#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Camera tich hop cua A1/P1 qua LAN — cong 6000, TLS tu ky, auth bang Access Code.

Giao thuc (OpenBambuAPI / cong dong ha-bambulab, da dung tren P1/A1):
  1. TLS connect toi <ip>:6000 (cert tu ky -> khong verify).
  2. Gui goi AUTH 80 byte: [0x40 LE][0x3000 LE][0][0] + username 'bblp' pad 32
     + access_code pad 32.
  3. May tra tung FRAME: header 16 byte (4 byte dau = kich thuoc payload LE),
     tiep theo la JPEG tron ven (FFD8...FFD9).

Thiet ke: 1 thread "bom" duy nhat giu ket noi, cache FRAME MOI NHAT; cac viewer
MJPEG chi doc cache -> n viewer van chi 1 ket noi toi may in. Thread tu tat khi
het viewer ~15s (khong giu TLS vo han khi khong ai xem).
"""
from __future__ import annotations

import socket
import ssl
import struct
import threading
import time

_LOCK = threading.Lock()
_FRAME: bytes | None = None
_FRAME_TS = 0.0
_LAST_WANT = 0.0          # lan cuoi co nguoi hoi frame
_ERR = ""                 # loi gan nhat (hien len UI cho de chan doan)
_PUMP_ON = False
_IDLE_STOP_S = 15         # het nguoi xem qua nguong nay -> dong ket noi


def _auth_packet(code: str, user: str = "bblp") -> bytes:
    pkt = struct.pack("<IIII", 0x40, 0x3000, 0, 0)
    pkt += user.encode("ascii").ljust(32, b"\x00")
    pkt += code.encode("ascii").ljust(32, b"\x00")
    return pkt


def _read_exact(sock, n: int) -> bytes:
    buf = b""
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:
            raise ConnectionError("printer dong ket noi")
        buf += chunk
    return buf


def _pump(host: str, code: str) -> None:
    """Thread nen: giu ket noi camera, cap nhat _FRAME. Tu thoat khi het viewer."""
    global _FRAME, _FRAME_TS, _ERR, _PUMP_ON
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE           # cert tu ky cua may in
    try:
        while True:
            with _LOCK:
                if time.time() - _LAST_WANT > _IDLE_STOP_S:
                    break                      # khong ai xem -> nghi
            try:
                raw = socket.create_connection((host, 6000), timeout=8)
                s = ctx.wrap_socket(raw, server_hostname=host)
                s.settimeout(12)
                s.sendall(_auth_packet(code))
                _ERR = ""
                while True:
                    with _LOCK:
                        if time.time() - _LAST_WANT > _IDLE_STOP_S:
                            raise StopIteration
                    head = _read_exact(s, 16)
                    size = struct.unpack("<I", head[:4])[0]
                    if not 0 < size < 8 * 1024 * 1024:
                        raise ConnectionError(f"header la (size={size})")
                    jpg = _read_exact(s, size)
                    if jpg[:2] != b"\xff\xd8":     # mat dong bo -> lam lai tu dau
                        raise ConnectionError("frame khong phai JPEG — resync")
                    with _LOCK:
                        _FRAME, _FRAME_TS = jpg, time.time()
            except StopIteration:
                break
            except Exception as e:              # noqa: BLE001 — mat mang/timeout: thu lai
                _ERR = str(e)
                time.sleep(3)
            finally:
                try:
                    s.close()
                except Exception:
                    pass
    finally:
        with _LOCK:
            _PUMP_ON = False


def _want(host: str, code: str) -> None:
    """Danh dau dang co nguoi xem + bat thread bom neu chua chay."""
    global _PUMP_ON, _LAST_WANT
    with _LOCK:
        _LAST_WANT = time.time()
        if not _PUMP_ON:
            _PUMP_ON = True
            threading.Thread(target=_pump, args=(host, code), daemon=True).start()


def get_frame(host: str, code: str, wait_s: float = 6.0) -> bytes | None:
    """Frame JPEG moi nhat (cho toi wait_s giay cho frame dau). None = chua co."""
    _want(host, code)
    t0 = time.time()
    while time.time() - t0 < wait_s:
        with _LOCK:
            if _FRAME and time.time() - _FRAME_TS < 30:
                return _FRAME
        time.sleep(0.2)
    return None


def last_error() -> str:
    return _ERR


def mjpeg_frames(host: str, code: str):
    """Generator MJPEG: yield frame moi (danh cho multipart/x-mixed-replace).

    Khong yield trung frame cu — cho frame moi theo _FRAME_TS.
    """
    seen = 0.0
    while True:
        _want(host, code)
        with _LOCK:
            f, ts = _FRAME, _FRAME_TS
        if f and ts > seen:
            seen = ts
            yield f
        else:
            time.sleep(0.25)