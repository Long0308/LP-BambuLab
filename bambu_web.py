#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
bambu_web.py — Web dashboard + BANG DIEU KHIEN may in Bambu A1 qua LAN.
Chay tren PC, dien thoai/PC mo trinh duyet qua LAN. NGUOI DUNG bam nut dieu khien;
AI/Claude KHONG dinh vao (server chi gui lenh khi co POST tu trinh duyet).

Tinh nang:
  - Theo doi realtime (stage/%/lop/con-time/nozzle/bed/AMS/wifi) — tu refresh 2s.
  - Nut: Tam dung / Tiep tuc / DUNG (co xac nhan) — bam tu trinh duyet.
  - CANH BAO khi may loi / dung dot ngot (print_error, hms, gcode_state=FAILED,
    hoac dang IN bong mat ket noi) -> banner do + tieng beep + thong bao trinh duyet.

Dung:
  python bambu_web.py                 -> doc IP/serial/code tu .mcp.json, cong 8787
  python bambu_web.py 8080
Yeu cau: pip install --user paho-mqtt ; may bat LAN Only + (nen) Developer Mode.
"""
import sys, os, ssl, json, time, threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import paho.mqtt.client as mqtt

HERE = os.path.dirname(os.path.abspath(__file__))


def load_cfg(argv):
    port = 8787
    rest = argv[:]
    if rest and rest[0].isdigit():
        port = int(rest.pop(0))
    if len(rest) >= 3:
        return port, rest[0], rest[1], rest[2]
    env = json.load(open(os.path.join(HERE, ".mcp.json"), encoding="utf-8"))["mcpServers"]["bambu-printer"]["env"]
    return port, env["PRINTER_HOST"], env["BAMBU_SERIAL"], env["BAMBU_TOKEN"]


PORT, IP, SERIAL, CODE = load_cfg(sys.argv[1:])
REPORT = f"device/{SERIAL}/report"
REQUEST = f"device/{SERIAL}/request"

STATE = {"data": {}, "ts": 0, "connected": False, "rc": None}
LOCK = threading.Lock()
MQTT = {"client": None, "seq": 0}


# ---------- MQTT ----------
def _send(payload):
    """Gui 1 lenh MQTT xuong may. Chi goi khi NGUOI DUNG bam nut (qua POST)."""
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


def cmd_pushall():
    return _send({"pushing": {"sequence_id": str(MQTT["seq"]), "command": "pushall"}})


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


def on_message(c, u, msg):
    try:
        d = json.loads(msg.payload.decode("utf-8", "ignore"))
    except Exception:
        return
    if "print" in d:
        with LOCK:
            STATE["data"].update(d["print"])
            STATE["ts"] = time.time()


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


# ---------- HTTP ----------
PAGE = r"""<!doctype html><html lang="vi"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Bambu A1 — LongPham</title>
<style>
 :root{--bg:#0f1216;--card:#1a1f27;--mut:#8b97a7;--acc:#22c55e;--warn:#ef4444;--txt:#e6edf3;--amb:#f59e0b}
 *{box-sizing:border-box} body{margin:0;background:var(--bg);color:var(--txt);
   font-family:-apple-system,Segoe UI,Roboto,sans-serif;padding:14px;max-width:640px;margin:auto}
 h1{font-size:18px;margin:2px 0 12px;display:flex;align-items:center;gap:8px}
 .dot{width:11px;height:11px;border-radius:50%;background:#555;display:inline-block}
 .on{background:var(--acc);box-shadow:0 0 8px var(--acc)} .off{background:var(--warn)}
 .stage{font-size:26px;font-weight:700;margin:6px 0}
 .card{background:var(--card);border-radius:14px;padding:14px;margin:10px 0}
 .bar{height:16px;background:#0b0e12;border-radius:8px;overflow:hidden;margin:8px 0}
 .fill{height:100%;background:linear-gradient(90deg,#16a34a,#22c55e);width:0%;transition:width .4s}
 .row{display:flex;justify-content:space-between;padding:5px 0;font-size:15px}
 .row .mut{color:var(--mut)} .grid{display:grid;grid-template-columns:1fr 1fr;gap:10px}
 .big{font-size:22px;font-weight:600} .unit{font-size:13px;color:var(--mut)}
 .ams{display:flex;gap:8px;flex-wrap:wrap} .tray{flex:1;min-width:70px;text-align:center;
   background:#0b0e12;border-radius:10px;padding:8px;font-size:12px}
 .sw{width:26px;height:26px;border-radius:50%;margin:0 auto 5px;border:2px solid #333}
 .foot{color:var(--mut);font-size:12px;text-align:center;margin-top:10px}
 .ctrl{display:grid;grid-template-columns:1fr 1fr 1fr;gap:10px;margin:10px 0}
 .btn{padding:16px 8px;border:none;border-radius:12px;font-size:16px;font-weight:700;color:#fff;cursor:pointer}
 .btn:active{transform:scale(.97)} .btn:disabled{opacity:.4}
 .b-pause{background:#d97706} .b-resume{background:#16a34a} .b-stop{background:#dc2626}
 #alert{display:none;background:var(--warn);color:#fff;padding:16px;border-radius:12px;margin:10px 0;
   font-weight:700;font-size:17px;animation:blink 1s steps(2) infinite}
 @keyframes blink{50%{opacity:.55}}
 #toast{position:fixed;left:50%;bottom:18px;transform:translateX(-50%);background:#222;color:#fff;
   padding:10px 16px;border-radius:10px;opacity:0;transition:opacity .3s;font-size:14px}
</style></head><body>
<h1><span id="dot" class="dot"></span> Bambu A1 · <span id="name">—</span></h1>

<div id="alert"></div>

<div class="card">
  <div class="stage" id="stage">…</div>
  <div id="job" style="font-size:14px;color:var(--mut)">—</div>
  <div class="bar"><div class="fill" id="fill"></div></div>
  <div class="row"><span id="pct">—%</span><span id="rem" class="mut">còn —</span></div>
  <div class="row"><span class="mut">Lớp</span><span id="layer">—</span></div>
</div>

<div class="ctrl">
  <button class="btn b-pause"  id="bPause"  onclick="cmd('pause')">⏸ Tạm dừng</button>
  <button class="btn b-resume" id="bResume" onclick="cmd('resume')">▶ Tiếp tục</button>
  <button class="btn b-stop"   id="bStop"   onclick="stopPrint()">⏹ DỪNG</button>
</div>

<div class="grid">
  <div class="card"><div class="mut">Nozzle</div><div class="big"><span id="nz">—</span><span class="unit">°C</span></div><div class="mut" id="nzt">→ — °C</div></div>
  <div class="card"><div class="mut">Bed</div><div class="big"><span id="bed">—</span><span class="unit">°C</span></div><div class="mut" id="bedt">→ — °C</div></div>
</div>
<div class="card"><div class="mut" style="margin-bottom:8px">AMS <span style="font-size:11px">· A1 Lite không cân nhựa — %  chỉ là máy báo, KHÔNG phản ánh nhựa đã dùng</span></div><div class="ams" id="ams">—</div></div>
<div class="grid">
  <div class="card"><div class="mut">Quạt (part)</div><div class="big" id="fan">—</div></div>
  <div class="card"><div class="mut">Wi‑Fi</div><div class="big" id="wifi">—</div></div>
</div>
<div class="foot" id="foot">Đang tải…</div>
<div id="toast"></div>

<script>
const STAGE={IDLE:"Đang rảnh",PREPARE:"Đang chuẩn bị",RUNNING:"ĐANG IN",PAUSE:"Tạm dừng",FINISH:"In XONG",FAILED:"In LỖI",SLICING:"Đang slice"};
let prevState=null, alerted=false, lastTs=0, lastSeen=0;
try{ if("Notification" in window && Notification.permission==="default") Notification.requestPermission(); }catch(e){}

function toast(m){const t=document.getElementById("toast");t.textContent=m;t.style.opacity=1;setTimeout(()=>t.style.opacity=0,2500);}
function beep(){try{const a=new (window.AudioContext||window.webkitAudioContext)();const o=a.createOscillator();const g=a.createGain();o.connect(g);g.connect(a.destination);o.type="square";o.frequency.value=880;g.gain.value=0.2;o.start();setTimeout(()=>{o.frequency.value=660;},250);setTimeout(()=>{o.stop();a.close();},550);}catch(e){}}
function notify(msg){try{if("Notification" in window && Notification.permission==="granted") new Notification("⚠ Máy in Bambu A1",{body:msg});}catch(e){}}
function raiseAlert(msg){const el=document.getElementById("alert");el.style.display="block";el.textContent="⚠ "+msg;if(!alerted){alerted=true;beep();notify(msg);}}
function clearAlert(){document.getElementById("alert").style.display="none";alerted=false;}

async function cmd(action){
  try{
    const r=await fetch("/api/cmd/"+action,{method:"POST"});
    const j=await r.json();
    toast(j.ok?("Đã gửi lệnh: "+action):("Lỗi: "+j.msg));
  }catch(e){toast("Lỗi gửi lệnh: "+e);}
}
function stopPrint(){ if(confirm("DỪNG hẳn bản in? Không thể hoàn tác.")) cmd("stop"); }

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
  const rem=parseInt(d.mc_remaining_time);
  document.getElementById("rem").textContent="còn ~"+(isNaN(rem)?"—":(rem>=60?(Math.floor(rem/60)+"h"+String(rem%60).padStart(2,"0")+"m"):rem+"m"));
  document.getElementById("layer").textContent=(d.layer_num??"—")+" / "+(d.total_layer_num??"—");
  const rnd=v=>{v=parseFloat(v);return isNaN(v)?"—":Math.round(v);};
  document.getElementById("nz").textContent=rnd(d.nozzle_temper);
  document.getElementById("nzt").textContent="→ "+rnd(d.nozzle_target_temper)+" °C";
  document.getElementById("bed").textContent=rnd(d.bed_temper);
  document.getElementById("bedt").textContent="→ "+rnd(d.bed_target_temper)+" °C";
  document.getElementById("fan").textContent=(d.cooling_fan_speed??"—");
  document.getElementById("wifi").textContent=(d.wifi_signal||"—");
  // nut theo trang thai
  const printing=(gc==="RUNNING"), paused=(gc==="PAUSE");
  document.getElementById("bPause").disabled=!printing;
  document.getElementById("bResume").disabled=!paused;
  document.getElementById("bStop").disabled=!(printing||paused);
  // AMS
  let ams=(d.ams&&d.ams.ams)?d.ams.ams:null;let html="";
  if(ams){for(const a of ams){for(const t of (a.tray||[])){if(t.tray_type){
    const col=t.tray_color?("#"+String(t.tray_color).slice(0,6)):"#333";
    const rem=parseInt(t.remain);
    html+='<div class="tray"><div class="sw" style="background:'+col+'"></div>'
      +(t.tray_sub_brands||t.tray_type||"?")+'<br>khe '+(t.id??"?")
      +((!isNaN(rem)&&rem>=0)?('<br><span class="mut">máy báo '+rem+'%</span>'):'<br><span class="mut">?%</span>')
      +'</div>';
  }}}}
  document.getElementById("ams").innerHTML=html||"—";
  // ===== CANH BAO LOI / DUNG DOT NGOT =====
  const err=parseInt(d.print_error)||parseInt(d.mc_print_error_code)||0;
  const hms=(d.hms&&d.hms.length)?d.hms.length:0;
  let alertMsg=null;
  if(err && err!==0) alertMsg="Máy báo LỖI (code "+err+")";
  else if(gc==="FAILED") alertMsg="Bản in THẤT BẠI (FAILED)";
  else if(hms>0) alertMsg=hms+" cảnh báo HMS trên máy";
  else if(prevState==="RUNNING" && (gc==="IDLE"||gc==="FAILED")) alertMsg="Máy đang in bỗng DỪNG đột ngột!";
  if(s.connected){ if(alertMsg) raiseAlert(alertMsg); else clearAlert(); }
  prevState=gc; lastSeen=Date.now()/1000; lastTs=s.ts||lastTs;
  const age=s.ts?Math.round((Date.now()/1000)-s.ts):null;
  document.getElementById("foot").textContent=(s.connected?"● Đã kết nối":"○ Mất kết nối")+(age!=null?(" · cập nhật "+age+"s trước"):"");
 }catch(e){
   // mat ket noi toi server/PC khi dang in
   if(prevState==="RUNNING") raiseAlert("Mất kết nối tới máy in khi đang in!");
   document.getElementById("foot").textContent="Lỗi tải: "+e;
 }
}
tick();setInterval(tick,2000);
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
        if self.path.startswith("/api/status"):
            with LOCK:
                payload = {"connected": STATE["connected"], "ts": STATE["ts"], "rc": STATE["rc"],
                           "name": "LongPham A1-3", "data": STATE["data"]}
            self._send(200, json.dumps(payload), "application/json; charset=utf-8")
        elif self.path in ("/", "/index.html"):
            self._send(200, PAGE, "text/html; charset=utf-8")
        elif self.path == "/healthz":
            self._send(200, "ok", "text/plain")
        else:
            self._send(404, "not found", "text/plain")

    def do_POST(self):
        # Lenh dieu khien — chi kich hoat khi NGUOI DUNG bam nut tren trinh duyet.
        if self.path == "/api/cmd/pause":
            ok, msg = cmd_print("pause")
        elif self.path == "/api/cmd/resume":
            ok, msg = cmd_print("resume")
        elif self.path == "/api/cmd/stop":
            ok, msg = cmd_print("stop")
        elif self.path == "/api/cmd/pushall":   # vo hai — chi xin may day trang thai (dung de test)
            ok, msg = cmd_pushall()
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
