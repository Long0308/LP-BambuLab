#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
bambu_connect.py - Tro ly ket noi may Bambu Lab qua MCP (LAN mode).

Lam 3 viec:
  1) Kiem tra may A1 co tiep can duoc tren mang LAN khong (port MQTTS 8883 + FTPS 990).
  2) Ghi cau hinh vao .mcp.json de Claude/Cursor nap server bambu-printer-mcp.
  3) In huong dan bat Developer Mode / LAN Only va lay Access Code.

Dung:
  python bambu_connect.py                         -> hoi tung thong tin
  python bambu_connect.py 192.168.1.50 01P00A.. CODE
Chi dung thu vien chuan - khong can cai them.
"""
import sys, os, json, socket

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

MCP_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".mcp.json")
PORTS = [(8883, "MQTTS (lenh in / trang thai)"), (990, "FTPS (upload file)")]

def test_port(ip, port, timeout=3.0):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(timeout)
    try:
        s.connect((ip, port))
        return True
    except Exception:
        return False
    finally:
        s.close()

def ask(label, default=""):
    v = input(f"  {label}{(' ['+default+']') if default else ''}: ").strip()
    return v or default

def write_mcp(ip, serial, code):
    cfg = {
        "mcpServers": {
            "bambu-printer": {
                "command": "npx",
                "args": ["-y", "@rowbotik/bambu-printer-mcp"],
                "env": {
                    "PRINTER_HOST": ip,
                    "BAMBU_SERIAL": serial,
                    "BAMBU_TOKEN": code,
                },
            }
        }
    }
    json.dump(cfg, open(MCP_PATH, "w", encoding="utf-8"), indent=2)
    return MCP_PATH

def main():
    print("=" * 58)
    print(" KET NOI BAMBU LAB A1 QUA MCP (LAN mode)")
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
        print("Thieu IP. Dung lai."); return

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
        print("\n[2] Ghi cau hinh MCP ...")
        p = write_mcp(ip, serial, code)
        print("    Da ghi:", p)
    else:
        print("\n[2] Chua du Serial/Access Code -> bo qua ghi .mcp.json.")
        print("    Dien tay vao .mcp.json (PRINTER_HOST / BAMBU_SERIAL / BAMBU_TOKEN).")

    print("\n[3] Buoc cuoi de Claude nap server:")
    print("    - Cai Node.js (de chay 'npx') neu chua co: https://nodejs.org")
    print("    - Mo lai Claude/Cursor -> chap nhan server 'bambu-printer'.")
    print("    - Khi nap xong se co cac tool: mcp__bambu-printer__* (get_status, print_3mf, ...).")
    print("=" * 58)

if __name__ == "__main__":
    main()
