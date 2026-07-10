#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
bambu_connect.py - Tro ly ket noi may Bambu Lab qua LAN.

Lam 3 viec:
  1) Kiem tra may A1 co tiep can duoc tren mang LAN khong (port MQTTS 8883 + FTPS 990).
  2) Ghi cau hinh vao printer.local.json cho cac script cuc bo (bambu_web / bambu_status).
  3) In huong dan bat Developer Mode / LAN Only va lay Access Code.

BAO MAT: file cau hinh CO Y KHONG dat ten `.mcp.json`. Claude Code tu dong nap
project-scoped MCP server tu `.mcp.json`, se trao quyen dieu khien may in cho AI
(in / huy / chinh nhiet / xoa file). Moi dieu khien phai do NGUOI DUNG bam tren
web dashboard (bambu_web.py). Xem README muc "Bao mat".

Dung:
  python bambu_connect.py                         -> hoi tung thong tin
  python bambu_connect.py 192.168.1.50 01P00A.. CODE
Chi dung thu vien chuan - khong can cai them.
"""
import sys, socket

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import printer_config

PORTS = [(8883, "MQTTS (lenh in / trang thai)"), (990, "FTPS (upload file)")]


def test_port(ip: str, port: int, timeout: float = 3.0) -> bool:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(timeout)
    try:
        s.connect((ip, port))
        return True
    except OSError:
        return False
    finally:
        s.close()


def ask(label: str, default: str = "") -> str:
    v = input(f"  {label}{(' [' + default + ']') if default else ''}: ").strip()
    return v or default


def main() -> None:
    print("=" * 58)
    print(" KET NOI BAMBU LAB A1 QUA LAN")
    print("=" * 58)
    args = sys.argv[1:]
    if len(args) >= 1:
        ip = args[0]
        serial = args[1] if len(args) > 1 else ""
        code = args[2] if len(args) > 2 else ""
    else:
        print("Nhap thong tin may (xem tren man hinh A1: Setting > Network / Device):")
        ip = ask("IP may A1 (vd 192.168.1.50)")
        serial = ask("Serial may (vd 01P00A123456789)")
        code = ask("Access Code (LAN, 8 ky tu)")

    if not ip:
        print("Thieu IP. Dung lai.")
        return

    print("\n[1] Kiem tra ket noi mang toi", ip, "...")
    ok_all = True
    for port, desc in PORTS:
        ok = test_port(ip, port)
        ok_all = ok_all and ok
        print(f"    Port {port:<5} {desc:<32} : {'OK - mo' if ok else 'KHONG ket noi duoc'}")
    if not ok_all:
        print("    => Neu KHONG ket noi: kiem tra may & PC cung mang; bat 'LAN Only Mode'")
        print("       va 'Developer Mode' tren may; tat firewall chan port.")

    if serial and code:
        print("\n[2] Ghi cau hinh cuc bo ...")
        path = printer_config.save(ip, serial, code)
        print("    Da ghi:", path)
        print("    (File nay bi gitignore — KHONG day len GitHub vi chua access code.)")
    else:
        print(f"\n[2] Chua du Serial/Access Code -> bo qua ghi {printer_config.CONFIG_NAME}.")
        print(f"    Chep printer.local.example.json -> {printer_config.CONFIG_NAME} roi dien tay.")

    print("\n[3] Buoc cuoi:")
    print("    - Chay dashboard:  python bambu_web.py 8787")
    print("    - Dien thoai/PC cung LAN mo:  http://<IP-PC>:8787")
    print("    - Moi lenh in/dung do BAN bam tren web. AI khong co quyen ra lenh.")
    print("=" * 58)


if __name__ == "__main__":
    main()
