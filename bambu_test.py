#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""One-shot: connect MQTT, xin pushall, in 1 snapshot roi thoat. Xac nhan credential."""
import sys, os, ssl, json, time, threading

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import paho.mqtt.client as mqtt

p = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".mcp.json")
env = json.load(open(p, encoding="utf-8"))["mcpServers"]["bambu-printer"]["env"]
IP, SERIAL, CODE = env["PRINTER_HOST"], env["BAMBU_SERIAL"], env["BAMBU_TOKEN"]
REPORT = f"device/{SERIAL}/report"
REQUEST = f"device/{SERIAL}/request"

got = {"data": None, "rc": None}
done = threading.Event()


def on_connect(c, u, f, rc, *a):
    got["rc"] = rc
    if rc == 0:
        c.subscribe(REPORT)
        c.publish(REQUEST, json.dumps({"pushing": {"sequence_id": "0", "command": "pushall"}}))
    else:
        done.set()


def on_message(c, u, msg):
    try:
        d = json.loads(msg.payload.decode("utf-8", "ignore"))
    except Exception:
        return
    if "print" in d:
        cur = got["data"] or {}
        cur.update(d["print"])
        got["data"] = cur
        if any(k in cur for k in ("nozzle_temper", "gcode_state", "bed_temper")):
            done.set()


try:
    c = mqtt.Client(mqtt.CallbackAPIVersion.VERSION1)
except Exception:
    c = mqtt.Client()
c.username_pw_set("bblp", CODE)
c.tls_set(cert_reqs=ssl.CERT_NONE, tls_version=ssl.PROTOCOL_TLS_CLIENT)
c.tls_insecure_set(True)
c.on_connect = on_connect
c.on_message = on_message
print(f"Ket noi {IP}:8883 serial={SERIAL} ...")
try:
    c.connect(IP, 8883, 15)
except Exception as e:
    print("CONNECT_FAIL", e)
    sys.exit(1)
c.loop_start()
done.wait(timeout=12)
c.loop_stop()
c.disconnect()

if got["rc"] != 0:
    print(f"AUTH_FAIL rc={got['rc']} -> sai Access Code hoac chua bat Developer/LAN mode")
    sys.exit(2)
d = got["data"] or {}
if not d:
    print("CONNECTED nhung chua nhan duoc report (thu bat Developer Mode).")
    sys.exit(3)
print("=== OK - DOC DUOC MAY IN ===")
print(f"  gcode_state : {d.get('gcode_state','?')}")
print(f"  nozzle      : {d.get('nozzle_temper','?')} -> {d.get('nozzle_target_temper','?')} C")
print(f"  bed         : {d.get('bed_temper','?')} -> {d.get('bed_target_temper','?')} C")
print(f"  fan(part)   : {d.get('cooling_fan_speed','?')}")
print(f"  wifi        : {d.get('wifi_signal','?')}")
print(f"  progress    : {d.get('mc_percent','?')}%  layer {d.get('layer_num','?')}/{d.get('total_layer_num','?')}")
