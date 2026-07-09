#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Do Serial may Bambu tren LAN qua SSDP (UDP 2021 broadcast/multicast)."""
import socket, struct, sys, time

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

TARGET = sys.argv[1] if len(sys.argv) > 1 else None
MCAST = "239.255.255.250"
PORT = 2021

s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
try:
    s.bind(("", PORT))
except Exception as e:
    print("BIND_FAIL", e)
    sys.exit(2)
try:
    mreq = struct.pack("4sl", socket.inet_aton(MCAST), socket.INADDR_ANY)
    s.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)
except Exception as e:
    print("MCAST_JOIN_WARN", e)

s.settimeout(2.0)
end = time.time() + 12
found = {}
print("Dang nghe SSDP tren UDP 2021 (~12s)...")
while time.time() < end:
    try:
        data, addr = s.recvfrom(65535)
    except socket.timeout:
        continue
    except Exception:
        continue
    text = data.decode("utf-8", "ignore")
    ip = addr[0]
    if TARGET and ip != TARGET:
        continue
    usn = name = model = None
    for line in text.splitlines():
        low = line.lower()
        if low.startswith("usn:"):
            usn = line.split(":", 1)[1].strip()
        elif low.startswith("devname.bambu.com:"):
            name = line.split(":", 1)[1].strip()
        elif low.startswith("devmodel.bambu.com:"):
            model = line.split(":", 1)[1].strip()
    if usn:
        found[ip] = (usn, name, model)
        print(f"FOUND ip={ip} serial={usn} name={name} model={model}")

if not found:
    print("NO_SSDP - khong bat duoc goi SSDP (firewall/mang chan multicast). Can nhap serial tay.")
