#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
bambu_status.py — Xem TRANG THAI may in Bambu A1 qua LAN (MQTT truc tiep tu may).
Khong phu thuoc OrcaSlicer/Bambu Studio dang mo — doc thang tu may.

Dung:
  python bambu_status.py <IP> <SERIAL> <ACCESS_CODE>
  (hoac keo-tha khong tham so -> doc tu .mcp.json cung thu muc)

Yeu cau tren MAY: bat "LAN Only Mode" + "Developer Mode", lay Access Code + Serial + IP.
Cai lib (1 lan): python -m pip install --user paho-mqtt
"""
import sys, os, ssl, json, time, threading

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

try:
    import paho.mqtt.client as mqtt
except ImportError:
    print("Thieu paho-mqtt. Chay:  python -m pip install --user paho-mqtt")
    sys.exit(1)


def load_cfg():
    """Doc IP/serial/code tu tham so, hoac tu .mcp.json."""
    if len(sys.argv) >= 4:
        return sys.argv[1], sys.argv[2], sys.argv[3]
    p = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".mcp.json")
    if os.path.isfile(p):
        try:
            env = json.load(open(p, encoding="utf-8"))["mcpServers"]["bambu-printer"]["env"]
            ip, sn, tok = env.get("PRINTER_HOST"), env.get("BAMBU_SERIAL"), env.get("BAMBU_TOKEN")
            if ip and "REPLACE" not in str(ip):
                return ip, sn, tok
        except Exception:
            pass
    print("Chua co thong tin may. Cach dung:")
    print("  python bambu_status.py <IP> <SERIAL> <ACCESS_CODE>")
    print("  hoac dien IP/serial/code that vao .mcp.json roi chay lai.")
    sys.exit(1)


IP, SERIAL, CODE = load_cfg()
REPORT = f"device/{SERIAL}/report"
REQUEST = f"device/{SERIAL}/request"
state = {"data": None, "ts": 0, "connected": False}

STAGE = {  # mc_print_stage / gcode_state → tieng Viet
    "IDLE": "Đang rảnh", "PREPARE": "Đang chuẩn bị", "RUNNING": "ĐANG IN",
    "PAUSE": "Tạm dừng", "FINISH": "In XONG", "FAILED": "In LỖI", "SLICING": "Đang slice",
}


def fmt_min(m):
    try:
        m = int(m)
        return f"{m//60}h{m%60:02d}m" if m >= 60 else f"{m}m"
    except Exception:
        return "—"


def on_connect(c, u, flags, rc, *a):
    if rc == 0:
        state["connected"] = True
        c.subscribe(REPORT)
        # yeu cau may push toan bo trang thai
        c.publish(REQUEST, json.dumps({"pushing": {"sequence_id": "0", "command": "pushall"}}))
    else:
        print(f"[LOI] Ket noi MQTT that bai rc={rc} — sai Access Code? Chua bat LAN Only/Developer Mode?")


def on_message(c, u, msg):
    try:
        d = json.loads(msg.payload.decode("utf-8", "ignore"))
    except Exception:
        return
    if "print" in d:
        cur = state["data"] or {}
        cur.update(d["print"])          # gop (may gui delta)
        state["data"] = cur
        state["ts"] = time.time()


def render():
    d = state["data"] or {}
    os.system("cls" if os.name == "nt" else "clear")
    print("=" * 60)
    print(f"  TRANG THAI MAY IN  ·  {IP}  ·  {SERIAL or '?'}")
    print("=" * 60)
    if not state["connected"]:
        print("  ... dang ket noi ...")
        return
    if not d:
        print("  Da ket noi — dang cho may push du lieu...")
        return
    gc = d.get("gcode_state", "?")
    stage = STAGE.get(gc, gc)
    print(f"  Trang thai   : {stage}")
    job = d.get("subtask_name") or d.get("gcode_file") or "—"
    if gc in ("RUNNING", "PAUSE"):
        pct = d.get("mc_percent", "?")
        rem = fmt_min(d.get("mc_remaining_time"))
        ln, tl = d.get("layer_num", "?"), d.get("total_layer_num", "?")
        bar = "█" * int((pct if isinstance(pct, int) else 0) / 5) + "·" * (20 - int((pct if isinstance(pct, int) else 0) / 5))
        print(f"  File         : {job}")
        print(f"  Tien do      : {pct}%  [{bar}]  còn ~{rem}")
        print(f"  Lớp          : {ln} / {tl}")
        print(f"  Tốc độ       : mức {d.get('spd_lvl','?')} (1 Silent · 2 Standard · 3 Sport · 4 Ludicrous)")
    print("-" * 60)
    print(f"  Nozzle       : {d.get('nozzle_temper','?')}°C  →  {d.get('nozzle_target_temper','?')}°C")
    print(f"  Bed          : {d.get('bed_temper','?')}°C  →  {d.get('bed_target_temper','?')}°C")
    fan = d.get("cooling_fan_speed")
    if fan is not None:
        print(f"  Quạt (part)  : {fan}")
    wifi = d.get("wifi_signal")
    if wifi:
        print(f"  Wi-Fi        : {wifi}")
    err = d.get("print_error", 0) or d.get("mc_print_error_code", 0)
    if err and str(err) != "0":
        print(f"  ⚠ LỖI code   : {err}")
    # AMS
    ams = (d.get("ams") or {}).get("ams") if isinstance(d.get("ams"), dict) else None
    if ams:
        print("-" * 60)
        for a in ams:
            for tr in a.get("tray", []):
                if tr.get("tray_type"):
                    print(f"  AMS khe {tr.get('id','?')} : {tr.get('tray_type','?')}  {tr.get('tray_color','')[:8]}")
    print("=" * 60)
    print(f"  (cap nhat {time.strftime('%H:%M:%S', time.localtime(state['ts']))} · Ctrl+C thoat)")


def main():
    print(f"Ket noi {IP}:8883 (MQTTS)…  Access Code: {'*'*len(CODE or '')}")
    try:
        c = mqtt.Client(mqtt.CallbackAPIVersion.VERSION1)   # paho 2.x
    except Exception:
        c = mqtt.Client()                                   # paho 1.x
    c.username_pw_set("bblp", CODE)
    c.tls_set(cert_reqs=ssl.CERT_NONE, tls_version=ssl.PROTOCOL_TLS_CLIENT)
    c.tls_insecure_set(True)
    c.on_connect = on_connect
    c.on_message = on_message
    try:
        c.connect(IP, 8883, 30)
    except Exception as e:
        print(f"[LOI] Khong ket noi duoc {IP}:8883 — {e}")
        print("  Kiem tra: cung mang LAN, IP dung, port 8883 khong bi firewall chan.")
        return
    c.loop_start()
    try:
        while True:
            render()
            time.sleep(2)
    except KeyboardInterrupt:
        print("\nThoat.")
    finally:
        c.loop_stop(); c.disconnect()


if __name__ == "__main__":
    main()
