#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""petg_monitor.py — Theo doi 1 job in tren Bambu A1 qua LAN, bat bat thuong NHUA.

CHI DOC (read-only): chi subscribe `device/<serial>/report` + xin `pushall` (lenh
chi doc trang thai). KHONG in / KHONG dung / KHONG chinh nhiet — moi lenh dieu khien
van do NGUOI DUNG bam tren web dashboard.

Dung:
  python petg_monitor.py                 # chay den khi job xong/loi (hoac MAX_H)
  python petg_monitor.py --status        # in tom tat file log moi nhat roi thoat
  python petg_monitor.py --max-h 8

Ghi ra:
  job_cache/<ten-job>__run.jsonl   timeline (1 dong / 20s, gitignored)
  PETG-ECO-BAI-HOC.md              bai hoc kinh nghiem (tu dong them khi co bat thuong)

Bat thuong theo doi (uu tien loi NHUA):
  1. HMS code (vd 1200-8007 = dun nhua that bai) + print_error != 0
  2. gcode_state doi trang thai (PAUSE = may dung cho xu ly)
  3. Nhiet voi lech > 12C so voi dich >= 3 mau lien tiep  -> nghi ket/nghien nhua
  4. Tien do dung >= 15 phut khong tang trong khi RUNNING  -> nghi ket
  5. Thoi gian con lai TANG (uoc luong tut)                -> nghi keo soi/bi ket
  6. Baseline: xac nhan dung file/so lop/nhiet cua profile PETG Eco
"""
from __future__ import annotations

import json
import os
import ssl
import sys
import time

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import printer_config  # noqa: E402

try:
    import paho.mqtt.client as mqtt
except ImportError:
    print("Thieu paho-mqtt:  python -m pip install --user paho-mqtt")
    sys.exit(1)

IP, SERIAL, CODE = printer_config.load()
REPORT = f"device/{SERIAL}/report"
REQUEST = f"device/{SERIAL}/request"

SAMPLE_S = 20
STALL_MIN = 15            # phut khong tang %  -> coi la ket
DEV_WARN_C = 12.0         # lech nhiet voi (C)
DEV_CONFIRM = 3           # so mau lien tiep
MAX_H = 8.0

CACHE = os.path.join(HERE, "job_cache")
LESSONS = os.path.join(HERE, "PETG-ECO-BAI-HOC.md")

# Ma HMS da xac minh — nguon: wiki.bambulab.com/en/hms/error-code (chi ghi ma chac chan).
# Key = cap "module-error" (2 nhom dau), tra cuu bang tien to nen khop ca ma 4 nhom.
HMS_VN = {
    "1200-8007": "ĐÙN NHỰA THẤT BẠI — kẹt extruder / kẹt sợi ('Failed to extrude'). "
                 "Kiểm tra sợi ở extruder; nặng thì nâng nozzle ~280 °C hoá lỏng cặn rồi rút (cold pull).",
    "1201-8015": "RÚT NHỰA KHỎI ĐẦU IN THẤT BẠI — sợi kẹt/gãy trong đầu in. Kiểm tra rồi bấm Retry.",
    "1200-8015": "RÚT NHỰA KHỎI ĐẦU IN THẤT BẠI — sợi kẹt, HOẶC sợi gãy bên trong extruder/ống PTFE. "
                 "Xảy ra ở BƯỚC NHẢ nhựa cuối bản in (không phải lỗi in). Kiểm tra đầu in rồi bấm Retry.",
}
STAGE_VN = {"IDLE": "rảnh", "PREPARE": "chuẩn bị", "RUNNING": "ĐANG IN",
            "PAUSE": "TẠM DỪNG", "FINISH": "XONG", "FAILED": "LỖI", "SLICING": "slice"}


def _hms_hex(attr, code) -> str:
    """attr+code (MQTT) -> '1200-1300-0002-0002' — dung dinh dang man hinh may.

    BUG DA SUA 2026-09-14: truoc day ghep (attr << 16) | code nen ma 1200-8015
    (print_error) va HMS that 1200-1300-0002-0002 bi hien thanh '1302-0002' vo nghia.
    2 field la 2 NUA DOC LAP cua ma HMS: attr = 2 nhom dau, code = 2 nhom sau.
    """
    a = f"{int(attr) & 0xFFFFFFFF:08X}"
    c = f"{int(code) & 0xFFFFFFFF:08X}"
    return f"{a[:4]}-{a[4:]}-{c[:4]}-{c[4:]}"


def _hms_vn(code4: str) -> str | None:
    """Tra nghia theo cap 'module-error' (khop ca ma 2 nhom lan 4 nhom)."""
    return HMS_VN.get(code4) or HMS_VN.get(code4[:9])


def _f(v, d=0.0):
    try:
        return float(v)
    except (TypeError, ValueError):
        return d


def _i(v, d=0):
    try:
        return int(v)
    except (TypeError, ValueError):
        return d


def snapshot(d: dict) -> dict:
    """Rut gon report -> dict nho de ghi timeline."""
    hms = []
    for h in (d.get("hms") or []):
        if isinstance(h, dict):
            hms.append(_hms_hex(h.get("attr"), h.get("code")))
    return {
        "t": time.strftime("%H:%M:%S"),
        "state": d.get("gcode_state"),
        "stage": d.get("stg_cur"),
        "layer": _i(d.get("layer_num")),
        "total": _i(d.get("total_layer_num")),
        "pct": _i(d.get("mc_percent")),
        "remain": _i(d.get("mc_remaining_time")),
        "noz": round(_f(d.get("nozzle_temper")), 1),
        "noz_t": _i(d.get("nozzle_target_temper")),
        "bed": round(_f(d.get("bed_temper")), 1),
        "bed_t": _i(d.get("bed_target_temper")),
        "fan": _i(d.get("cooling_fan_speed")),
        "hms": hms,
        "err": _i(d.get("print_error")) or _i(d.get("mc_print_error_code")),
        "ams": d.get("ams_status"),
        "wifi": d.get("wifi_signal"),
    }


class Mon:
    def __init__(self) -> None:
        self.d: dict = {}
        self.events: list[dict] = []
        self.samples: list[dict] = []
        self.dev_run = 0
        self.last_pct, self.last_pct_t = -1, time.time()
        self.last_remain = None
        self.seen_running = False
        self.base_done = False
        self.path = None
        self.fh = None

    # ---------- ghi ----------
    def log_line(self, obj: dict) -> None:
        if self.fh:
            self.fh.write(json.dumps(obj, ensure_ascii=False) + "\n")
            self.fh.flush()

    def event(self, kind: str, msg: str, extra: dict | None = None) -> None:
        ev = {"t": time.strftime("%Y-%m-%d %H:%M:%S"), "kind": kind, "msg": msg}
        if extra:
            ev.update(extra)
        if self.events and self.events[-1].get("msg") == msg:
            return                              # khong ghi lap lien tiep
        self.events.append(ev)
        print(f"[{ev['t']}] {kind}: {msg}", flush=True)
        self.log_line({"event": ev})
        self.lessons(ev)

    def lessons(self, ev: dict) -> None:
        """Ghi 1 su kien vao so BAI HOC (append, tao header neu chua co)."""
        new = not os.path.isfile(LESSONS)
        try:
            with open(LESSONS, "a", encoding="utf-8") as f:
                if new:
                    f.write("# PETG Eco — bài học kinh nghiệm (theo dõi tự động)\n\n"
                            "Ghi bởi `petg_monitor.py` trong lúc máy in. Mỗi mục là một "
                            "sự kiện THẬT đo được từ máy — không suy đoán.\n\n")
                extra = " · ".join(f"{k}={v}" for k, v in ev.items()
                                   if k not in ("t", "kind", "msg"))
                f.write(f"- **{ev['t']}** · `{ev['kind']}` — {ev['msg']}"
                        + (f"  \n  `{extra}`" if extra else "") + "\n")
        except OSError as e:
            print("khong ghi duoc bai hoc:", e)

    # ---------- phan tich ----------
    def check(self, s: dict) -> None:
        d = self.d
        if not self.seen_running and s["state"] == "RUNNING":
            self.seen_running = True
            os.makedirs(CACHE, exist_ok=True)
            self.path = os.path.join(CACHE, f"{d.get('subtask_name') or 'job'}__run.jsonl")
            self.fh = open(self.path, "a", encoding="utf-8")
            ams = []
            for u in ((d.get("ams") or {}).get("ams") or []):
                for t in (u.get("tray") or []):
                    if t.get("tray_type"):
                        ams.append(f"khe {_i(t.get('id'))+1}={t.get('tray_type')}"
                                   f"/{str(t.get('tray_color') or '')[:6]}")
            self.event("START",
                       f"job={d.get('subtask_name')} file={d.get('gcode_file')} "
                       f"layers={s['total']}", {"ams": ams})
            self.lessons({"t": time.strftime("%Y-%m-%d %H:%M:%S"), "kind": "BASELINE",
                          "msg": f"AMS lúc bắt đầu: {' | '.join(ams) or 'không đọc được'}"})
        # Baseline nhiet: CHI kiem khi da in THAT (layer_num >= 1). Luc moi START may con
        # chay chuoi start gcode (M109 S170/S190 de do ban roi S140 de can ban) — do KHONG
        # phai loi. LUU Y: mc_percent nhay len 3% ngay tu pha do ban nen KHONG dung pct.
        if self.seen_running and s["layer"] >= 1 and not self.base_done:
            self.base_done = True
            self.lessons({"t": time.strftime("%Y-%m-%d %H:%M:%S"), "kind": "BASELINE",
                          "msg": f"Lúc vào in thật: nozzle đích {s['noz_t']}C · "
                                 f"bàn đích {s['bed_t']}C · quạt {s['fan']}% · "
                                 f"{s['total']} lớp"})
            if s["noz_t"] != 240:
                self.event("WARN", f"nhiệt vòi đích {s['noz_t']}C KHÁC 240C của preset PETG Eco")
            if s["bed_t"] != 80:
                self.event("WARN", f"nhiệt bàn đích {s['bed_t']}C KHÁC 80C của preset PETG Eco")
            if s["fan"] > 0:
                self.event("WARN", f"quạt {s['fan']}% ở lớp đầu — preset đặt TẮT quạt lớp 1 "
                                   f"để bám bàn (close_fan_the_first_x_layers=1)")

        if s["hms"]:
            for c in s["hms"]:
                self.event("HMS", f"mã {c}" + (f" — {_hms_vn(c)}" if _hms_vn(c) else
                                               " (chưa có trong bảng — tra wiki.bambulab.com)"),
                           {"state": s["state"], "layer": s["layer"]})
        if s["err"]:
            e2 = _hms_hex(s["err"], 0)[:9]
            self.event("PRINT_ERROR", f"print_error={s['err']} ({e2})"
                       + (f" — {_hms_vn(e2)}" if _hms_vn(e2) else ""),
                       {"state": s["state"], "layer": s["layer"]})

        if self.samples and s["state"] != self.samples[-1]["state"]:
            self.event("STATE", f"{self.samples[-1]['state']} → {s['state']}",
                       {"layer": s["layer"], "pct": s["pct"]})

        if s["state"] == "RUNNING" and s["noz_t"] > 0:
            if abs(s["noz"] - s["noz_t"]) > DEV_WARN_C:
                self.dev_run += 1
                if self.dev_run == DEV_CONFIRM:
                    self.event("NHIET",
                               f"vòi lệch {s['noz']-s['noz_t']:+.1f}C so với {s['noz_t']}C "
                               f"({DEV_CONFIRM} mẫu liên tiếp) — nghi nghẽn/nghiền nhựa",
                               {"noz": s["noz"], "layer": s["layer"]})
            else:
                if self.dev_run >= DEV_CONFIRM:
                    self.event("NHIET", f"vòi về đúng đích ({s['noz']}C) — hết lệch")
                self.dev_run = 0

        if s["state"] == "RUNNING":
            if s["pct"] != self.last_pct:
                self.last_pct, self.last_pct_t = s["pct"], time.time()
            elif (time.time() - self.last_pct_t) > STALL_MIN * 60:
                self.event("KET", f"tiến độ đứng ở {s['pct']}% > {STALL_MIN} phút",
                           {"layer": s["layer"]})
                self.last_pct_t = time.time()      # chi bao lai sau moi STALL_MIN

        if self.last_remain is not None and s["state"] == "RUNNING":
            if s["remain"] > self.last_remain + 3:
                self.event("TIME", f"thời gian còn lại TĂNG {self.last_remain}→{s['remain']} "
                                   f"phút — dấu hiệu phải hãm tốc/chờ nhựa",
                           {"layer": s["layer"]})
        self.last_remain = s["remain"]

    def summary(self) -> str:
        ss = self.samples
        if not ss:
            return "khong co mau nao"
        noz = [x["noz"] for x in ss if x["state"] == "RUNNING"]
        bed = [x["bed"] for x in ss]
        lines = [
            f"- Mẫu: **{len(ss)}** · thời lượng theo dõi: **{len(ss)*SAMPLE_S/60:.0f} phút**",
            f"- Lớp: {ss[0]['layer']} → **{ss[-1]['layer']}**/{ss[-1]['total']} "
            f"({ss[-1]['pct']}%)",
        ]
        if noz:
            lines.append(f"- Nhiệt vòi khi in: min {min(noz):.0f} · max {max(noz):.0f} · "
                         f"tb {sum(noz)/len(noz):.1f} °C")
        lines.append(f"- Nhiệt bàn: min {min(bed):.0f} · max {max(bed):.0f} °C")
        ev = [e for e in self.events if e["kind"] not in ("START", "BASELINE")]
        lines.append(f"- Sự kiện bất thường: **{len(ev)}**" +
                     ("".join(f"\n    - `{e['kind']}` {e['msg']}" for e in ev) if ev else " (không có)"))
        return "\n".join(lines)


MON = Mon()


def on_connect(c, u, flags, rc, *a):
    if rc == 0:
        c.subscribe(REPORT)
        c.publish(REQUEST, json.dumps({"pushing": {"sequence_id": "0", "command": "pushall"}}))
    else:
        print(f"[LOI] MQTT rc={rc} — sai Access Code? Chua bat LAN Only/Developer Mode?",
              flush=True)


def on_message(c, u, msg):
    try:
        d = json.loads(msg.payload.decode("utf-8", "ignore"))
    except Exception:
        return
    if "print" in d:
        MON.d.update(d["print"])


def show_status() -> None:
    files = sorted((f for f in os.listdir(CACHE) if f.endswith("__run.jsonl")),
                   key=lambda f: os.path.getmtime(os.path.join(CACHE, f)), reverse=True)
    if not files:
        print("chua co file timeline nao"); return
    p = os.path.join(CACHE, files[0])
    rows, events = [], []
    for ln in open(p, encoding="utf-8"):
        try:
            o = json.loads(ln)
        except ValueError:
            continue
        (events if "event" in o else rows).append(o.get("event", o))
    print(f"=== {files[0]} ({len(rows)} mau) ===")
    if rows:
        a, b = rows[0], rows[-1]
        print(f"  {a['t']} → {b['t']} · lop {a['layer']}→{b['layer']}/{b['total']} "
              f"({b['pct']}%) · con {b['remain']} phut")
        print(f"  nozzle {b['noz']}→{b['noz_t']}C · ban {b['bed']}→{b['bed_t']}C · quat {b['fan']}")
    for e in events:
        print(f"  [{e['t']}] {e['kind']}: {e['msg']}")


def one_sample(quiet: bool = False) -> int:
    """Lay 1 mau DUY NHAT roi thoat: ghi vao timeline + in bat thuong.

    Dung cho NHIP TU KIEM TRA (heartbeat) — khong phu thuoc tien trinh nen, ma van
    co 1 diem du lieu moi lan chay. Tra ve so su kien bat thuong moi.
    """
    c = mqtt.Client(mqtt.CallbackAPIVersion.VERSION1)
    c.username_pw_set("bblp", CODE)
    c.tls_set(cert_reqs=ssl.CERT_NONE, tls_version=ssl.PROTOCOL_TLS_CLIENT)
    c.tls_insecure_set(True)
    c.on_connect, c.on_message = on_connect, on_message
    c.connect(IP, 8883, 30)
    c.loop_start()
    t0 = time.time()
    while not MON.d and time.time() - t0 < 15:
        time.sleep(0.5)
    c.loop_stop(); c.disconnect()
    if not MON.d:
        print("KHONG doc duoc may in (MQTT im lang)")
        return -1
    s = snapshot(MON.d)
    # doc lai timeline cu de biet su kien nao DA co (khong bao lai)
    seen = set()
    if os.path.isdir(CACHE):
        fs = sorted((f for f in os.listdir(CACHE) if f.endswith("__run.jsonl")),
                    key=lambda f: os.path.getmtime(os.path.join(CACHE, f)))
        if fs:
            for ln in open(os.path.join(CACHE, fs[-1]), encoding="utf-8"):
                try:
                    o = json.loads(ln)
                except ValueError:
                    continue
                if "event" in o:
                    seen.add((o["event"]["kind"], o["event"]["msg"]))
    MON.seen_running = True
    MON.base_done = True                      # khong lap lai kiem baseline
    MON.path = os.path.join(CACHE, f"{MON.d.get('subtask_name') or 'job'}__run.jsonl")
    os.makedirs(CACHE, exist_ok=True)
    MON.fh = open(MON.path, "a", encoding="utf-8")
    MON.check(s)
    MON.log_line(s)
    MON.fh.close()
    new = [e for e in MON.events if (e["kind"], e["msg"]) not in seen]
    if not quiet:
        print(f"{s['t']} {s['state']} lop {s['layer']}/{s['total']} {s['pct']}% "
              f"noz {s['noz']}→{s['noz_t']} bed {s['bed']}→{s['bed_t']} "
              f"quat {s['fan']} con {s['remain']}p hms={s['hms'] or '-'} err={s['err']}")
        for e in new:
            print(f"  MOI [{e['t']}] {e['kind']}: {e['msg']}")
    return len(new)


def main() -> None:
    args = sys.argv[1:]
    if "--status" in args:
        show_status(); return
    if "--sample" in args:
        one_sample(quiet="--quiet" in args); return
    global MAX_H
    if "--max-h" in args:
        MAX_H = float(args[args.index("--max-h") + 1])
    print(f"Theo doi {IP} (serial {SERIAL}) · mau {SAMPLE_S}s · toi da {MAX_H}h", flush=True)
    c = mqtt.Client(mqtt.CallbackAPIVersion.VERSION1)
    c.username_pw_set("bblp", CODE)
    c.tls_set(cert_reqs=ssl.CERT_NONE, tls_version=ssl.PROTOCOL_TLS_CLIENT)
    c.tls_insecure_set(True)
    c.on_connect, c.on_message = on_connect, on_message
    c.connect(IP, 8883, 30)
    c.loop_start()
    t0 = time.time()
    idle_after_run = 0
    try:
        while time.time() - t0 < MAX_H * 3600:
            time.sleep(SAMPLE_S)
            if not MON.d:
                continue
            s = snapshot(MON.d)
            MON.samples.append(s)
            MON.check(s)
            MON.log_line(s)
            print(f"  {s['t']} {s['state']:8} lop {s['layer']:3}/{s['total']:3} "
                  f"{s['pct']:3}% noz {s['noz']:5}→{s['noz_t']} bed {s['bed']:5} "
                  f"quat {s['fan']:3} hms={s['hms'] or '-'} err={s['err']}", flush=True)
            if MON.seen_running and s["state"] in ("FINISH", "FAILED", "IDLE"):
                idle_after_run += 1
                if idle_after_run >= 2:
                    break
    except KeyboardInterrupt:
        print("dung theo yeu cau")
    finally:
        c.loop_stop(); c.disconnect()
        if MON.fh:
            MON.fh.close()
        print("\n===== TOM TAT =====")
        print(MON.summary())
        with open(LESSONS, "a", encoding="utf-8") as f:
            f.write(f"\n## Kết thúc theo dõi — {time.strftime('%Y-%m-%d %H:%M')}\n"
                    f"{MON.summary()}\n\n")


if __name__ == "__main__":
    main()
