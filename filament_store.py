#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Luu luong nhua con lai theo tung cuon RFID (khoa = tag_uid).

Vi sao can module nay: A1/AMS Lite KHONG day so gam da dung qua MQTT LAN
(field `remain` ket o 100%). So gam that o Filament Library tren cloud, khong
lay duoc qua LAN. Nen ta tu quan ly cuc bo: nguoi dung khai bao gam con lai khi
thay cuon (giong man 'Edit Filament' cua Bambu), khoa theo tag_uid cua chip RFID
nen doi khe / rut ra cam lai van dung dung cuon.

File luu: filament.local.json (gitignore — khong day len GitHub).
"""
from __future__ import annotations

import json
import os
import threading
import time

STORE_NAME = "filament.local.json"
_HERE = os.path.dirname(os.path.abspath(__file__))
_LOCK = threading.Lock()
DEFAULT_NET = 1000  # gam / cuon Bambu 1kg


def _path() -> str:
    return os.path.join(_HERE, STORE_NAME)


def _read() -> dict:
    try:
        with open(_path(), encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _write(data: dict) -> None:
    tmp = _path() + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, _path())


def get(tag_uid: str) -> dict | None:
    """Tra ve record {net, remaining, updated} cho 1 cuon, hoac None neu chua khai bao."""
    if not tag_uid or tag_uid.strip("0") == "":
        return None
    with _LOCK:
        return _read().get(tag_uid)


def set_remaining(tag_uid: str, remaining: float, net: float | None = None) -> dict:
    """Khai bao gam con lai cho 1 cuon (khi thay cuon / hieu chinh)."""
    if not tag_uid:
        raise ValueError("thieu tag_uid")
    remaining = max(0, round(float(remaining)))
    with _LOCK:
        data = _read()
        rec = data.get(tag_uid, {})
        if net is not None:
            rec["net"] = max(1, round(float(net)))
        rec.setdefault("net", max(DEFAULT_NET, remaining))
        rec["remaining"] = min(remaining, rec["net"])
        rec["updated"] = int(time.time())
        data[tag_uid] = rec
        _write(data)
        return rec


def subtract(tag_uid: str, grams: float) -> dict | None:
    """Tru gam da dung sau 1 job (neu cuon da duoc khai bao)."""
    if not tag_uid or grams <= 0:
        return None
    with _LOCK:
        data = _read()
        rec = data.get(tag_uid)
        if not rec:
            return None
        rec["remaining"] = max(0, round(rec.get("remaining", 0) - float(grams)))
        rec["updated"] = int(time.time())
        data[tag_uid] = rec
        _write(data)
        return rec
