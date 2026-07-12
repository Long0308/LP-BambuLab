#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Doc/ghi cau hinh may in Bambu cuc bo.

Thu tu uu tien khi doc (cai nao co truoc thi dung):
  1. Tham so dong lenh:  <IP> <SERIAL> <ACCESS_CODE>
  2. Bien moi truong:    BAMBU_HOST / BAMBU_SERIAL / BAMBU_ACCESS_CODE
                         (an toan nhat: KHONG co file secret nao trong thu muc du an)
  3. File .env           (gitignore)
  4. printer.local.json  (gitignore)

BAO MAT — vi sao KHONG dat ten `.mcp.json`:
Claude Code tu dong nap project-scoped MCP server tu file `.mcp.json` o thu muc goc.
Neu cau hinh may in nam trong file do, AI se duoc trao toan quyen dieu khien may in
(start_print_job / cancel_print / set_temperature / delete_printer_file / upload_gcode...).
Nguyen tac cua du an: MOI dieu khien do NGUOI DUNG bam tren web dashboard;
AI chi doc va phan tich. Xem README muc "Bao mat".

Luu y that long: .env va printer.local.json deu la PLAINTEXT tren dia, khong ma hoa.
Chung chi giup tranh commit nham len git. Muon secret khong nam trong thu muc du an,
hay dat bien moi truong BAMBU_* o cap he dieu hanh.
"""
from __future__ import annotations

import json
import os
import sys

CONFIG_NAME = "printer.local.json"
ENV_NAME = ".env"
_HERE = os.path.dirname(os.path.abspath(__file__))

ENV_KEYS = ("BAMBU_HOST", "BAMBU_SERIAL", "BAMBU_ACCESS_CODE")


def config_path() -> str:
    """Duong dan tuyet doi toi printer.local.json."""
    return os.path.join(_HERE, CONFIG_NAME)


def env_path() -> str:
    """Duong dan tuyet doi toi .env."""
    return os.path.join(_HERE, ENV_NAME)


def save(host: str, serial: str, access_code: str) -> str:
    """Ghi cau hinh may in vao printer.local.json; tra ve duong dan da ghi."""
    cfg = {"host": host, "serial": serial, "access_code": access_code}
    with open(config_path(), "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)
    return config_path()


def _valid(host: str | None) -> bool:
    return bool(host) and "REPLACE" not in str(host)


def _from_environ() -> tuple[str, str, str] | None:
    host, serial, code = (os.environ.get(k) for k in ENV_KEYS)
    return (host, serial, code) if _valid(host) else None


def _parse_dotenv(path: str) -> dict[str, str]:
    """Parse .env toi gian: KEY=VALUE, bo qua comment va dong trong. Khong can thu vien."""
    out: dict[str, str] = {}
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, value = line.partition("=")
                out[key.strip()] = value.strip().strip("'\"")
    except OSError:
        pass
    return out


def _from_dotenv() -> tuple[str, str, str] | None:
    if not os.path.isfile(env_path()):
        return None
    data = _parse_dotenv(env_path())
    host, serial, code = (data.get(k) for k in ENV_KEYS)
    return (host, serial, code) if _valid(host) else None


def _from_json() -> tuple[str, str, str] | None:
    path = config_path()
    if not os.path.isfile(path):
        return None
    try:
        with open(path, encoding="utf-8") as f:
            cfg = json.load(f)
    except (OSError, ValueError):
        return None
    host, serial, code = cfg.get("host"), cfg.get("serial"), cfg.get("access_code")
    return (host, serial, code) if _valid(host) else None


def load(argv: list[str] | None = None) -> tuple[str, str, str]:
    """Tra ve (host, serial, access_code) theo thu tu uu tien o docstring module."""
    args = argv if argv is not None else sys.argv[1:]
    if len(args) >= 3:
        return args[0], args[1], args[2]

    for source in (_from_environ, _from_dotenv, _from_json):
        found = source()
        if found:
            return found

    print("Chua co cau hinh may in. Chon MOT trong cac cach sau:")
    print("  1) Bien moi truong (khong luu file):")
    print("       setx BAMBU_HOST 192.168.1.50")
    print("       setx BAMBU_SERIAL <SERIAL>")
    print("       setx BAMBU_ACCESS_CODE <CODE>")
    print(f"  2) File {ENV_NAME}  (chep tu .env.example)")
    print(f"  3) File {CONFIG_NAME}:  python bambu_connect.py <IP> <SERIAL> <ACCESS_CODE>")
    print("  4) Truyen thang: python <script>.py <IP> <SERIAL> <ACCESS_CODE>")
    sys.exit(1)
