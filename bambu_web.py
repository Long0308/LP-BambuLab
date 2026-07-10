#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
bambu_web.py — Web dashboard + BANG DIEU KHIEN may in Bambu A1 qua LAN.
Chay tren PC, dien thoai/PC mo trinh duyet qua LAN. NGUOI DUNG bam nut dieu khien;
AI/Claude KHONG dinh vao (server chi gui lenh khi co POST tu trinh duyet).

Tinh nang:
  - Theo doi realtime (stage/%/lop/con-time/nozzle/bed/AMS/wifi) — tu refresh 2s.
  - Anh may in dong mo phong tien do in (scan-line dang len theo %).
  - Nut: Tam dung / Tiep tuc / DUNG (co xac nhan) — bam tu trinh duyet.
  - AMS Lite dung layout that (khe 1 4 / 2 3) + quan ly gam nhua con lai (sua tay,
    luu theo tag_uid RFID qua filament_store).
  - CANH BAO khi may loi / dung dot ngot (print_error, hms, FAILED, mat ket noi).

Dung:
  python bambu_web.py                 -> doc cau hinh tu .env / printer.local.json, cong 8787
  python bambu_web.py 8080
Yeu cau: pip install --user paho-mqtt ; may bat LAN Only. Access Code lay qua /bambu-check.
"""
import sys, os, ssl, json, time, threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import paho.mqtt.client as mqtt

import printer_config
import filament_store
import filament_ftp

HERE = os.path.dirname(os.path.abspath(__file__))
PRINTER_NAME = "LongPham A1-3"

# Cache job dang in: gam + anh model + toan bo thong so (tai 1 lan qua FTP khi doi file)
JOB = {"file": None, "weight": None, "thumb": None, "info": None, "fetching": False, "subtracted": set()}
JOB_LOCK = threading.Lock()

# Tu dien lenh G-code (Marlin + rieng Bambu) -> giai thich tieng Viet
GCODE_DICT = {
    "G0": ["Di chuyển nhanh", "Đưa đầu phun tới vị trí (KHÔNG đùn nhựa) — di chuyển không in."],
    "G1": ["Di chuyển + in", "Di chuyển có kèm đùn nhựa (E) — đây là lệnh vẽ ra vật thể."],
    "G2": ["Cung tròn thuận", "Nội suy cung tròn theo chiều kim đồng hồ."],
    "G3": ["Cung tròn nghịch", "Nội suy cung tròn ngược chiều kim đồng hồ."],
    "G4": ["Dừng chờ", "Tạm dừng một khoảng thời gian (dwell)."],
    "G28": ["Về gốc (Home)", "Đưa các trục về vị trí gốc bằng công tắc/cảm biến."],
    "G29": ["Cân chỉnh bàn", "Auto bed leveling — quét lưới độ cao bàn để bù vênh."],
    "G90": ["Toạ độ tuyệt đối", "Mọi toạ độ tính từ gốc máy."],
    "G91": ["Toạ độ tương đối", "Toạ độ tính từ vị trí hiện tại."],
    "G92": ["Đặt lại toạ độ", "Gán giá trị vị trí hiện tại (thường reset E về 0)."],
    "M17": ["Bật động cơ", "Cấp điện giữ các động cơ bước."],
    "M18": ["Tắt động cơ", "Ngắt giữ động cơ (có thể xoay tay)."],
    "M82": ["Đùn tuyệt đối", "Trục E tính theo giá trị tuyệt đối."],
    "M83": ["Đùn tương đối", "Trục E tính theo lượng thêm mỗi đoạn (Bambu dùng cái này)."],
    "M84": ["Tắt giữ động cơ", "Nhả động cơ khi rảnh."],
    "M104": ["Đặt nhiệt nozzle", "Set nhiệt độ đầu phun, KHÔNG chờ đạt."],
    "M109": ["Nhiệt nozzle + chờ", "Set nhiệt đầu phun và CHỜ tới khi đạt."],
    "M106": ["Bật quạt", "Bật quạt làm mát vật in, chỉnh tốc độ S0-255."],
    "M107": ["Tắt quạt", "Tắt quạt làm mát."],
    "M140": ["Đặt nhiệt bàn", "Set nhiệt độ bàn nhiệt, không chờ."],
    "M190": ["Nhiệt bàn + chờ", "Set nhiệt bàn và CHỜ tới khi đạt."],
    "M204": ["Gia tốc", "Đặt gia tốc in/di chuyển (mm/s²)."],
    "M205": ["Jerk/độ giật", "Giới hạn thay đổi vận tốc đột ngột."],
    "M220": ["Tốc độ %", "Override tốc độ in tổng thể theo %."],
    "M221": ["Lưu lượng %", "Override lượng đùn (flow) theo %."],
    "M400": ["Chờ hết chuyển động", "Đợi buffer chuyển động chạy xong."],
    "M73": ["Tiến độ in", "Báo % hoàn thành + thời gian còn lại lên màn hình."],
    "M900": ["Pressure Advance", "Bù áp suất đùn để cạnh sắc nét, giảm phình góc."],
    "M620": ["AMS nạp nhựa", "Lệnh riêng Bambu — chọn/nạp cuộn từ AMS."],
    "M621": ["AMS nhả nhựa", "Lệnh riêng Bambu — rút nhựa khỏi đầu phun."],
    "M622": ["Điều kiện (Bambu)", "Rẽ nhánh có điều kiện trong macro Bambu."],
    "M623": ["Kết thúc điều kiện", "Đóng khối điều kiện macro Bambu."],
    "M991": ["Macro hệ thống Bambu", "Lệnh nội bộ điều phối in của firmware Bambu."],
    "M1002": ["Macro hệ thống Bambu", "Lệnh nội bộ (kiểm tra/hiệu chỉnh) của Bambu."],
    "T0": ["Chọn đầu/khe 0", "Chuyển sang tool/khe nhựa 0."],
    "T1": ["Chọn đầu/khe 1", "Chuyển sang tool/khe nhựa 1."],
}

# Layout vat ly AMS Lite: id MQTT 0..3 -> so khe 1..4, sap xep tren-duoi:
#   khe 1 (id0)  khe 4 (id3)
#   khe 2 (id1)  khe 3 (id2)
SLOT_LABEL = {0: 1, 1: 2, 2: 3, 3: 4}


def load_cfg(argv):
    port = 8787
    rest = argv[:]
    if rest and rest[0].isdigit():
        port = int(rest.pop(0))
    host, serial, code = printer_config.load(rest)
    return port, host, serial, code


PORT, IP, SERIAL, CODE = load_cfg(sys.argv[1:])
REPORT = f"device/{SERIAL}/report"
REQUEST = f"device/{SERIAL}/request"

STATE = {"data": {}, "ts": 0, "connected": False, "rc": None}
LOCK = threading.Lock()
MQTT = {"client": None, "seq": 0}

# Anh may in + AMS Lite (serve truc tiep, mo phong)
def _load_img(name):
    try:
        with open(os.path.join(HERE, name), "rb") as f:
            return f.read()
    except OSError:
        return b""


A1_IMG = _load_img("BAMBULAB A1.jpg")
AMS_IMG = _load_img("AMS.jpg")


# ---------- MQTT ----------
def _send(payload):
    c = MQTT["client"]
    if not c:
        return False, "chua ket noi MQTT"
    MQTT["seq"] += 1
    try:
        c.publish(REQUEST, json.dumps(payload))
        return True, "ok"
    except Exception as e:
        return False, str(e)


def cmd_print(command):
    return _send({"print": {"sequence_id": str(MQTT["seq"]), "command": command, "param": ""}})


def on_connect(c, u, f, rc, *a):
    with LOCK:
        STATE["rc"] = rc
        STATE["connected"] = (rc == 0)
    if rc == 0:
        c.subscribe(REPORT)
        c.publish(REQUEST, json.dumps({"pushing": {"sequence_id": "0", "command": "pushall"}}))


def on_disconnect(c, u, rc, *a):
    with LOCK:
        STATE["connected"] = False


def _active_tag(data):
    ams = (data.get("ams") or {})
    try:
        active = int(ams.get("tray_now", 255))
    except (TypeError, ValueError):
        return None
    for u in ams.get("ams", []):
        for t in (u.get("tray") or []):
            try:
                if int(t.get("id")) == active:
                    return t.get("tray_uuid") or t.get("tag_uid")
            except (TypeError, ValueError):
                continue
    return None


CACHE_DIR = os.path.join(HERE, "job_cache")


def _cache_key(gcode_file):
    import re as _re
    return _re.sub(r"[^A-Za-z0-9._-]", "_", os.path.basename(gcode_file or ""))[:120]


def _load_cache(gcode_file):
    key = _cache_key(gcode_file)
    meta = os.path.join(CACHE_DIR, key + ".json")
    if not key or not os.path.isfile(meta):
        return None
    try:
        with open(meta, encoding="utf-8") as f:
            m = json.load(f)
    except (OSError, ValueError):
        return None
    thumb = None
    png = os.path.join(CACHE_DIR, key + ".png")
    if os.path.isfile(png):
        try:
            with open(png, "rb") as f:
                thumb = f.read()
        except OSError:
            pass
    return {"weight": m.get("weight"), "info": m.get("info"), "thumb": thumb}


def _save_cache(gcode_file, res):
    key = _cache_key(gcode_file)
    if not key or not res:
        return
    try:
        os.makedirs(CACHE_DIR, exist_ok=True)
        if res.get("thumb"):
            with open(os.path.join(CACHE_DIR, key + ".png"), "wb") as f:
                f.write(res["thumb"])
        with open(os.path.join(CACHE_DIR, key + ".json"), "w", encoding="utf-8") as f:
            json.dump({"weight": res.get("weight"), "info": res.get("info")}, f, ensure_ascii=False)
    except OSError as e:
        print("[cache] loi ghi:", e)


def maybe_fetch_job(gcode_file):
    """Lay gam + anh + thong so. Uu tien cache dia (tuc thi) -> chi FTP khi chua co."""
    if not gcode_file:
        return
    with JOB_LOCK:
        if JOB["file"] == gcode_file and (JOB["weight"] is not None or JOB["thumb"] is not None):
            return
        if JOB["fetching"]:
            return
    cached = _load_cache(gcode_file)
    if cached and (cached["thumb"] or cached["weight"] is not None):
        with JOB_LOCK:
            JOB["file"] = gcode_file
            JOB["weight"] = cached["weight"]
            JOB["thumb"] = cached["thumb"]
            JOB["info"] = cached.get("info")
        return
    with JOB_LOCK:
        JOB["fetching"] = True
        JOB["file"] = gcode_file
        JOB["weight"] = None
        JOB["thumb"] = None
        JOB["info"] = None

    def worker():
        res = {}
        try:
            res = filament_ftp.fetch_job(IP, CODE, gcode_file)
        except Exception as e:
            print("[FTP] loi tai job:", e)
        with JOB_LOCK:
            JOB["weight"] = res.get("weight")
            JOB["thumb"] = res.get("thumb")
            JOB["info"] = res.get("info")
            JOB["fetching"] = False
        _save_cache(gcode_file, res)
        print(f"[FTP] job '{gcode_file}': {res.get('weight')} g, thumb={'co' if res.get('thumb') else 'khong'}")
    threading.Thread(target=worker, daemon=True).start()


def _on_finish(data):
    """Khi in XONG: tru gam that (job_weight) khoi cuon dang dung, 1 lan/ban in."""
    with JOB_LOCK:
        w = JOB["weight"]
        f = JOB["file"]
        done = f in JOB["subtracted"]
    if not w or not f or done:
        return
    tag = _active_tag(data)
    if tag and filament_store.get(tag):
        filament_store.subtract(tag, w)
        with JOB_LOCK:
            JOB["subtracted"].add(f)
        print(f"[GAM] tru {w} g khoi cuon {tag[:8]} (job xong)")


def on_message(c, u, msg):
    try:
        d = json.loads(msg.payload.decode("utf-8", "ignore"))
    except Exception:
        return
    if "print" in d:
        with LOCK:
            prev = STATE["data"].get("gcode_state")
            STATE["data"].update(d["print"])
            STATE["ts"] = time.time()
            snap = dict(STATE["data"])
        gc = snap.get("gcode_state")
        gf = snap.get("gcode_file")
        if gc in ("RUNNING", "PAUSE") and gf:
            maybe_fetch_job(gf)
        if prev == "RUNNING" and gc == "FINISH":
            _on_finish(snap)


def mqtt_loop():
    while True:
        try:
            try:
                c = mqtt.Client(mqtt.CallbackAPIVersion.VERSION1)
            except Exception:
                c = mqtt.Client()
            c.username_pw_set("bblp", CODE)
            c.tls_set(cert_reqs=ssl.CERT_NONE, tls_version=ssl.PROTOCOL_TLS_CLIENT)
            c.tls_insecure_set(True)
            c.on_connect = on_connect
            c.on_disconnect = on_disconnect
            c.on_message = on_message
            c.connect(IP, 8883, 30)
            MQTT["client"] = c

            def repush():
                while True:
                    time.sleep(30)
                    try:
                        c.publish(REQUEST, json.dumps({"pushing": {"sequence_id": "0", "command": "pushall"}}))
                    except Exception:
                        break
            threading.Thread(target=repush, daemon=True).start()
            c.loop_forever()
        except Exception as e:
            with LOCK:
                STATE["connected"] = False
            MQTT["client"] = None
            print("[MQTT] reconnect sau loi:", e)
            time.sleep(5)


# ---------- Ghep du lieu nhua (AMS + store cuc bo) ----------
def build_filament():
    with LOCK:
        data = dict(STATE["data"])
    ams_root = (data.get("ams") or {})
    units = ams_root.get("ams") or []
    try:
        active = int(ams_root.get("tray_now", 255))
    except (TypeError, ValueError):
        active = 255
    try:
        pct = int(data.get("mc_percent"))
    except (TypeError, ValueError):
        pct = None
    with JOB_LOCK:
        jw = JOB["weight"]
    out = []
    for unit in units:
        for t in (unit.get("tray") or []):
            if not t.get("tray_type"):
                continue
            try:
                tid = int(t.get("id"))
            except (TypeError, ValueError):
                continue
            tag = t.get("tray_uuid") or t.get("tag_uid") or ""
            rec = filament_store.get(tag)
            color = str(t.get("tray_color") or "888888")[:6]
            is_active = (tid == active)
            # gam da dung o ban in hien tai (uoc theo % tien do) — chi cuon dang dung
            job_used = round(jw * pct / 100) if (is_active and jw and pct is not None) else None
            out.append({
                "id": tid,
                "slot": SLOT_LABEL.get(tid, tid + 1),
                "type": t.get("tray_sub_brands") or t.get("tray_type") or "?",
                "color": color,
                "tag_uid": tag,
                "machine_remain": t.get("remain"),
                "net": (rec or {}).get("net"),
                "remaining": (rec or {}).get("remaining"),
                "active": is_active,
                "job_used": job_used,
            })
    return out


# ---------- HTTP ----------
PAGE = r"""<!doctype html><html lang="vi"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>Bambu A1 — LongPham</title>
<style>
 :root{
   --bg0:#080b10;--bg1:#0e131b;--card1:#171d28;--card2:#1e2635;--line:#28324a;
   --txt:#eef3fb;--mut:#8ea0b8;--acc:#22c55e;--acc2:#16a34a;--amb:#f59e0b;--red:#ef4444;
   --cyan:#38bdf8;--pink:#f472b6;
   --sh:0 18px 34px -18px rgba(0,0,0,.85), 0 6px 12px -6px rgba(0,0,0,.6);
   --hl:inset 0 1px 0 rgba(255,255,255,.06), inset 0 0 0 1px rgba(255,255,255,.03);
 }
 *{box-sizing:border-box;-webkit-tap-highlight-color:transparent}
 body{margin:0;background:
     radial-gradient(1200px 600px at 50% -10%, #16233a 0%, transparent 60%),
     linear-gradient(180deg,var(--bg1),var(--bg0));
   color:var(--txt);font-family:-apple-system,"Segoe UI",Roboto,sans-serif;
   padding:14px 14px 30px;max-width:480px;margin:auto;min-height:100vh}
 h1{font-size:17px;font-weight:700;margin:2px 2px 14px;display:flex;align-items:center;gap:9px}
 .dot{width:10px;height:10px;border-radius:50%;background:#556;flex:0 0 auto}
 .on{background:var(--acc);box-shadow:0 0 0 4px rgba(34,197,94,.18),0 0 10px var(--acc)}
 .off{background:var(--red);box-shadow:0 0 0 4px rgba(239,68,68,.18)}
 .card{position:relative;background:linear-gradient(160deg,var(--card2),var(--card1));
   border-radius:18px;padding:16px;margin:12px 0;box-shadow:var(--sh),var(--hl)}
 .lbl{color:var(--mut);font-size:12.5px;font-weight:600;letter-spacing:.3px;text-transform:uppercase}

 /* HERO */
 .hero{display:flex;gap:14px;align-items:stretch;overflow:hidden}
 .stagebox{flex:1;min-width:0}
 .stage{font-size:27px;font-weight:800;letter-spacing:-.3px;margin:2px 0 2px;color:#f4f8ff}
 .job{font-size:13px;color:var(--mut);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
 .printer{position:relative;width:128px;flex:0 0 auto;display:flex;align-items:center;justify-content:center;
   border-radius:14px;overflow:hidden}
 .printer img{width:100%;height:auto;border-radius:14px;display:block;
   filter:drop-shadow(0 8px 14px rgba(0,0,0,.55))}
 .glow{position:absolute;inset:-10px;border-radius:50%;pointer-events:none;opacity:0;transition:opacity .4s}
 .printer.run .glow{opacity:1;background:radial-gradient(circle at 50% 45%,rgba(34,197,94,.26),transparent 62%)}
 .plabel{position:absolute;left:6px;bottom:6px;font-size:10px;font-weight:700;color:#eafff0;
   background:rgba(0,0,0,.55);padding:2px 6px;border-radius:6px;opacity:0}
 .printer.run .plabel{opacity:1}

 /* PROGRESS */
 .bar{height:15px;background:#0a0e16;border-radius:10px;overflow:hidden;margin:12px 0 8px;
   box-shadow:inset 0 2px 5px rgba(0,0,0,.7)}
 .fill{height:100%;width:0%;border-radius:10px;transition:width .6s cubic-bezier(.2,.7,.2,1);
   background:linear-gradient(90deg,var(--acc2),var(--acc),#4ade80);background-size:200% 100%;
   box-shadow:0 0 12px rgba(34,197,94,.5);animation:flow 2.2s linear infinite}
 @keyframes flow{to{background-position:-200% 0}}
 .prow{display:flex;justify-content:space-between;font-size:14px}
 .prow .big{font-size:22px;font-weight:800} .prow .mut{color:var(--mut)}

 /* CONTROL */
 .ctrl{display:grid;grid-template-columns:1fr 1fr 1fr;gap:11px;margin:12px 0}
 .btn{min-height:56px;border:none;border-radius:15px;font-size:15px;font-weight:800;color:#fff;
   cursor:pointer;display:flex;align-items:center;justify-content:center;gap:7px;
   box-shadow:var(--sh),inset 0 1px 0 rgba(255,255,255,.25);transition:transform .12s,filter .12s}
 .btn svg{width:20px;height:20px;fill:currentColor;flex:0 0 auto}
 .btn:active{transform:translateY(2px);filter:brightness(.92)}
 .btn:disabled{opacity:.38;box-shadow:var(--sh);cursor:not-allowed}
 .b-pause{background:linear-gradient(160deg,#fbbf24,#d97706)}
 .b-resume{background:linear-gradient(160deg,#34d399,#16a34a)}
 .b-stop{background:linear-gradient(160deg,#f87171,#dc2626)}
 .infolink{display:flex;align-items:center;justify-content:center;gap:8px;margin:2px 0 12px;
   min-height:50px;padding:12px;border-radius:14px;background:linear-gradient(160deg,var(--card2),var(--card1));
   color:var(--cyan);font-weight:700;font-size:14px;text-decoration:none;box-shadow:var(--sh),var(--hl)}
 .infolink svg{width:18px;height:18px;fill:currentColor}
 .infolink:active{transform:translateY(1px)}

 /* STAT TILES (number card 3D) */
 .grid{display:grid;grid-template-columns:1fr 1fr;gap:12px}
 .tile{position:relative;background:linear-gradient(160deg,var(--card2),var(--card1));
   border-radius:18px;padding:15px 16px;box-shadow:var(--sh),var(--hl);overflow:hidden}
 .tile .ic{position:absolute;top:13px;right:13px;width:22px;height:22px;opacity:.5}
 .tile .ic svg{width:100%;height:100%;fill:none;stroke:var(--mut);stroke-width:1.8}
 .num{font-size:34px;font-weight:800;letter-spacing:-1px;line-height:1.05;margin-top:6px;
   text-shadow:0 2px 0 rgba(0,0,0,.35),0 6px 14px rgba(0,0,0,.45)}
 .num .u{font-size:14px;font-weight:700;color:var(--mut);margin-left:3px}
 .sub{font-size:12.5px;color:var(--mut);margin-top:3px}
 .num.nz{color:#ffcaa8} .num.bed{color:#ff9db0}

 /* AMS */
 .amsnote{font-size:11px;color:var(--mut);font-weight:500;text-transform:none;letter-spacing:0}
 .amshead{display:flex;justify-content:space-between;align-items:center;gap:12px}
 .amsimg{width:104px;height:auto;flex:0 0 auto;border-radius:12px;background:#f4f6fb;padding:6px;
   box-shadow:var(--sh);opacity:.96}
 .ams{display:grid;grid-template-columns:1fr 1fr;gap:11px;margin-top:12px}
 .slot{position:relative;background:linear-gradient(160deg,var(--card2),#141a24);
   border-radius:16px;padding:12px;box-shadow:var(--sh),var(--hl);border:1px solid transparent}
 .slot.act{border-color:var(--acc);box-shadow:var(--sh),0 0 0 1px var(--acc),0 0 16px rgba(34,197,94,.35)}
 .slot .top{display:flex;align-items:center;gap:10px}
 .snum{width:30px;height:30px;flex:0 0 auto;border-radius:9px;display:flex;align-items:center;justify-content:center;
   font-weight:800;font-size:15px;color:#fff;background:linear-gradient(160deg,#2a3446,#1a2130);
   box-shadow:inset 0 1px 0 rgba(255,255,255,.15),0 3px 6px rgba(0,0,0,.5)}
 .sw{width:26px;height:26px;flex:0 0 auto;border-radius:50%;border:2px solid rgba(255,255,255,.15);
   box-shadow:0 2px 5px rgba(0,0,0,.5),inset 0 2px 4px rgba(255,255,255,.25)}
 .stype{font-size:12.5px;font-weight:700;line-height:1.15;flex:1;min-width:0;
   white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
 .gram{margin-top:9px}
 .gram .n{font-size:20px;font-weight:800} .gram .n .u{font-size:12px;color:var(--mut);font-weight:700}
 .gbar{height:7px;border-radius:5px;background:#0a0e16;overflow:hidden;margin-top:6px;box-shadow:inset 0 1px 3px rgba(0,0,0,.7)}
 .gbar > i{display:block;height:100%;border-radius:5px;background:linear-gradient(90deg,#f59e0b,#22c55e)}
 .gramrow{display:flex;align-items:center;justify-content:space-between;margin-top:8px}
 .edit{background:#222c3d;color:var(--cyan);border:1px solid var(--line);border-radius:9px;
   padding:7px 11px;font-size:12px;font-weight:700;cursor:pointer;display:flex;align-items:center;gap:5px;min-height:34px}
 .edit svg{width:14px;height:14px;fill:currentColor}
 .undecl{font-size:11.5px;color:var(--amb)}
 /* AMS Lite — 4 cuon nhua + dong chay (giong man hinh may) */
 .amsviz{display:grid;grid-template-columns:1fr 40px 1fr;grid-template-rows:1fr 1fr;gap:9px;margin-top:12px}
 .spool{position:relative;border-radius:13px;padding:10px;min-height:98px;display:flex;flex-direction:column;
   align-items:center;justify-content:center;cursor:pointer;box-shadow:var(--sh),inset 0 0 0 1px rgba(255,255,255,.10)}
 .spool .num{position:absolute;top:7px;left:8px;width:22px;height:22px;border-radius:50%;background:rgba(0,0,0,.42);
   display:flex;align-items:center;justify-content:center;font-weight:800;font-size:12px;color:#fff}
 .spool .flag{position:absolute;top:7px;right:8px;font-size:9px;font-weight:800;background:rgba(0,0,0,.5);color:#fff;padding:2px 6px;border-radius:6px}
 .spool .pla{font-size:24px;font-weight:900;letter-spacing:1.5px;line-height:1;text-shadow:0 1px 3px rgba(0,0,0,.35)}
 .spool .sub{font-size:10.5px;font-weight:700;opacity:.92;margin-top:2px}
 .spool .g{font-size:12.5px;font-weight:800;margin-top:6px;opacity:.95}
 .spool.act{box-shadow:var(--sh),0 0 0 2px #eafff0,0 0 18px rgba(234,255,240,.45)}
 .s1{grid-column:1;grid-row:1}.s4{grid-column:3;grid-row:1}.s2{grid-column:1;grid-row:2}.s3{grid-column:3;grid-row:2}
 .buffer{grid-column:2;grid-row:1/3;display:flex;align-items:stretch;justify-content:center}
 .tube{width:16px;border-radius:9px;background:linear-gradient(90deg,#1c2433,#33405a,#1c2433);position:relative;
   overflow:hidden;box-shadow:inset 0 0 5px rgba(0,0,0,.7)}
 .tube .flow{position:absolute;left:2px;right:2px;top:-100%;height:200%;
   background:repeating-linear-gradient(180deg,var(--fc,#22c55e) 0 6px,transparent 6px 15px);opacity:0}
 .buffer.run .tube .flow{opacity:.95;animation:flowdown .85s linear infinite}
 @keyframes flowdown{to{transform:translateY(25%)}}

 /* ALERT / TOAST */
 #alert{display:none;color:#fff;padding:15px;border-radius:15px;margin:12px 0;font-weight:800;
   font-size:16px;box-shadow:var(--sh);align-items:center;gap:10px;cursor:pointer;
   background:linear-gradient(160deg,#ef4444,#b91c1c);animation:blink 1.1s steps(2) infinite}
 #alert.al-error{background:linear-gradient(160deg,#ef4444,#b91c1c)}
 #alert.al-warn{background:linear-gradient(160deg,#f59e0b,#b45309)}
 #alert.al-done{background:linear-gradient(160deg,#22c55e,#15803d);animation:none}
 #alert svg{width:24px;height:24px;fill:#fff;flex:0 0 auto}
 @keyframes blink{50%{opacity:.6}}
 .sndbtn{margin-left:auto;background:#1e2635;border:1px solid var(--line);color:var(--cyan);
   border-radius:10px;padding:7px 11px;font-size:12px;font-weight:700;cursor:pointer;
   display:flex;align-items:center;gap:6px;min-height:36px}
 .sndbtn svg{width:15px;height:15px;fill:currentColor} .sndbtn.on{color:var(--acc);border-color:var(--acc)}
 .foot{color:var(--mut);font-size:12px;text-align:center;margin-top:14px;display:flex;align-items:center;justify-content:center;gap:6px}
 #toast{position:fixed;left:50%;bottom:20px;transform:translateX(-50%) translateY(10px);background:#0b1220;
   border:1px solid var(--line);color:#fff;padding:11px 18px;border-radius:12px;opacity:0;pointer-events:none;
   transition:opacity .25s,transform .25s;font-size:14px;box-shadow:var(--sh);z-index:50}
 #toast.show{opacity:1;transform:translateX(-50%) translateY(0)}
 @media (prefers-reduced-motion:reduce){*{animation:none!important;transition:none!important}}
</style></head><body>
<h1><span id="dot" class="dot"></span> Bambu A1 · <span id="name">—</span>
  <button id="sndBtn" class="sndbtn" onclick="enableSound()"><svg viewBox="0 0 24 24"><path d="M12 3a1 1 0 0 0-1 1v.28C8.5 4.9 7 7.1 7 9.7V13l-1.7 2.5A1 1 0 0 0 6.1 17h11.8a1 1 0 0 0 .8-1.5L17 13V9.7c0-2.6-1.5-4.8-4-5.42V4a1 1 0 0 0-1-1zm0 18a2.5 2.5 0 0 0 2.45-2h-4.9A2.5 2.5 0 0 0 12 21z"/></svg><span>Bật âm</span></button></h1>

<div id="alert" onclick="dismissAlert()"><svg viewBox="0 0 24 24"><path d="M1 21h22L12 2 1 21zm12-3h-2v-2h2v2zm0-4h-2v-4h2v4z"/></svg><span id="alertmsg"></span></div>

<div class="card hero">
  <div class="stagebox">
    <div class="lbl">Trạng thái</div>
    <div class="stage" id="stage">…</div>
    <div class="job" id="job">—</div>
    <div class="bar"><div class="fill" id="fill"></div></div>
    <div class="prow"><span class="big" id="pct">—%</span><span class="mut" id="rem">còn —</span></div>
    <div class="prow" style="margin-top:6px"><span class="mut">Lớp</span><span id="layer">—</span></div>
  </div>
  <div class="printer" id="printer">
    <div class="glow"></div>
    <img id="heroImg" src="/a1.jpg" alt="Model đang in" onerror="this.onerror=null;this.src='/a1.jpg'">
    <div class="plabel">đang in</div>
  </div>
</div>

<div class="ctrl">
  <button class="btn b-pause"  id="bPause"  onclick="cmd('pause')" aria-label="Tạm dừng">
    <svg viewBox="0 0 24 24"><path d="M6 5h4v14H6zM14 5h4v14h-4z"/></svg>Tạm dừng</button>
  <button class="btn b-resume" id="bResume" onclick="cmd('resume')" aria-label="Tiếp tục">
    <svg viewBox="0 0 24 24"><path d="M8 5v14l11-7z"/></svg>Tiếp tục</button>
  <button class="btn b-stop"   id="bStop"   onclick="stopPrint()" aria-label="Dừng hẳn">
    <svg viewBox="0 0 24 24"><path d="M6 6h12v12H6z"/></svg>DỪNG</button>
</div>

<a class="infolink" href="/info"><svg viewBox="0 0 24 24"><path d="M11 7h2v2h-2zM11 11h2v6h-2zM12 2a10 10 0 1 0 0 20 10 10 0 0 0 0-20zm0 18a8 8 0 1 1 0-16 8 8 0 0 1 0 16z"/></svg> Thông tin & phân tích lệnh G-code</a>

<div class="grid">
  <div class="tile">
    <div class="ic"><svg viewBox="0 0 24 24"><path d="M14 14.76V5a2 2 0 1 0-4 0v9.76a4 4 0 1 0 4 0z"/></svg></div>
    <div class="lbl">Nozzle</div>
    <div class="num nz"><span id="nz">—</span><span class="u">°C</span></div>
    <div class="sub" id="nzt">→ — °C</div>
  </div>
  <div class="tile">
    <div class="ic"><svg viewBox="0 0 24 24"><rect x="3" y="14" width="18" height="4" rx="1"/><path d="M6 14V9M12 14V7M18 14V9"/></svg></div>
    <div class="lbl">Bed</div>
    <div class="num bed"><span id="bed">—</span><span class="u">°C</span></div>
    <div class="sub" id="bedt">→ — °C</div>
  </div>
</div>

<div class="card">
  <div class="amshead">
    <div><div class="lbl">AMS Lite</div><div class="amsnote">khe 1-4 theo máy thật · gam bạn khai báo (RFID)</div></div>
    <img class="amsimg" src="/ams.jpg" alt="Sơ đồ AMS Lite 4 khe">
  </div>
  <div class="ams" id="ams">—</div>
</div>

<div class="grid">
  <div class="tile">
    <div class="ic"><svg viewBox="0 0 24 24"><path d="M12 12a4 4 0 0 1 4-4c3 0 4 2 4 4M12 12a4 4 0 0 1-4 4c-3 0-4-2-4-4M12 12a4 4 0 0 1 4 4c0 3-2 4-4 4M12 12a4 4 0 0 1-4-4c0-3 2-4 4-4"/></svg></div>
    <div class="lbl">Quạt (part)</div>
    <div class="num" id="fan" style="color:#a7f3d0">—</div>
  </div>
  <div class="tile">
    <div class="ic"><svg viewBox="0 0 24 24"><path d="M5 12.5a10 10 0 0 1 14 0M8 16a5 5 0 0 1 8 0"/><circle cx="12" cy="19" r="1" fill="currentColor" stroke="none"/></svg></div>
    <div class="lbl">Wi‑Fi</div>
    <div class="num" id="wifi" style="color:#bae6fd;font-size:26px">—</div>
  </div>
</div>

<div class="foot" id="foot">Đang tải…</div>
<div id="toast"></div>

<script>
const STAGE={IDLE:"Đang rảnh",PREPARE:"Đang chuẩn bị",RUNNING:"ĐANG IN",PAUSE:"Tạm dừng",FINISH:"In XONG",FAILED:"In LỖI",SLICING:"Đang slice"};
let prevState=null, wasConnected=false, connLost=false, curAlert=null, lastBeepTs=0, doneShown=false, dismissed=null, ac=null;
const PENCIL='<svg viewBox="0 0 24 24"><path d="M3 17.25V21h3.75L17.8 9.94l-3.75-3.75L3 17.25zM20.7 7.04a1 1 0 0 0 0-1.41l-2.34-2.34a1 1 0 0 0-1.41 0l-1.83 1.83 3.75 3.75 1.83-1.83z"/></svg>';

function toast(m){const t=document.getElementById("toast");t.textContent=m;t.classList.add("show");setTimeout(()=>t.classList.remove("show"),2500);}
function ensureAudio(){ if(!ac){ try{ ac=new (window.AudioContext||window.webkitAudioContext)(); }catch(e){} } if(ac&&ac.state==="suspended"){ try{ac.resume();}catch(e){} } }
function tone(f,d,type,delay){ if(!ac)return; setTimeout(()=>{ try{ const o=ac.createOscillator(),g=ac.createGain(); o.connect(g);g.connect(ac.destination); o.type=type||"sine"; o.frequency.value=f; const s=ac.currentTime; g.gain.setValueAtTime(0.25,s); g.gain.exponentialRampToValueAtTime(0.001,s+d); o.start(s); o.stop(s+d);}catch(e){} }, delay||0); }
function soundError(){ ensureAudio(); tone(880,.18,"square",0); tone(660,.2,"square",210); tone(880,.18,"square",440); }
function soundDone(){ ensureAudio(); tone(659,.16,"sine",0); tone(880,.16,"sine",170); tone(1046,.34,"sine",340); }
function soundWarn(){ ensureAudio(); tone(520,.2,"triangle",0); tone(400,.26,"triangle",230); }
function soundReconnect(){ ensureAudio(); tone(523,.14,"sine",0); tone(784,.2,"sine",150); }
function vibrate(p){ try{ if(navigator.vibrate) navigator.vibrate(p); }catch(e){} }
function notify(title,body){ try{ if("Notification" in window && Notification.permission==="granted") new Notification(title,{body:body||""}); }catch(e){} }
function enableSound(){ ensureAudio(); tone(880,.12,"sine",0); tone(1174,.14,"sine",130); try{ if("Notification" in window && Notification.permission==="default") Notification.requestPermission(); }catch(e){} const b=document.getElementById("sndBtn"); if(b){ b.classList.add("on"); b.querySelector("span").textContent="Âm bật"; } toast("Đã bật âm thanh + thông báo"); }
function dismissAlert(){ dismissed=curAlert; document.getElementById("alert").style.display="none"; }
function setAlert(type,msg){
  const el=document.getElementById("alert"); const key=type?(type+":"+msg):null;
  if(!type){ el.style.display="none"; curAlert=null; return; }
  if(key===dismissed) return;
  el.className="al-"+type; el.style.display="flex";
  document.getElementById("alertmsg").textContent=msg;
  if(curAlert!==key){ curAlert=key; lastBeepTs=Date.now();
    if(type==="done"){ soundDone(); notify("Bambu A1 — IN XONG",msg); vibrate([120,60,120]); }
    else if(type==="error"){ soundError(); notify("Bambu A1 — LỖI",msg); vibrate([220,90,220,90,220]); }
    else { soundWarn(); notify("Bambu A1 — Cảnh báo",msg); vibrate([160,80,160]); }
  } else if(type!=="done" && Date.now()-lastBeepTs>5000){ lastBeepTs=Date.now(); (type==="error"?soundError:soundWarn)(); vibrate([150]); }
}
function fmtMin(m){m=parseInt(m);if(isNaN(m))return"—";return m>=60?(Math.floor(m/60)+"h"+String(m%60).padStart(2,"0")+"m"):(m+"m");}

async function cmd(action){
  try{const r=await fetch("/api/cmd/"+action,{method:"POST"});const j=await r.json();
    toast(j.ok?("Đã gửi lệnh: "+action):("Lỗi: "+j.msg));}catch(e){toast("Lỗi gửi lệnh: "+e);}
}
function stopPrint(){ if(confirm("DỪNG hẳn bản in? Không thể hoàn tác.")) cmd("stop"); }

async function editGram(tag, slot, cur, net){
  if(!tag){ toast("Khe này chưa có cuộn RFID"); return; }
  const v=prompt("Khe "+slot+" — nhập số GAM nhựa còn lại:", (cur!=null?cur:net||1000));
  if(v===null) return;
  const g=parseInt(v); if(isNaN(g)||g<0){ toast("Số không hợp lệ"); return; }
  try{
    const r=await fetch("/api/filament",{method:"POST",headers:{"Content-Type":"application/json"},
      body:JSON.stringify({tag_uid:tag, remaining:g, net:(net||Math.max(1000,g))})});
    const j=await r.json();
    toast(j.ok?("Khe "+slot+": "+g+"g"):("Lỗi: "+(j.msg||"")));
  }catch(e){toast("Lỗi lưu: "+e);}
}

function lum(h){const r=parseInt(h.substr(0,2),16),g=parseInt(h.substr(2,2),16),b=parseInt(h.substr(4,2),16);return(0.299*r+0.587*g+0.114*b)/255;}
function renderAms(fil, printing){
  const by={}; (fil||[]).forEach(f=>by[f.id]=f);
  const SLOT={0:1,1:2,2:3,3:4};
  let anyActive=false, activeColor=null;
  function spool(id,cls){
    const f=by[id]; const slot=SLOT[id];
    if(!f) return '<div class="spool '+cls+'" style="background:#141a24;color:var(--mut)"><div class="num">'+slot+'</div><div class="sub">trống</div></div>';
    const col=(f.color||"888888").substr(0,6);
    const txt=lum(col)>0.62?"#141a24":"#ffffff";
    const net=f.net||1000;
    const used=(f.active&&f.job_used!=null)?f.job_used:0;
    const live=(f.remaining!=null)?Math.max(0,f.remaining-used):null;
    if(f.active){ anyActive=true; activeColor="#"+col; }
    return '<div class="spool '+cls+(f.active?' act':'')+'" style="background:#'+col+';color:'+txt+'"'
      +' onclick="editGram(\''+(f.tag_uid||'')+'\','+slot+','+(f.remaining!=null?f.remaining:'null')+','+net+')">'
      +'<div class="num">'+slot+'</div>'
      +(f.active?'<div class="flag">đang in</div>':'')
      +'<div class="pla">PLA</div><div class="sub">'+(f.type||'')+'</div>'
      +'<div class="g">'+(live!=null?(live+' g'+(used>0?(' (−'+used+')'):'')):'chạm để khai báo')+'</div></div>';
  }
  const a=spool(0,'s1'), b=spool(3,'s4'), c=spool(1,'s2'), d=spool(2,'s3');
  const run=(printing&&anyActive)?' run':'';
  const buf='<div class="buffer'+run+'"><div class="tube"><div class="flow" style="--fc:'+(activeColor||'#22c55e')+'"></div></div></div>';
  document.getElementById("ams").innerHTML='<div class="amsviz">'+a+b+buf+c+d+'</div>';
}
let heroFile=null;
function updateHero(hasThumb, gcodeFile){
  const img=document.getElementById("heroImg");
  if(hasThumb){
    if(gcodeFile!==heroFile){ img.src="/thumb.png?t="+Date.now(); heroFile=gcodeFile; }
  } else if(heroFile!==null){ img.src="/a1.jpg"; heroFile=null; }
}

async function tick(){
 try{
  const r=await fetch("/api/status",{cache:"no-store"});const s=await r.json();const d=s.data||{};
  document.getElementById("dot").className="dot "+(s.connected?"on":"off");
  document.getElementById("name").textContent=s.name||"—";
  const gc=d.gcode_state||"?";
  document.getElementById("stage").textContent=STAGE[gc]||gc;
  document.getElementById("job").textContent=d.subtask_name||d.gcode_file||"—";
  let pct=parseInt(d.mc_percent);if(isNaN(pct))pct=0;
  document.getElementById("fill").style.width=pct+"%";
  document.getElementById("pct").textContent=pct+"%";
  document.getElementById("rem").textContent="còn ~"+fmtMin(d.mc_remaining_time);
  document.getElementById("layer").textContent=(d.layer_num??"—")+" / "+(d.total_layer_num??"—");
  const rnd=v=>{v=parseFloat(v);return isNaN(v)?"—":Math.round(v);};
  document.getElementById("nz").textContent=rnd(d.nozzle_temper);
  document.getElementById("nzt").textContent="→ "+rnd(d.nozzle_target_temper)+" °C";
  document.getElementById("bed").textContent=rnd(d.bed_temper);
  document.getElementById("bedt").textContent="→ "+rnd(d.bed_target_temper)+" °C";
  document.getElementById("fan").textContent=(d.cooling_fan_speed??"—");
  document.getElementById("wifi").textContent=(d.wifi_signal||"—");
  // printer/model animation + anh model that
  const printing=(gc==="RUNNING");
  const pr=document.getElementById("printer");
  pr.classList.toggle("run",printing);
  updateHero(s.has_thumb, d.gcode_file);
  // buttons
  const paused=(gc==="PAUSE");
  document.getElementById("bPause").disabled=!printing;
  document.getElementById("bResume").disabled=!paused;
  document.getElementById("bStop").disabled=!(printing||paused);
  // AMS + gam nhua + dong chay
  renderAms(s.filament, printing);
  // ===== su kien: mat ket noi / in xong / loi =====
  const err=parseInt(d.print_error)||parseInt(d.mc_print_error_code)||0;
  const hms=(d.hms&&d.hms.length)?d.hms.length:0;
  if(!s.connected){
    if(wasConnected){ connLost=true; setAlert("warn","Mất kết nối máy in!"); }
  } else {
    if(connLost){ connLost=false; soundReconnect(); notify("Bambu A1 — Đã kết nối lại",""); vibrate([80,40,80]); toast("Đã kết nối lại máy in"); setAlert(null); }
    if(gc==="FINISH" && (prevState==="RUNNING"||doneShown)){
      doneShown=true; setAlert("done","Đã in XONG: "+(d.subtask_name||d.gcode_file||""));
    } else {
      doneShown=false;
      let type=null,msg=null;
      if(err&&err!==0){ type="error"; msg="Máy báo LỖI (mã "+err+")"; }
      else if(gc==="FAILED"){ type="error"; msg="Bản in THẤT BẠI"; }
      else if(hms>0){ type="error"; msg=hms+" cảnh báo HMS trên máy"; }
      else if(prevState==="RUNNING"&&gc==="IDLE"){ type="error"; msg="Máy đang in bỗng DỪNG đột ngột!"; }
      if(type) setAlert(type,msg); else setAlert(null);
    }
    wasConnected=true;
  }
  prevState=gc;
  const age=s.ts?Math.round((Date.now()/1000)-s.ts):null;
  document.getElementById("foot").innerHTML=(s.connected?'<span class="dot on"></span> Đã kết nối':'<span class="dot off"></span> Mất kết nối')+(age!=null?(" · cập nhật "+age+"s trước"):"");
 }catch(e){
   if(wasConnected) setAlert("warn","Mất kết nối (không tải được dữ liệu)!");
   document.getElementById("foot").textContent="Lỗi tải: "+e;
 }
}
tick();setInterval(tick,2000);
</script></body></html>"""


INFO_PAGE = r"""<!doctype html><html lang="vi"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Thông tin file in — Bambu A1</title>
<style>
 :root{--bg0:#080b10;--bg1:#0e131b;--card1:#171d28;--card2:#1e2635;--line:#28324a;
   --txt:#eef3fb;--mut:#8ea0b8;--acc:#22c55e;--cyan:#38bdf8;--amb:#f59e0b;
   --sh:0 16px 30px -16px rgba(0,0,0,.85);--hl:inset 0 1px 0 rgba(255,255,255,.06)}
 *{box-sizing:border-box}
 body{margin:0;background:linear-gradient(180deg,var(--bg1),var(--bg0));color:var(--txt);
   font-family:-apple-system,"Segoe UI",Roboto,sans-serif;padding:14px 14px 40px;max-width:620px;margin:auto}
 a.back{color:var(--cyan);text-decoration:none;font-weight:700;font-size:14px;display:inline-flex;align-items:center;gap:6px;margin-bottom:10px}
 h2{font-size:18px;margin:16px 2px 8px}
 .lbl{color:var(--mut);font-size:12px;font-weight:700;text-transform:uppercase;letter-spacing:.3px}
 .card{background:linear-gradient(160deg,var(--card2),var(--card1));border-radius:16px;padding:15px;margin:10px 0;box-shadow:var(--sh),var(--hl)}
 .stat{display:grid;grid-template-columns:1fr 1fr 1fr;gap:10px;text-align:center}
 .stat .n{font-size:22px;font-weight:800} .stat .u{font-size:12px;color:var(--mut)}
 table{width:100%;border-collapse:collapse;font-size:13.5px}
 td{padding:8px 6px;border-bottom:1px solid var(--line);vertical-align:top}
 td.k{color:var(--mut);width:55%} td.v{font-weight:700;text-align:right}
 .cmd{display:flex;gap:11px;padding:11px 6px;border-bottom:1px solid var(--line);align-items:flex-start}
 .badge{flex:0 0 auto;background:linear-gradient(160deg,#2a3446,#1a2130);color:var(--cyan);font-weight:800;
   font-size:13px;padding:6px 9px;border-radius:9px;box-shadow:inset 0 1px 0 rgba(255,255,255,.12);min-width:52px;text-align:center}
 .cname{font-weight:800;font-size:14px} .cdesc{font-size:12.5px;color:var(--mut);margin-top:2px}
 .cnt{flex:0 0 auto;color:var(--mut);font-size:12px;font-weight:700;align-self:center}
 .unk{color:var(--amb)}
 details{margin-top:8px} summary{cursor:pointer;color:var(--cyan);font-weight:700;font-size:13px;padding:6px 0}
 .foot{color:var(--mut);font-size:11.5px;text-align:center;margin-top:16px}
 .loading{color:var(--mut);text-align:center;padding:30px}
</style></head><body>
<a class="back" href="/"><svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor"><path d="M15 6l-6 6 6 6z"/></svg> Về dashboard</a>
<h2 id="title">Thông tin file in</h2>
<div id="root"><div class="loading">Đang tải thông số…</div></div>
<div class="foot">Chú giải G-code tham khảo: github.com/rjduran/bambu-gcode-reference · x1plus Gcode.md</div>
<script>
const LABELS={
 layer_height:["Chiều cao lớp","mm"],initial_layer_print_height:["Lớp đầu tiên","mm"],
 line_width:["Bề rộng đường","mm"],wall_loops:["Số vòng tường",""],
 top_shell_layers:["Lớp mặt trên",""],bottom_shell_layers:["Lớp đáy",""],
 sparse_infill_density:["Mật độ infill",""],sparse_infill_pattern:["Kiểu infill",""],
 outer_wall_speed:["Tốc độ tường ngoài","mm/s"],inner_wall_speed:["Tốc độ tường trong","mm/s"],
 sparse_infill_speed:["Tốc độ infill","mm/s"],internal_solid_infill_speed:["Tốc độ infill đặc","mm/s"],
 top_surface_speed:["Tốc độ mặt trên","mm/s"],travel_speed:["Tốc độ di chuyển","mm/s"],
 outer_wall_acceleration:["Gia tốc tường ngoài","mm/s²"],default_acceleration:["Gia tốc mặc định","mm/s²"],
 enable_support:["Bật support",""],support_type:["Kiểu support",""],support_style:["Style support",""],
 brim_type:["Kiểu brim",""],ironing_type:["Ironing",""],seam_position:["Vị trí đường nối",""],
 wall_generator:["Bộ tạo tường",""],nozzle_temperature:["Nhiệt nozzle","°C"],
 hot_plate_temp:["Nhiệt bàn","°C"],filament_type:["Loại nhựa",""],
 filament_max_volumetric_speed:["Trần lưu lượng","mm³/s"]
};
const ORDER=Object.keys(LABELS);
function fmtVal(v){ if(Array.isArray(v)) return v.join(", "); return String(v); }
function fmtTime(s){ s=parseInt(s); if(isNaN(s))return"—"; const h=Math.floor(s/3600),m=Math.round((s%3600)/60); return (h?h+"h":"")+m+"m"; }
function enableTxt(v){ const s=fmtVal(v); return s==="1"?"Bật":(s==="0"?"Tắt":s); }

async function load(){
  let jr={}, dict={};
  try{ jr=await (await fetch("/api/jobinfo",{cache:"no-store"})).json(); }catch(e){}
  try{ dict=await (await fetch("/api/gcodedict")).json(); }catch(e){}
  const root=document.getElementById("root");
  const info=jr.info;
  document.getElementById("title").textContent="File: "+(jr.file||"—");
  if(!info){ root.innerHTML='<div class="card loading">'+(jr.fetching?"Đang tải file từ máy in… (thử lại sau vài giây)":"Chưa có dữ liệu file in. Cần máy đang in / vừa in một file.")+'</div>'; setTimeout(load,4000); return; }
  const sl=info.slice||{};
  let html='<div class="card stat">'
    +'<div><div class="n">'+(jr.weight!=null?jr.weight:(sl.weight_g??"—"))+'</div><div class="u">gam</div></div>'
    +'<div><div class="n">'+fmtTime(sl.time_s)+'</div><div class="u">thời gian</div></div>'
    +'<div><div class="n">'+(sl.length_m??"—")+'</div><div class="u">mét nhựa</div></div></div>';
  // thong so chinh
  const cfg=info.config||{};
  let rows="";
  for(const k of ORDER){ if(cfg[k]===undefined) continue;
    let v=(k==="enable_support")?enableTxt(cfg[k]):fmtVal(cfg[k]);
    rows+='<tr><td class="k">'+LABELS[k][0]+(LABELS[k][1]?(' ('+LABELS[k][1]+')'):'')+'</td><td class="v">'+v+'</td></tr>';
  }
  if(rows) html+='<h2>Thông số chính</h2><div class="card"><table>'+rows+'</table></div>';
  // lenh gcode
  const cmds=info.commands||{};
  const keys=Object.keys(cmds).sort((a,b)=>cmds[b]-cmds[a]);
  if(keys.length){
    let clist="";
    for(const c of keys){
      const d=dict[c];
      const nm=d?d[0]:"(chưa có chú giải)";
      const ds=d?d[1]:"Lệnh G/M-code — tra thêm ở tài liệu tham khảo bên dưới.";
      clist+='<div class="cmd"><span class="badge">'+c+'</span><div style="flex:1"><div class="cname'+(d?'':' unk')+'">'+nm+'</div><div class="cdesc">'+ds+'</div></div><span class="cnt">'+cmds[c]+'×</span></div>';
    }
    html+='<h2>Lệnh G-code trong file <span class="lbl">('+keys.length+' loại)</span></h2><div class="card" style="padding:6px 12px">'+clist+'</div>';
  }
  // raw
  const allKeys=Object.keys(cfg).sort();
  if(allKeys.length){
    let raw="";
    for(const k of allKeys){ raw+='<tr><td class="k">'+k+'</td><td class="v">'+fmtVal(cfg[k])+'</td></tr>'; }
    html+='<details><summary>Toàn bộ thông số nâng cao ('+allKeys.length+' khoá)</summary><div class="card"><table>'+raw+'</table></div></details>';
  }
  root.innerHTML=html;
}
load();
</script></body></html>"""


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, body, ctype):
        b = body.encode("utf-8") if isinstance(body, str) else body
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(b)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(b)

    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if path.startswith("/api/status"):
            with LOCK:
                payload = {"connected": STATE["connected"], "ts": STATE["ts"], "rc": STATE["rc"],
                           "name": PRINTER_NAME, "data": STATE["data"]}
            payload["filament"] = build_filament()
            with JOB_LOCK:
                payload["job_weight"] = JOB["weight"]
                payload["has_thumb"] = bool(JOB["thumb"])
            self._send(200, json.dumps(payload), "application/json; charset=utf-8")
        elif path.startswith("/api/filament"):
            self._send(200, json.dumps({"filament": build_filament()}), "application/json; charset=utf-8")
        elif path.startswith("/api/jobinfo"):
            with JOB_LOCK:
                payload = {"file": JOB["file"], "weight": JOB["weight"],
                           "fetching": JOB["fetching"], "info": JOB["info"]}
            self._send(200, json.dumps(payload), "application/json; charset=utf-8")
        elif path.startswith("/api/gcodedict"):
            self._send(200, json.dumps(GCODE_DICT), "application/json; charset=utf-8")
        elif path == "/a1.jpg":
            if A1_IMG:
                self._send(200, A1_IMG, "image/jpeg")
            else:
                self._send(404, "no image", "text/plain")
        elif path == "/ams.jpg":
            if AMS_IMG:
                self._send(200, AMS_IMG, "image/jpeg")
            else:
                self._send(404, "no image", "text/plain")
        elif path == "/thumb.png":
            with JOB_LOCK:
                thumb = JOB["thumb"]
            if thumb:
                self._send(200, thumb, "image/png")
            else:
                self._send(404, "no thumb", "text/plain")
        elif path in ("/", "/index.html"):
            self._send(200, PAGE, "text/html; charset=utf-8")
        elif path == "/info":
            self._send(200, INFO_PAGE, "text/html; charset=utf-8")
        elif path == "/healthz":
            self._send(200, "ok", "text/plain")
        else:
            self._send(404, "not found", "text/plain")

    def _read_json(self):
        try:
            n = int(self.headers.get("Content-Length", 0))
            return json.loads(self.rfile.read(n).decode("utf-8")) if n else {}
        except (ValueError, OSError):
            return {}

    def do_POST(self):
        if self.path == "/api/cmd/pause":
            ok, msg = cmd_print("pause")
        elif self.path == "/api/cmd/resume":
            ok, msg = cmd_print("resume")
        elif self.path == "/api/cmd/stop":
            ok, msg = cmd_print("stop")
        elif self.path == "/api/filament":
            body = self._read_json()
            tag = (body.get("tag_uid") or "").strip()
            try:
                rem = float(body.get("remaining"))
            except (TypeError, ValueError):
                self._send(400, json.dumps({"ok": False, "msg": "remaining khong hop le"}), "application/json")
                return
            if not tag:
                self._send(400, json.dumps({"ok": False, "msg": "thieu tag_uid"}), "application/json")
                return
            rec = filament_store.set_remaining(tag, rem, body.get("net"))
            self._send(200, json.dumps({"ok": True, "rec": rec}), "application/json; charset=utf-8")
            return
        else:
            self._send(404, json.dumps({"ok": False, "msg": "unknown cmd"}), "application/json")
            return
        self._send(200, json.dumps({"ok": ok, "msg": msg}), "application/json; charset=utf-8")


def main():
    threading.Thread(target=mqtt_loop, daemon=True).start()
    srv = ThreadingHTTPServer(("0.0.0.0", PORT), H)
    print("=" * 56)
    print("  BAMBU WEB DASHBOARD + DIEU KHIEN dang chay")
    print(f"  May in : {IP}  serial {SERIAL}")
    print(f"  Tren PC : http://localhost:{PORT}")
    print(f"  Dien thoai (cung LAN): http://<IP-PC>:{PORT}")
    print("  Nut Pause/Resume/Stop = NGUOI DUNG bam (AI khong dieu khien).")
    print("  Ctrl+C de dung.")
    print("=" * 56)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nDung.")


if __name__ == "__main__":
    main()
