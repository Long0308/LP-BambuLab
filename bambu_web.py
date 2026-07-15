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
import sys, os, re, ssl, json, time, threading, shutil
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import paho.mqtt.client as mqtt

import printer_config
import filament_store
import filament_ftp
import slicer_cli
import analyzer
import optimize_e2e

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


def cmd_project_file(name, path):
    """Ra lenh in 1 file .gcode.3mf da co san tren may (NGUOI DUNG bam)."""
    p = (path or ("/" + name)).lstrip("/")
    payload = {"print": {
        "sequence_id": str(MQTT["seq"]),
        "command": "project_file",
        "param": "Metadata/plate_1.gcode",
        "subtask_name": name.replace(".gcode.3mf", "").replace(".3mf", ""),
        "url": "file:///sdcard/" + p,
        "bed_type": "auto",
        "timelapse": False, "bed_leveling": True, "flow_cali": False,
        "vibration_cali": True, "layer_inspect": False, "use_ams": False,
        "profile_id": "0", "project_id": "0", "subtask_id": "0", "task_id": "0",
    }}
    return _send(payload)


FILES_CACHE = {"ts": 0, "data": []}
THUMB_LOCK = threading.Lock()  # tai thumbnail tuan tu (Bambu FTP gioi han ket noi)

# Slice tren may tinh (Bambu Studio CLI) khi user upload file CHUA slice.
# Chi 1 job mot luc — CLI ngon RAM/CPU nhu mo ca app.
SLICE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "slice_jobs")
UPJOB = {"state": "idle", "name": None, "msg": "", "stats": None}
UPJOB_LOCK = threading.Lock()
LAST_SLICED = {"path": None, "name": None}   # file .gcode.3mf slice gan nhat -> cho tai ve
OPTJOB = {"state": "idle", "name": None, "msg": "", "report": None}
OPTJOB_LOCK = threading.Lock()
ANJOB = {"state": "idle", "name": None, "msg": "", "result": None}
ANJOB_LOCK = threading.Lock()


def _ams_filament_presets():
    """Sinh preset filament tu 4 khe AMS THAT (MQTT) — mau + loai + nhiet do that."""
    with LOCK:
        ams = (STATE["data"].get("ams") or {})
    out = []
    for u in ams.get("ams", []):
        for t in (u.get("tray") or []):
            sub = (t.get("tray_sub_brands") or t.get("tray_type") or "").strip()
            color = (t.get("tray_color") or "")[:6]
            if not sub or not color:
                continue
            slot = int(t.get("id", 0)) + 1
            preset = {
                "type": "filament",
                "from": "User",
                "inherits": f"Bambu {sub} @BBL A1",
                "name": f"{sub} #{color} (AMS khe {slot})",
                "filament_settings_id": [f"{sub} #{color} (AMS khe {slot})"],
                "filament_colour": [f"#{color}"],
                "version": "2.7.0.8",
            }
            if t.get("nozzle_temp_max"):
                preset["nozzle_temperature"] = [str(t["nozzle_temp_max"])]
            out.append({"slot": slot, "sub": sub, "color": f"#{color}", "preset": preset})
    return out


def _ams_first_color():
    """Mau hex cua khay AMS dau tien co nhua — de render preview dung mau that."""
    for f in _ams_filament_presets():
        return f["color"]
    return None


def _ams_tray_types():
    """Loai nhua THAT dang nam trong 4 khay AMS Lite (MQTT cache) — cung nguon voi
    panel AMS tren dashboard. Tra ['PLA LITE','PLA MATTE',...] theo khe 1-4;
    tra [] neu chua ket noi may (analyzer se fallback theo khai bao trong file)."""
    with LOCK:
        ams = (STATE["data"].get("ams") or {})
    out = []
    for u in ams.get("ams", []):
        for t in (u.get("tray") or []):
            typ = (t.get("tray_sub_brands") or t.get("tray_type") or "").strip()
            if typ:
                out.append(typ.upper())
    return out


def _run_analyze(name, src_path):
    """Phan tich chay NEN — file lon (300k+ tam giac) mat 30-60s, khong the
    giu request HTTP mo lau vay (Tailscale/trinh duyet cat -> tuong treo)."""
    try:
        res = analyzer.analyze(src_path, ams=_ams_tray_types(), color=_ams_first_color())
        res["ok"] = True
        res["name"] = name
        res["ams_filaments"] = _ams_filament_presets()   # preset filament tu AMS that
        with ANJOB_LOCK:
            ANJOB.update(state="done", msg="Xong", result=res)
    except Exception as e:                                # noqa: BLE001
        with ANJOB_LOCK:
            ANJOB.update(state="error", msg=f"Lỗi phân tích: {e}", result=None)
    finally:
        try:
            os.remove(src_path)
        except OSError:
            pass


def _run_optimize(name, src_path):
    """Slice BASELINE + 3 che do -> bao cao so sanh bang SO THAT. Khong dung may in."""
    try:
        with OPTJOB_LOCK:
            OPTJOB.update(state="running", name=name,
                          msg="Slice baseline + 3 chế độ (4 lần slice)…", report=None)
        rep = optimize_e2e.run_modes(src_path, os.path.join(SLICE_DIR, "e2e"))
        with OPTJOB_LOCK:
            if rep.get("error"):
                OPTJOB.update(state="error", msg=rep["error"])
            else:
                OPTJOB.update(state="done", msg="Xong", report=rep)
    except Exception as e:                                # noqa: BLE001
        with OPTJOB_LOCK:
            OPTJOB.update(state="error", msg=f"Lỗi: {e}")
    finally:
        try:
            os.remove(src_path)
        except OSError:
            pass


def _slice_and_push(name, src_path, mode=None, push=True):
    """Chay nen: slice file du an (config A1 that + khay AMS) -> day .gcode.3mf
    xuong may in (push=True) HOAC giu lai cho user TAI VE (push=False).

    push=False: user mo file trong Bambu Studio/Handy de REVIEW roi tu bam in —
    khong tu day xuong may. Toan bo do 1 cu bam upload cua NGUOI DUNG khoi dong.
    """
    base = re.sub(r"\.(3mf|stl)$", "", name, flags=re.I)
    out_name = base + ".gcode.3mf"
    try:
        mesh_info = None
        if name.lower().endswith(".stl"):
            with UPJOB_LOCK:
                UPJOB.update(state="slicing", name=name,
                             msg="Đang phân tích STL + bọc cấu hình A1…", stats=None)
            import stl_to_3mf
            wrapped = src_path + ".3mf"
            mesh_info = stl_to_3mf.wrap(src_path, wrapped)
            src_path = wrapped
        if mode:
            # Slice theo CHE DO user chon: ap preset suy luan vao config nhung roi slice
            with UPJOB_LOCK:
                UPJOB.update(state="slicing", name=name,
                             msg=f"Đang áp cấu hình chế độ + slice…", stats=None)
            import optimize_e2e
            an = analyzer.analyze(src_path, mode, ams=_ams_tray_types())
            tuned = src_path + f".{mode}.3mf"
            optimize_e2e.apply_preset(src_path, tuned, an["presets"][mode]["preset"])
            src_path = tuned
        with UPJOB_LOCK:
            UPJOB.update(state="slicing", name=name, msg="Đang slice trên máy tính…", stats=None)
        ok, res, stats = slicer_cli.slice_3mf(src_path, SLICE_DIR)
        if mesh_info:
            stats = {**(stats or {}), **mesh_info}
        if not ok:
            with UPJOB_LOCK:
                UPJOB.update(state="error", msg=res)
            return
        if not push:
            # CHI SLICE DE TAI VE — giu file .gcode.3mf lai, KHONG day xuong may.
            keep = os.path.join(SLICE_DIR, out_name)
            if os.path.abspath(res) != os.path.abspath(keep):
                shutil.copyfile(res, keep)
            with UPJOB_LOCK:
                LAST_SLICED.update(path=keep, name=out_name)
                UPJOB.update(state="done", name=out_name, download=out_name,
                             msg=f"Đã slice xong: {out_name} — bấm Tải về để mở/in trong Bambu Studio/Handy")
            return
        with UPJOB_LOCK:
            UPJOB.update(state="pushing", msg="Slice xong — đang chuyển xuống máy in…", stats=stats)
        with open(res, "rb") as f:
            data = f.read()
        with THUMB_LOCK:
            ok2, msg2 = filament_ftp.upload_file(IP, CODE, data, out_name)
        if ok2:
            FILES_CACHE["ts"] = 0
            keep = os.path.join(SLICE_DIR, out_name)      # giu ban sao de user cung tai duoc
            if os.path.abspath(res) != os.path.abspath(keep):
                try:
                    shutil.copyfile(res, keep)
                except OSError:
                    keep = res
            with UPJOB_LOCK:
                LAST_SLICED.update(path=keep, name=out_name)
                UPJOB.update(state="done", name=out_name, download=out_name,
                             msg=f"Đã slice + chuyển xuống máy: {out_name}")
        else:
            with UPJOB_LOCK:
                UPJOB.update(state="error", msg=f"Slice OK nhưng FTP lỗi: {msg2}")
    except Exception as e:                              # noqa: BLE001 - bao len UI
        with UPJOB_LOCK:
            UPJOB.update(state="error", msg=f"Lỗi slice: {e}")
    finally:
        try:
            os.remove(src_path)
        except OSError:
            pass


def get_files():
    """Danh sach file tren may, cache 25s de khong lam phien FTP."""
    now = time.time()
    with JOB_LOCK:
        if now - FILES_CACHE["ts"] < 25 and FILES_CACHE["data"]:
            return FILES_CACHE["data"]
    try:
        data = filament_ftp.list_files(IP, CODE)
    except Exception as e:
        print("[FTP] loi liet ke file:", e)
        return FILES_CACHE["data"]
    with JOB_LOCK:
        FILES_CACHE["ts"] = now
        FILES_CACHE["data"] = data
    return data


def ensure_file_meta(fpath):
    """Tai 1 file .3mf tren may (1 lan duy nhat) -> (anh PNG | None, da_slice | None).

    Cache ra job_cache/<key>.png + <key>.json nen lan sau tuc thi. Tra sliced=None
    khi khong tai duoc (de UI biet la "chua ro" chu khong phai "khong in duoc").
    """
    key = _cache_key(os.path.basename(fpath))
    png = os.path.join(CACHE_DIR, key + ".png")
    meta = os.path.join(CACHE_DIR, key + ".json")

    def _read_cache():
        thumb = None
        if os.path.isfile(png):
            try:
                with open(png, "rb") as f:
                    thumb = f.read()
            except OSError:
                pass
        if os.path.isfile(meta):
            try:
                with open(meta, encoding="utf-8") as f:
                    return thumb, json.load(f).get("sliced")
            except (OSError, ValueError):
                pass
        return thumb, None

    thumb, sliced = _read_cache()
    if sliced is not None:
        return thumb, sliced

    with THUMB_LOCK:                       # Bambu FTP chi chiu 1 ket noi -> tuan tu
        thumb, sliced = _read_cache()      # luong khac vua tai xong?
        if sliced is not None:
            return thumb, sliced
        try:
            m = filament_ftp.fetch_file_meta(IP, CODE, fpath)
        except Exception as e:             # noqa: BLE001 - chi log, UI van chay
            print("[filemeta] loi:", e)
            return None, None
        if not m:
            return None, None
        thumb, sliced = m.get("thumb"), bool(m.get("sliced"))
        try:
            os.makedirs(CACHE_DIR, exist_ok=True)
            if thumb:
                with open(png, "wb") as f:
                    f.write(thumb)
            with open(meta, "w", encoding="utf-8") as f:
                json.dump({"sliced": sliced}, f)
        except OSError:
            pass
        return thumb, sliced


def is_busy():
    with LOCK:
        gc = STATE["data"].get("gcode_state")
    return gc in ("RUNNING", "PAUSE", "PREPARE")


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
            with LOCK:               # snapshot (ip, code) NGUYEN KHOI — tranh cap ip-moi/code-cu
                _ip, _code = IP, CODE
            c.username_pw_set("bblp", _code)
            c.tls_set(cert_reqs=ssl.CERT_NONE, tls_version=ssl.PROTOCOL_TLS_CLIENT)
            c.tls_insecure_set(True)
            c.on_connect = on_connect
            c.on_disconnect = on_disconnect
            c.on_message = on_message
            c.connect(_ip, 8883, 30)
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


def update_printer_config(host: str, serial: str, code: str) -> None:
    """Doi IP/serial/access-code NONG: ghi .env + printer.local.json (deu gitignore),
    cap nhat globals roi ngat MQTT — mqtt_loop tu tao client moi voi thong so moi.
    Khong can restart server, khong can sua code."""
    global IP, SERIAL, CODE, REPORT, REQUEST
    # Ghi FILE truoc — neu ghi loi thi global GIU NGUYEN (state va file khong lech nhau)
    printer_config.update_env(host, serial, code)
    printer_config.save(host, serial, code)
    with LOCK:                       # doc/ghi bo (IP,CODE) nguyen khoi — mqtt_loop snapshot cung LOCK
        IP, SERIAL, CODE = host, serial, code
        REPORT = f"device/{serial}/report"
        REQUEST = f"device/{serial}/request"
    for k, v in zip(printer_config.ENV_KEYS, (host, serial, code)):
        os.environ[k] = v            # nguon uu tien 2 (environ) cung phai khop
    c = MQTT.get("client")
    if c:
        try:
            c.disconnect()           # loop_forever thoat -> vong while tao client moi
        except Exception:
            pass


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
 .cb{position:sticky;top:0;z-index:60;margin:-14px -14px 12px;padding:10px 14px;font-weight:800;font-size:13.5px;
   text-align:center;letter-spacing:.3px}
 .cb.on{background:linear-gradient(90deg,#065f46,#16a34a);color:#eafff3}
 .cb.off{background:linear-gradient(90deg,#7f1d1d,#dc2626);color:#fff}
 .cb.wait{background:#1e2635;color:#8ea0b8}
 .chips{display:flex;gap:7px;flex-wrap:wrap;margin-top:9px;align-items:center}
 .chip{display:flex;align-items:center;gap:6px;background:#0c111a;border:1px solid var(--line);
   border-radius:99px;padding:4px 10px 4px 5px;font-size:11.5px;font-weight:700}
 .chip i{width:15px;height:15px;border-radius:50%;border:1px solid rgba(255,255,255,.25);display:block}
 .up{padding:13px;border-radius:14px;background:linear-gradient(160deg,var(--card2),var(--card1));
   box-shadow:var(--sh),var(--hl);margin:2px 0 12px}
 .ubtn{width:100%;background:linear-gradient(160deg,#38bdf8,#0284c7);color:#fff;border:none;border-radius:12px;
   padding:13px;font-weight:800;font-size:14px;cursor:pointer;display:flex;align-items:center;justify-content:center;gap:7px}
 .ubtn:disabled{opacity:.45;cursor:not-allowed;background:#334155}
 .ubtn svg{width:17px;height:17px;fill:currentColor}
 .ubar{height:7px;border-radius:99px;background:#0c111a;border:1px solid var(--line);margin-top:10px;overflow:hidden;display:none}
 .ubar > i{display:block;height:100%;width:0;background:linear-gradient(90deg,#38bdf8,#22c55e);transition:width .2s}
 .uhint{font-size:11.5px;color:var(--mut);margin-top:8px}
 .linkrow{display:grid;grid-template-columns:1fr 1fr 1fr;gap:9px;margin:2px 0 12px}
 .infolink{display:flex;align-items:center;justify-content:center;gap:7px;text-align:center;
   min-height:52px;padding:10px;border-radius:14px;background:linear-gradient(160deg,var(--card2),var(--card1));
   color:var(--cyan);font-weight:700;font-size:13px;text-decoration:none;box-shadow:var(--sh),var(--hl)}
 .infolink svg{width:18px;height:18px;fill:currentColor;flex:0 0 auto}
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
<div id="connbar" class="cb wait">Đang kiểm tra kết nối máy in…</div>
<h1><span id="dot" class="dot"></span> Bambu A1 · <span id="name">—</span>
  <button id="sndBtn" class="sndbtn" onclick="enableSound()"><svg viewBox="0 0 24 24"><path d="M12 3a1 1 0 0 0-1 1v.28C8.5 4.9 7 7.1 7 9.7V13l-1.7 2.5A1 1 0 0 0 6.1 17h11.8a1 1 0 0 0 .8-1.5L17 13V9.7c0-2.6-1.5-4.8-4-5.42V4a1 1 0 0 0-1-1zm0 18a2.5 2.5 0 0 0 2.45-2h-4.9A2.5 2.5 0 0 0 12 21z"/></svg><span>Bật âm</span></button>
  <button class="sndbtn" onclick="toggleCfg()" title="Kết nối máy in"><svg viewBox="0 0 24 24"><path d="M19.4 13a7.6 7.6 0 0 0 .1-1l2-1.6a.5.5 0 0 0 .1-.6l-1.9-3.3a.5.5 0 0 0-.6-.2l-2.4 1a7.5 7.5 0 0 0-1.7-1l-.4-2.6a.5.5 0 0 0-.5-.4h-3.8a.5.5 0 0 0-.5.4l-.4 2.6a7.5 7.5 0 0 0-1.7 1l-2.4-1a.5.5 0 0 0-.6.2L2.4 9.8a.5.5 0 0 0 .1.6l2 1.6a7.6 7.6 0 0 0 0 2l-2 1.6a.5.5 0 0 0-.1.6l1.9 3.3c.1.2.4.3.6.2l2.4-1c.5.4 1.1.8 1.7 1l.4 2.6c0 .3.3.4.5.4h3.8c.2 0 .5-.1.5-.4l.4-2.6c.6-.2 1.2-.6 1.7-1l2.4 1c.2.1.5 0 .6-.2l1.9-3.3a.5.5 0 0 0-.1-.6l-2-1.6zM12 15.5A3.5 3.5 0 1 1 12 8.5a3.5 3.5 0 0 1 0 7z"/></svg><span>Kết nối</span></button></h1>

<div id="alert" onclick="dismissAlert()"><svg viewBox="0 0 24 24"><path d="M1 21h22L12 2 1 21zm12-3h-2v-2h2v2zm0-4h-2v-4h2v4z"/></svg><span id="alertmsg"></span></div>

<div class="card" id="cfgcard" style="display:none">
  <h3 style="margin-top:0">⚙ Kết nối máy in (LAN) — như Bambu Studio</h3>
  <div class="mut" style="font-size:12px;margin-bottom:8px">Xem trên màn hình máy in: <b>Cài đặt → WLAN</b> có IP + Access Code (đổi mỗi lần máy reset WLAN). Lưu vào <code>.env</code> trên server — không nằm trong git, không cần build lại code.</div>
  <div style="display:flex;gap:10px;flex-wrap:wrap;align-items:end">
    <label style="font-size:12px">IP máy in<br><input id="cfgHost" placeholder="192.168.x.x" style="width:140px;padding:7px;border-radius:8px;border:1px solid #334;background:#0f1523;color:#e8ecf4"></label>
    <label style="font-size:12px">Serial (giữ trống = giữ nguyên)<br><input id="cfgSerial" placeholder="" style="width:170px;padding:7px;border-radius:8px;border:1px solid #334;background:#0f1523;color:#e8ecf4"></label>
    <label style="font-size:12px">Access Code (8 ký tự)<br><input id="cfgCode" placeholder="" maxlength="8" style="width:120px;padding:7px;border-radius:8px;border:1px solid #334;background:#0f1523;color:#e8ecf4"></label>
    <button class="btn" onclick="saveCfg()" id="cfgSave" style="padding:9px 16px">Lưu &amp; kết nối lại</button>
  </div>
  <div class="mut" id="cfgHint" style="font-size:12px;margin-top:8px"></div>
</div>
<script>
async function loadCfg(){
  try{ const r=await fetch("/api/printer-config"); const j=await r.json();
    document.getElementById("cfgHost").value=j.host||"";
    document.getElementById("cfgSerial").placeholder=j.serial_set?"đã cấu hình (trống = giữ nguyên)":"chưa có";
    document.getElementById("cfgCode").placeholder=j.code_set?"••••••••  (trống = giữ nguyên)":"chưa có";
    document.getElementById("cfgHint").textContent=j.connected?"Đang kết nối OK với cấu hình hiện tại.":"⚠ Chưa kết nối được — kiểm tra IP/Access Code (mã đổi khi máy reset WLAN).";
  }catch(e){}
}
function toggleCfg(){ const c=document.getElementById("cfgcard");
  const show=c.style.display==="none"; c.style.display=show?"block":"none"; if(show) loadCfg(); }
async function saveCfg(){
  const b=document.getElementById("cfgSave"); b.disabled=true;
  try{
    const r=await fetch("/api/printer-config",{method:"POST",headers:{"Content-Type":"application/json"},
      body:JSON.stringify({host:document.getElementById("cfgHost").value,
                           serial:document.getElementById("cfgSerial").value,
                           code:document.getElementById("cfgCode").value})});
    const j=await r.json(); toast(j.msg||(j.ok?"Đã lưu":"Lỗi"));
    if(j.ok){ document.getElementById("cfgCode").value=""; setTimeout(loadCfg,4000); }
  }catch(e){ toast("Mất kết nối server"); }
  b.disabled=false;
}
</script>

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

<div class="linkrow">
  <a class="infolink" href="/info"><svg viewBox="0 0 24 24"><path d="M11 7h2v2h-2zM11 11h2v6h-2zM12 2a10 10 0 1 0 0 20 10 10 0 0 0 0-20zm0 18a8 8 0 1 1 0-16 8 8 0 0 1 0 16z"/></svg> Thông tin G-code</a>
  <a class="infolink" href="/files"><svg viewBox="0 0 24 24"><path d="M10 4H4a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2V8a2 2 0 0 0-2-2h-8l-2-2z"/></svg> File trên máy · chọn in</a>
  <a class="infolink" href="/analyze"><svg viewBox="0 0 24 24"><path d="M3 3v18h18v-2H5V3H3zm4 12h2v-5H7v5zm4 0h2V7h-2v8zm4 0h2v-3h-2v3z"/></svg> Phân tích .3mf / .stl</a>
</div>

<div class="chips" id="chips"></div>

<div class="up" id="up">
  <input type="file" id="fpick" accept=".3mf,.stl" style="display:none" onchange="pick()">
  <button class="ubtn" id="ubtn" onclick="document.getElementById('fpick').click()">
    <svg viewBox="0 0 24 24"><path d="M5 20h14v-2H5v2zM12 2L6.5 9.5h4V16h3V9.5h4L12 2z"/></svg>
    <span id="ulabel">Đẩy file .3mf / .stl lên máy in — chưa slice cũng được</span>
  </button>
  <div class="ubar" id="ubar"><i id="ufill"></i></div>
  <div class="uhint">File <b>đã slice</b> → chuyển thẳng xuống máy. File <b>dự án thô</b> → máy tính tự slice
  (Bambu Studio, ~1-2 phút) rồi chuyển, kèm thời gian in + gam nhựa. <span id="uhintx" style="color:var(--acc)"></span></div>
</div>

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

// ===== Upload + tu slice (tich hop hub) =====
function pick(){
  const inp=document.getElementById("fpick"), f=inp.files&&inp.files[0];
  inp.value="";
  if(!f) return;
  if(!/\.(3mf|stl)$/i.test(f.name)){ toast("Chỉ nhận file .3mf hoặc .stl"); return; }
  upload(f);
}
function upload(f){
  const btn=document.getElementById("ubtn"), lab=document.getElementById("ulabel");
  const bar=document.getElementById("ubar"), fill=document.getElementById("ufill");
  btn.disabled=true; bar.style.display="block"; fill.style.width="0";
  const mb=(f.size/1048576).toFixed(1);
  const xhr=new XMLHttpRequest();
  xhr.open("POST","/api/upload?name="+encodeURIComponent(f.name));
  xhr.upload.onprogress=e=>{
    if(!e.lengthComputable) return;
    const p=Math.round(e.loaded/e.total*100);
    fill.style.width=p+"%";
    lab.textContent = p<100 ? ("Đang đẩy… "+p+"% ("+mb+" MB)") : "Đang ghi vào máy in… (chờ máy xác nhận)";
  };
  xhr.onload=()=>{
    let j={}; try{ j=JSON.parse(xhr.responseText); }catch(e){}
    if(xhr.status===200 && j.ok && j.queued){ pollSlice(); return; }
    btn.disabled=false; bar.style.display="none";
    lab.textContent="Đẩy file .3mf / .stl lên máy in — chưa slice cũng được";
    if(xhr.status===200 && j.ok){ toast("Đã đẩy lên máy: "+j.name); }
    else{ toast("Lỗi: "+(j.msg||("HTTP "+xhr.status))); }
  };
  xhr.onerror=()=>{
    btn.disabled=false; bar.style.display="none";
    lab.textContent="Đẩy file .3mf / .stl lên máy in — chưa slice cũng được";
    toast("Mất kết nối khi đẩy file");
  };
  lab.textContent="Đang đẩy… 0% ("+mb+" MB)";
  xhr.send(f);
}
function fmtStats(s){
  if(!s) return "";
  const p=[];
  if(s.time) p.push("in "+s.time);
  if(s.weight_g) p.push(s.weight_g.toFixed(0)+" g");
  if(s.layers) p.push(s.layers+" lớp");
  if(s.dims) p.push(s.dims.join("×")+" mm");
  if(s.overhang_pct>0) p.push("overhang "+s.overhang_pct+"%");
  return p.join(" · ");
}
async function pollSlice(){
  const btn=document.getElementById("ubtn"), lab=document.getElementById("ulabel");
  const bar=document.getElementById("ubar"), fill=document.getElementById("ufill");
  btn.disabled=true; bar.style.display="block"; fill.style.width="100%";
  try{
    const j=await (await fetch("/api/upstatus",{cache:"no-store"})).json();
    if(j.state==="slicing"||j.state==="pushing"){
      lab.textContent=j.msg||"Đang xử lý…";
      setTimeout(pollSlice, 3000); return;
    }
    btn.disabled=false; bar.style.display="none";
    lab.textContent="Đẩy file .3mf / .stl lên máy in — chưa slice cũng được";
    if(j.state==="done"){
      toast("✔ "+j.msg+(j.stats?(" — "+fmtStats(j.stats)):""));
      const hint=document.getElementById("uhintx");
      if(hint&&j.stats) hint.textContent="Kết quả slice: "+fmtStats(j.stats);
    }
    else if(j.state==="error"){ toast("Lỗi: "+j.msg); }
  }catch(e){ setTimeout(pollSlice, 4000); }
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
  // Mau nhua THUC SU dung trong ban in (tu slice_info cua file dang in)
  const fils=s.job_filaments||[];
  document.getElementById("chips").innerHTML = fils.length
    ? fils.map(f=>'<span class="chip"><i style="background:'+(f.color||"#888")+'"></i>'
        +(f.type||"?")+' · '+(f.used_g||0)+' g</span>').join("")
    : "";
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
  // May in TAT: mat MQTT, HOAC "connected" nhung >90s khong co tin hieu (dung hinh)
  const offline=!s.connected||(age!==null&&age>90);
  const cb=document.getElementById("connbar");
  if(offline){ cb.className="cb off"; cb.textContent="⏻ MÁY IN ĐANG TẮT hoặc mất kết nối — sẽ tự báo khi máy bật lại"; }
  else { cb.className="cb on"; cb.textContent="● ĐÃ KẾT NỐI — "+(s.name||"máy in")+(age!=null?(" · tín hiệu "+age+"s trước"):""); }
  document.getElementById("foot").innerHTML=(s.connected?'<span class="dot on"></span> Đã kết nối':'<span class="dot off"></span> Mất kết nối')+(age!=null?(" · cập nhật "+age+"s trước"):"");
 }catch(e){
   if(wasConnected) setAlert("warn","Mất kết nối (không tải được dữ liệu)!");
   const cb=document.getElementById("connbar");
   cb.className="cb off"; cb.textContent="⏻ MẤT KẾT NỐI TỚI SERVER (máy tính tắt hoặc rớt mạng)";
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


FILES_PAGE = r"""<!doctype html><html lang="vi"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>File trên máy — Bambu A1</title>
<style>
 :root{--bg0:#080b10;--bg1:#0e131b;--card1:#171d28;--card2:#1e2635;--line:#28324a;
   --txt:#eef3fb;--mut:#8ea0b8;--acc:#22c55e;--cyan:#38bdf8;--amb:#f59e0b;--red:#ef4444;
   --sh:0 16px 30px -16px rgba(0,0,0,.85);--hl:inset 0 1px 0 rgba(255,255,255,.06)}
 *{box-sizing:border-box}
 body{margin:0;background:linear-gradient(180deg,var(--bg1),var(--bg0));color:var(--txt);
   font-family:-apple-system,"Segoe UI",Roboto,sans-serif;padding:14px 14px 40px;max-width:620px;margin:auto}
 a.back{color:var(--cyan);text-decoration:none;font-weight:700;font-size:14px;display:inline-flex;align-items:center;gap:6px;margin-bottom:10px}
 h2{font-size:18px;margin:12px 2px 6px}
 .busy{background:linear-gradient(160deg,#f59e0b,#b45309);color:#fff;padding:12px;border-radius:12px;font-weight:800;font-size:14px;margin:8px 0}
 .search{width:100%;padding:12px 14px;border-radius:12px;border:1px solid var(--line);background:#0c111a;color:var(--txt);font-size:15px;margin:6px 0 10px}
 .file{display:flex;gap:11px;align-items:center;padding:12px;border-radius:14px;background:linear-gradient(160deg,var(--card2),var(--card1));box-shadow:var(--sh),var(--hl);margin:9px 0}
 .fthumb{flex:0 0 auto;width:58px;height:58px;border-radius:10px;object-fit:contain;background:#0c111a;border:1px solid var(--line)}
 .fmeta{flex:1;min-width:0}
 .fname{font-weight:700;font-size:14px;word-break:break-word}
 .fsub{font-size:11.5px;color:var(--mut);margin-top:3px}
 .tag{display:inline-block;background:#0c111a;border:1px solid var(--line);border-radius:6px;padding:1px 6px;font-size:10.5px;margin-right:5px}
 .pbtn{flex:0 0 auto;background:linear-gradient(160deg,#34d399,#16a34a);color:#fff;border:none;border-radius:12px;
   padding:12px 15px;font-weight:800;font-size:14px;cursor:pointer;display:flex;align-items:center;gap:6px;min-height:46px}
 .pbtn:disabled{opacity:.4;cursor:not-allowed;background:#334155}
 .pbtn svg{width:16px;height:16px;fill:currentColor}
 .loading{color:var(--mut);text-align:center;padding:30px}
 .up{padding:13px;border-radius:14px;background:linear-gradient(160deg,var(--card2),var(--card1));
   box-shadow:var(--sh),var(--hl);margin:10px 0}
 .uprow{display:flex;gap:10px;align-items:center}
 .ubtn{flex:1;background:linear-gradient(160deg,#38bdf8,#0284c7);color:#fff;border:none;border-radius:12px;
   padding:13px;font-weight:800;font-size:14px;cursor:pointer;display:flex;align-items:center;justify-content:center;gap:7px}
 .ubtn:disabled{opacity:.45;cursor:not-allowed;background:#334155}
 .ubtn svg{width:17px;height:17px;fill:currentColor}
 .ubar{height:7px;border-radius:99px;background:#0c111a;border:1px solid var(--line);margin-top:10px;overflow:hidden;display:none}
 .ubar > i{display:block;height:100%;width:0;background:linear-gradient(90deg,#38bdf8,#22c55e);transition:width .2s}
 .uhint{font-size:11.5px;color:var(--mut);margin-top:8px}
 #toast{position:fixed;left:50%;bottom:20px;transform:translateX(-50%);background:#0b1220;border:1px solid var(--line);
   color:#fff;padding:11px 18px;border-radius:12px;opacity:0;transition:opacity .25s;font-size:14px;box-shadow:var(--sh);z-index:50;max-width:90%}
 #toast.show{opacity:1}
 .foot{color:var(--mut);font-size:11.5px;text-align:center;margin-top:16px}
</style></head><body>
<a class="back" href="/"><svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor"><path d="M15 6l-6 6 6 6z"/></svg> Về dashboard</a>
<h2>File in trên máy <span id="count" style="color:var(--mut);font-size:13px"></span></h2>
<div id="busy"></div>

<div class="up" id="up">
  <div class="uprow">
    <input type="file" id="fpick" accept=".3mf,.stl" style="display:none" onchange="pick()">
    <button class="ubtn" id="ubtn" onclick="document.getElementById('fpick').click()">
      <svg viewBox="0 0 24 24"><path d="M5 20h14v-2H5v2zM12 2L6.5 9.5h4V16h3V9.5h4L12 2z"/></svg>
      <span id="ulabel">Đẩy file .3mf / .stl từ máy tính lên máy in</span>
    </button>
  </div>
  <div class="ubar" id="ubar"><i id="ufill"></i></div>
  <div class="uhint">Nhận cả 2 loại: file <b>đã slice</b> (.gcode.3mf) → chuyển thẳng xuống máy in;
  file <b>dự án thô</b> (.3mf) → máy tính tự slice bằng Bambu Studio (vài phút) rồi mới chuyển.
  Tất cả qua LAN, không cần cloud. <span id="uhintx" style="color:var(--acc)"></span></div>
</div>

<input class="search" id="q" placeholder="Tìm file…" oninput="render()">
<div id="root"><div class="loading">Đang tải danh sách từ máy…</div></div>
<div class="foot">Nút "In" chỉ hoạt động khi máy RẢNH. Đây là lệnh điều khiển do BẠN bấm.</div>
<div id="toast"></div>
<script>
let FILES=[], BUSY=true, META={}, OBS=null;   // META: path -> true(da slice) / false / null(loi)
function toast(m){const t=document.getElementById("toast");t.textContent=m;t.classList.add("show");setTimeout(()=>t.classList.remove("show"),3000);}
function fsize(b){ if(!b) return "?"; const m=b/1048576; return m>=1?(m.toFixed(1)+" MB"):((b/1024).toFixed(0)+" KB"); }
function folder(p){ if(p.startsWith("/cache")) return "cache"; if(p.startsWith("/model")) return "model"; return "máy"; }
async function printFile(name,path){
  if(BUSY){ toast("Máy đang bận — chờ in xong mới in file mới"); return; }
  if(!confirm('IN file này?\n\n'+name+'\n\nMáy sẽ bắt đầu in ngay.')) return;
  try{
    const r=await fetch("/api/print",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({name:name,path:path})});
    const j=await r.json();
    toast(j.ok?("Đã gửi lệnh in: "+name):("Lỗi: "+(j.msg||"")));
    setTimeout(()=>location.href="/",1500);
  }catch(e){ toast("Lỗi gửi lệnh: "+e); }
}
function pick(){
  const inp=document.getElementById("fpick"), f=inp.files&&inp.files[0];
  inp.value="";                                  // cho phep chon lai cung file
  if(!f) return;
  if(!/\.(3mf|stl)$/i.test(f.name)){ toast("Chỉ nhận file .3mf hoặc .stl"); return; }
  upload(f);
}
function upload(f){
  const btn=document.getElementById("ubtn"), lab=document.getElementById("ulabel");
  const bar=document.getElementById("ubar"), fill=document.getElementById("ufill");
  btn.disabled=true; bar.style.display="block"; fill.style.width="0";
  const mb=(f.size/1048576).toFixed(1);
  const xhr=new XMLHttpRequest();
  xhr.open("POST","/api/upload?name="+encodeURIComponent(f.name));
  xhr.upload.onprogress=e=>{
    if(!e.lengthComputable) return;
    const p=Math.round(e.loaded/e.total*100);
    fill.style.width=p+"%";
    // 100% = trinh duyet gui xong cho SERVER. Server con phai ghi tiep vao may in
    // qua FTPS -> phai noi ro, khong de im lang nhu treo.
    lab.textContent = p<100 ? ("Đang đẩy… "+p+"% ("+mb+" MB)")
                            : "Đang ghi vào máy in… (chờ máy xác nhận)";
  };
  xhr.onload=()=>{
    let j={}; try{ j=JSON.parse(xhr.responseText); }catch(e){}
    if(xhr.status===200 && j.ok && j.queued){ pollSlice(); return; }   // chua slice -> server dang slice
    btn.disabled=false; bar.style.display="none";
    lab.textContent="Đẩy file .3mf / .stl từ máy tính lên máy in";
    if(xhr.status===200 && j.ok){ toast("Đã đẩy lên máy: "+j.name); load(); }
    else{ toast("Lỗi: "+(j.msg||("HTTP "+xhr.status))); }
  };
  xhr.onerror=()=>{
    btn.disabled=false; bar.style.display="none";
    lab.textContent="Đẩy file .3mf / .stl từ máy tính lên máy in";
    toast("Mất kết nối khi đẩy file");
  };
  lab.textContent="Đang đẩy… 0% ("+mb+" MB)";
  xhr.send(f);
}
function fmtStats(s){
  if(!s) return "";
  const p=[];
  if(s.time) p.push("in "+s.time);
  if(s.weight_g) p.push(s.weight_g.toFixed(0)+" g");
  if(s.layers) p.push(s.layers+" lớp");
  if(s.dims) p.push(s.dims.join("×")+" mm");
  if(s.overhang_pct>0) p.push("overhang "+s.overhang_pct+"%");
  return p.join(" · ");
}
async function pollSlice(){
  const btn=document.getElementById("ubtn"), lab=document.getElementById("ulabel");
  const bar=document.getElementById("ubar"), fill=document.getElementById("ufill");
  btn.disabled=true; bar.style.display="block"; fill.style.width="100%";
  try{
    const j=await (await fetch("/api/upstatus",{cache:"no-store"})).json();
    if(j.state==="slicing"||j.state==="pushing"){
      lab.textContent=j.msg||"Đang xử lý…";
      setTimeout(pollSlice, 3000); return;
    }
    btn.disabled=false; bar.style.display="none";
    lab.textContent="Đẩy file .3mf / .stl từ máy tính lên máy in";
    if(j.state==="done"){
      toast("✔ "+j.msg+(j.stats?(" — "+fmtStats(j.stats)):"")); load();
      const hint=document.getElementById("uhintx");
      if(hint&&j.stats) hint.textContent="Kết quả slice: "+fmtStats(j.stats);
    }
    else if(j.state==="error"){ toast("Lỗi: "+j.msg); }
  }catch(e){ setTimeout(pollSlice, 4000); }
}
function esc(s){ return String(s).replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/"/g,"&quot;"); }
// Khong the doan "da slice" bang duoi ten file: Bambu luu file DA slice thanh
// "<ten>.3mf" trong /cache chu khong phai ".gcode.3mf". Phai hoi server (server mo
// zip xem co Metadata/plate_N.gcode khong). Hoi luoi khi cuon toi, roi cache.
function statusHtml(p){
  const s=META[p];
  if(s===undefined) return ' · <span style="color:var(--mut)">đang kiểm tra…</span>';
  if(s===null)      return ' · <span style="color:var(--red)">không đọc được file</span>';
  return s ? ' · <span style="color:var(--acc)">đã slice — in được</span>'
           : ' · <span style="color:var(--amb)">chưa slice (file dự án)</span>';
}
function paint(row){
  const p=row.dataset.path;
  row.querySelector(".fstat").innerHTML=statusHtml(p);
  row.querySelector(".pbtn").disabled = BUSY || META[p]!==true;
}
async function checkMeta(row){
  const p=row.dataset.path;
  if(p in META){ paint(row); return; }
  try{
    const j=await (await fetch("/api/filemeta?path="+encodeURIComponent(p))).json();
    META[p]= j.ok ? !!j.sliced : null;
  }catch(e){ META[p]=null; }
  paint(row);
}
function render(){
  const q=(document.getElementById("q").value||"").toLowerCase();
  const list=FILES.filter(f=>f.name.toLowerCase().includes(q));
  document.getElementById("count").textContent="("+FILES.length+")";
  const root=document.getElementById("root");
  if(!FILES.length){
    root.innerHTML='<div class="loading">Máy chưa có file in nào (hoặc chưa đọc được thẻ SD).<br><br>'
      +'👆 Dùng nút <b>"Đẩy file .3mf"</b> phía trên để đưa file đầu tiên lên — '
      +'file chưa slice máy tính sẽ tự slice giúp bạn.</div>';
    return;
  }
  if(!list.length){ root.innerHTML='<div class="loading">Không có file khớp từ khoá tìm.</div>'; return; }
  let html="";
  for(const f of list){
    html+='<div class="file" data-path="'+esc(f.path)+'">'
      +'<img class="fthumb" loading="lazy" src="/api/filethumb?path='+encodeURIComponent(f.path)+'" onerror="this.style.visibility=\'hidden\'">'
      +'<div class="fmeta"><div class="fname">'+esc(f.name)+'</div>'
      +'<div class="fsub"><span class="tag">'+folder(f.path)+'</span>'+fsize(f.size)
      +'<span class="fstat"></span></div></div>'
      +'<button class="pbtn" disabled onclick="printFile('+JSON.stringify(f.name)+','+JSON.stringify(f.path)+')">'
      +'<svg viewBox="0 0 24 24"><path d="M8 5v14l11-7z"/></svg>In</button></div>';
  }
  root.innerHTML=html;
  if(OBS) OBS.disconnect();
  OBS=new IntersectionObserver(es=>{
    for(const e of es) if(e.isIntersecting){ OBS.unobserve(e.target); checkMeta(e.target); }
  },{rootMargin:"200px"});
  root.querySelectorAll(".file").forEach(r=>{ paint(r); OBS.observe(r); });
}
async function load(){
  try{
    const j=await (await fetch("/api/files",{cache:"no-store"})).json();
    FILES=j.files||[]; BUSY=!!j.busy;
    document.getElementById("busy").innerHTML=BUSY?'<div class="busy">Máy đang IN — nút "In" tạm khoá. Xong bản in mới chọn được file mới.</div>':'';
    render();
  }catch(e){ document.getElementById("root").innerHTML='<div class="loading">Lỗi tải danh sách: '+e+'</div>'; }
}
load();
</script></body></html>"""


ANALYZE_PAGE = r"""<!doctype html><html lang="vi"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Phân tích file — Bambu A1</title>
<style>
 :root{--bg0:#080b10;--bg1:#0e131b;--card1:#171d28;--card2:#1e2635;--line:#28324a;
   --txt:#eef3fb;--mut:#8ea0b8;--acc:#22c55e;--cyan:#38bdf8;--amb:#f59e0b;--red:#ef4444;
   --sh:0 16px 30px -16px rgba(0,0,0,.85);--hl:inset 0 1px 0 rgba(255,255,255,.06)}
 *{box-sizing:border-box}
 body{margin:0;background:linear-gradient(180deg,var(--bg1),var(--bg0));color:var(--txt);
   font-family:-apple-system,"Segoe UI",Roboto,sans-serif;padding:14px 14px 40px;max-width:680px;margin:auto}
 a.back{color:var(--cyan);text-decoration:none;font-weight:700;font-size:14px;display:inline-flex;align-items:center;gap:6px;margin-bottom:10px}
 h2{font-size:18px;margin:12px 2px 6px} h3{font-size:14px;margin:18px 2px 8px;color:var(--cyan)}
 .card{padding:14px;border-radius:14px;background:linear-gradient(160deg,var(--card2),var(--card1));
   box-shadow:var(--sh),var(--hl);margin:10px 0}
 .btn{width:100%;background:linear-gradient(160deg,#38bdf8,#0284c7);color:#fff;border:none;border-radius:12px;
   padding:14px;font-weight:800;font-size:14px;cursor:pointer}
 .btn:disabled{opacity:.45;background:#334155;cursor:not-allowed}
 .btn.go{background:linear-gradient(160deg,#34d399,#16a34a);margin-top:10px}
 .grid{display:grid;grid-template-columns:1fr 1fr;gap:9px;margin-top:4px}
 .kv{background:#0c111a;border:1px solid var(--line);border-radius:10px;padding:9px 11px}
 .kv b{display:block;font-size:16px;margin-top:2px}
 .kv span{font-size:11px;color:var(--mut)}
 .iss,.tip{border-radius:10px;padding:10px 12px;margin:7px 0;font-size:13px;line-height:1.5}
 .iss{background:rgba(239,68,68,.12);border-left:3px solid var(--red)}
 .tip{background:rgba(34,197,94,.12);border-left:3px solid var(--acc)}
 table{width:100%;border-collapse:collapse;font-size:12.5px;margin-top:6px}
 td,th{padding:6px 8px;border-bottom:1px solid var(--line);text-align:left}
 th{color:var(--mut);font-weight:600}
 .bad{color:var(--red);font-weight:700} .good{color:var(--acc);font-weight:700}
 .mut{color:var(--mut);font-size:12px}
 #toast{position:fixed;left:50%;bottom:20px;transform:translateX(-50%);background:#0b1220;border:1px solid var(--line);
   color:#fff;padding:11px 18px;border-radius:12px;opacity:0;transition:opacity .25s;font-size:14px;z-index:50;max-width:90%}
 #toast.show{opacity:1}
</style></head><body>
<a class="back" href="/"><svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor"><path d="M15 6l-6 6 6 6z"/></svg> Về dashboard</a>
<h2>Phân tích file in <span class="mut">· .3mf và .stl</span></h2>

<div class="card">
  <input type="file" id="fp" accept=".3mf,.stl" style="display:none" onchange="go()">
  <button class="btn" id="bt" onclick="document.getElementById('fp').click()">
    <span id="lb">Chọn file .3mf / .stl để phân tích</span></button>
  <div class="mut" style="margin-top:8px">Máy tính phân tích: kích thước · overhang · support · thử xoay ·
  Variable Layer Height · trần lưu lượng. <b>Chỉ tính toán — không đụng tới máy in.</b></div>
</div>
<div id="out"></div>

<details class="card" style="margin-top:14px">
  <summary style="cursor:pointer;font-weight:700;font-size:15px">📚 Mẹo gỡ support đẹp như mặt kính — PETG interface cho PLA</summary>
  <div class="mut" style="margin-top:10px;line-height:1.7">
  <b>Nguyên lý:</b> PLA và PETG <b>không dính nhau về hóa học</b>. Bình thường support cùng
  vật liệu phải chừa khe 0.2mm (Top Z distance) để bóc ra — chính khe đó làm mặt dưới rỗ.
  Đổi lớp tiếp xúc (interface) sang nhựa đối ứng thì ép khít <b>0mm</b> vẫn bóc rời →
  mặt dưới bóng như mặt trên.<br><br>
  <b>5 bước trong Bambu Studio (tab Support, bật Advanced):</b><br>
  1️⃣ Filament for Supports → <b>Support/raft interface = PETG</b> (đúng slot AMS đang nạp)<br>
  2️⃣ <b>Top Z distance = 0</b> · Bottom Z distance = 0<br>
  3️⃣ <b>Top interface spacing = 0</b> (interface đặc 100%)<br>
  4️⃣ Interface pattern = <b>Rectilinear Interlaced</b><br>
  5️⃣ TẮT <b>Independent support layer height</b> (khỏi bị làm tròn lệch lớp)<br><br>
  ✅ Hub <b>TỰ ÁP</b> bộ này khi bạn upload .3mf có khai báo PETG trong Project Filaments
  (thân PLA) — hoặc ngược lại PLA làm interface cho thân PETG.<br>
  🔁 Máy chỉ có 1 loại nhựa → hub fallback interface cùng vật liệu đúng slot thân in,
  khe an toàn 0.2mm.<br>
  ⚠️ <b>Cấm</b> để Z distance = 0 khi interface CÙNG vật liệu — support dính chết vào model.<br><br>
  <b>Cả 4 khay đều PLA (không có nhựa đối ứng) thì set thế này:</b><br>
  • Support/raft interface = <b>Default</b> (hoặc đúng khay thân in)<br>
  • <b>Top Z distance = 0.2mm</b> (vẫn khó bóc → tăng 0.25; đây là khe hở sống còn)<br>
  • Bottom Z distance = 0.2 · Top interface spacing = <b>0.5</b> (KHÔNG để 0)<br>
  • Interface pattern = Rectilinear Interlaced · Top interface layers = 2-3<br>
  → Bóc được nhưng mặt dưới hơi rỗ — đó là giới hạn vật lý của cùng nhựa; muốn bóng
  như mặt trên bắt buộc phải có nhựa đối ứng. Hub tự set đúng bộ này khi phân tích file.<br><br>
  ⏱️ Giá phải trả (trick PETG): single-nozzle đổi nhựa mỗi lớp interface → tốn thời gian + nhựa purge.<br><br>
  <b>An toàn trước khi in model lớn (case thất bại cộng đồng đã quét):</b><br>
  🧪 Lần đầu dùng trick: in <b>thử 1 miếng nhỏ có overhang</b> (~20 phút) trước, đừng đặt cược model 8 tiếng.<br>
  🔍 Import preset xong phải <b>chọn nó ở dropdown Process</b> — import KHÔNG tự áp; bóc không ra đa số do preset chưa được chọn, Z distance vẫn của preset cũ.<br>
  💧 Giữ nguyên flush volume Bambu tự tính khi đổi PLA↔PETG — giảm flush quá tay thì vùng nhựa trộn có thể bám nhẹ.<br>
  🔗 Kiểm chứng: forum.bambulab.com/t/5942 · 3djake.ie (PLA trick) · wiki.bambulab.com/en/software/bambu-studio/Seam
  </div>
</details>

<details style="max-width:900px;margin:14px auto 0;padding:0 16px">
  <summary style="cursor:pointer;font-weight:700;font-size:15px">📚 Fix mặt trên lấm tấm / lỗ li ti / vân thưa — vị trí chỉnh chính xác</summary>
  <div class="mut" style="margin-top:10px;line-height:1.7">
  <b>Triệu chứng:</b> mặt trên cùng có lỗ li ti, lấm tấm, vân thưa (đường in không khít nhau),
  rõ nhất ở góc nhọn và vùng hẹp.<br>
  <b>Thủ phạm:</b> đường in tròn đầu — chỗ queo và đầu mút để lại khe; nozzle to thì khe to
  (đồng thuận forum Bambu, thread 14.7k view).<br><br>
  <b>Cách chỉnh — theo tab Bambu Studio (bật Advanced):</b><br>
  1️⃣ <b>Quality › Line width › Top surface = 0.25</b> mm (nozzle 0.4) — đường mảnh nhét kín khe. Đây là fix số 1.<br>
  2️⃣ <b>Strength › Top/bottom shells › Top surface pattern = Monotonic line</b> — đi đường một chiều, khít nhất.<br>
  3️⃣ <b>Quality › Wall generator = Arachne</b> — độ rộng biến thiên, nhét được góc nhọn.<br>
  4️⃣ <b>Speed › Other layers speed › Top surface ≤ 150</b> mm/s — chậm để nhựa dàn đều.<br>
  5️⃣ <b>Strength › Top/bottom shells › Top shell layers ≥ 5</b> (đủ dày để lấp) — hub tính theo độ dày 1.0mm.<br>
  6️⃣ Còn rỗ nữa → <b>Quality › Ironing › Ironing Type = Top surfaces</b> (ủi phẳng, đánh đổi thời gian).<br><br>
  🔧 <b>Nguyên nhân GỐC = dòng chảy chưa chuẩn.</b> Preset chỉ giảm; muốn HẾT hẳn phải hiệu chỉnh cho ĐÚNG cuộn nhựa:<br>
  • Máy/ app: <b>Calibration › Flow Dynamics (PA)</b> + <b>Flow Rate</b> — mỗi cuộn/màu chạy 1 lần, lưu lại.<br>
  • Nhiệt độ cao hơn ~5-10°C cũng giúp nhựa dàn (PLA 220→230).<br><br>
  ✅ Hub <b>TỰ ÁP</b> mục 1-5 khi phân tích (mọi chế độ); mục 6 bật ở chế độ Đẹp khi có mặt phẳng lớn.<br>
  🔗 Kiểm chứng: forum.bambulab.com/t/top-surface-has-tiny-holes-and-gaps/5489 (14.7k view, đồng thuận frank.d/albin/Flashy_DE)
  </div>
</details>

<div id="toast"></div>
<script>
let FILE=null;
function toast(m){const t=document.getElementById("toast");t.textContent=m;t.classList.add("show");setTimeout(()=>t.classList.remove("show"),3500);}
function esc(s){return String(s).replace(/&/g,"&amp;").replace(/</g,"&lt;");}
function reset(msg){
  const bt=document.getElementById("bt"), lb=document.getElementById("lb");
  bt.disabled=false; lb.textContent="Chọn file .3mf / .stl để phân tích";
  if(msg) toast(msg);
}
function go(){
  const inp=document.getElementById("fp"); FILE=inp.files&&inp.files[0]; inp.value="";
  if(!FILE) return;
  const bt=document.getElementById("bt"), lb=document.getElementById("lb");
  bt.disabled=true;
  document.getElementById("out").innerHTML="";
  const mb=(FILE.size/1048576).toFixed(1);
  const xhr=new XMLHttpRequest();
  xhr.open("POST","/api/analyze?name="+encodeURIComponent(FILE.name));
  xhr.upload.onprogress=e=>{
    if(!e.lengthComputable) return;
    const p=Math.round(e.loaded/e.total*100);
    lb.textContent = p<100 ? ("Đang gửi… "+p+"% ("+mb+" MB)") : "Đã gửi — server bắt đầu phân tích…";
  };
  xhr.onload=()=>{
    let j={}; try{ j=JSON.parse(xhr.responseText); }catch(e){}
    if(xhr.status===200 && j.ok && j.queued){ pollAn(); }
    else reset("Lỗi: "+(j.msg||("HTTP "+xhr.status)));
  };
  xhr.onerror=()=>reset("Mất kết nối khi gửi file");
  lb.textContent="Đang gửi… 0% ("+mb+" MB)";
  xhr.send(FILE);
}
async function pollAn(){
  const lb=document.getElementById("lb");
  try{
    const j=await (await fetch("/api/anstatus",{cache:"no-store"})).json();
    if(j.state==="running"){
      lb.textContent=(j.msg||"Đang phân tích…")+" ("+(j.name||"")+")";
      setTimeout(pollAn, 2000); return;
    }
    if(j.state==="done" && j.result){ reset(); render(j.result); }
    else reset("Lỗi: "+(j.msg||"không rõ"));
  }catch(e){ setTimeout(pollAn, 3000); }
}
function render(j){
  const m=j.mesh||{}; let h="";
  h+='<div class="card"><h3 style="margin-top:0">'+esc(j.name)+'</h3>';
  h+='<div class="grid">'
    +kv("Kích thước",(m.dims||[]).join(" × ")+" mm")
    +kv("Số tam giác",(m.triangles||0).toLocaleString())
    +kv("Mặt hẫng >45°",(m.overhang_pct||0)+"% · "+(m.overhang_cm2||0)+" cm²")
    +kv("Bám bàn",(m.bed_cm2||0)+" cm²")
    +'</div>';
  h+='<div class="mut" style="margin-top:9px">'+(j.sliced?"Đã slice (có G-code)":"File thô — chưa slice")+'</div></div>';

  // Khay AMS THAT (MQTT) — quyet dinh cau hinh support interface. Khong sync duoc
  // thi phai canh bao TO: cau hinh suy theo file co the sai (Z=0 voi nhua khong co).
  {
    const af=j.ams_filaments||[], amsl=j.ams||[];
    h+='<div class="card"><h3 style="margin-top:0">Khay AMS thật <span class="mut" style="font-size:12px">· sync qua MQTT lúc phân tích</span></h3>';
    if(amsl.length){
      h+='<div class="grid">';
      if(af.length){ for(const t of af) h+=kv("Khe "+t.slot,'⬤ '+t.sub).replace('⬤','<span style="color:'+esc(t.color)+'">⬤</span>'); }
      else { for(let i=0;i<amsl.length;i++) h+=kv("Khe "+(i+1), amsl[i]); }
      h+='</div>';
      const hasPETG=amsl.some(t=>t.indexOf("PETG")===0), hasPLA=amsl.some(t=>t.indexOf("PLA")===0);
      h+= (hasPETG&&hasPLA)
        ? '<div class="tip" style="margin-top:9px">✓ Có cặp PLA + PETG thật trong khay — cấu hình support interface Z=0 (gỡ đẹp) dùng được. Khai báo cả 2 nhựa trong Project Filaments để hub tự áp.</div>'
        : '<div class="iss" style="margin-top:9px">Khay chỉ có 1 họ nhựa ('+esc(amsl.join(", "))+') — hub dùng cấu hình interface CÙNG vật liệu (khe hở 0.2mm, an toàn). KHÔNG tự ý chỉnh Z distance = 0.</div>';
    } else {
      h+='<div class="iss">⚠️ CHƯA SYNC ĐƯỢC KHAY AMS (máy in tắt / mất kết nối) — cấu hình support bên dưới suy theo KHAI BÁO TRONG FILE, có thể lệch thực tế. Bật máy in rồi phân tích lại để chắc chắn.</div>';
    }
    h+='</div>';
  }

  if(j.issues&&j.issues.length){ h+='<div class="card"><h3 style="margin-top:0">Vấn đề phát hiện</h3>';
    for(const i of j.issues) h+='<div class="iss">'+esc(i)+'</div>'; h+='</div>'; }
  if(j.tips&&j.tips.length){ h+='<div class="card"><h3 style="margin-top:0">Khuyến nghị</h3>';
    for(const t of j.tips) h+='<div class="tip">'+esc(t)+'</div>'; h+='</div>'; }

  if(j.rotations&&j.rotations.length){
    h+='<div class="card"><h3 style="margin-top:0">Thử xoay 2 trục X + Y — tìm mặt úp tốt nhất</h3>'
     +'<div class="mut" style="font-size:12px;margin-bottom:8px">Tiêu chí xếp hạng: ① <b>SUPPORT ít nhất</b> — số cm³ là ƯỚC LƯỢNG TƯƠNG ĐỐI (diện tích hẫng × chiều cao cột chống) để SO SÁNH giữa các hướng, KHÔNG phải gam thật (support in ở ~15% mật độ nên nhẹ hơn nhiều). Điểm mấu chốt: hướng bám bàn to mà support nhiều thì vẫn IN LÂU → xếp support trước. → ② tiếp xúc bàn lớn (bám chắc, chống warp) → ③ thấp nhất. Nguyên lý Tweaker (Schranz 2016 — Auto-Orientation của Cura) + bổ sung ước lượng support theo chiều cao.</div>'
     +'<table><tr><th>Hướng</th><th>Support</th><th>Overhang</th><th>Bám bàn</th><th>Cao</th><th>Dùng được?</th></tr>';
    for(const r of j.rotations){
      const isCur=(r.axis==="X"||r.axis==null)&&(r.angle===0||r.angle_x===0);
      const style=r.recommend?' style="background:rgba(34,197,94,.16)"':(isCur?' style="background:rgba(56,189,248,.1)"':'');
      const ax=r.axis||"X", ang=(r.angle!=null?r.angle:r.angle_x);
      h+='<tr'+style+'><td>'+ax+' '+ang+'°'
       +(isCur?' <span class="mut">(hiện tại)</span>':'')
       +(r.recommend?' <b style="color:#22c55e">★ ĐỀ XUẤT</b>':'')+'</td>'
       +'<td><b>~'+(r.support_cm3!=null?r.support_cm3:'?')+' cm³</b></td>'
       +'<td>'+r.overhang_pct+'%</td><td>'+r.bed_cm2+' cm²</td><td>'+r.height+' mm</td>'
       +'<td class="'+(r.usable?'good':'bad')+'">'+(r.usable?'OK':'bám bàn quá ít')+'</td></tr>';
    }
    h+='</table><div class="mut" style="margin-top:8px">Xếp hạng: ít support nhất → bám bàn nhiều nhất → thấp nhất. '
     +'Overhang thấp mà bám bàn ~0 là BẪY: model đứng trên cạnh dao, lớp đầu không bám.</div>';
    // Anh render de user NHIN thay xoay the nao — khong phai doan tu con so
    if(j.rot_preview&&j.rot_preview.current){
      const pv=j.rot_preview;
      const cm=pv.current_meta;
      const cmeta=cm?('support ~'+(cm.support_cm3||0)+'cm³ · overhang '+cm.overhang_pct+'% · bám '+cm.bed_cm2+'cm² · cao '+cm.height+'mm'):'';
      h+='<div style="display:flex;gap:18px;flex-wrap:wrap;margin-top:12px;align-items:flex-start">'
       +'<div style="text-align:center"><div class="mut" style="margin-bottom:4px">Hướng hiện tại'
       +(pv.current_is_best?' <span style="color:#22c55e">✓ tốt nhất</span>':'')+'</div>'+pv.current
       +(cmeta?'<div class="mut" style="font-size:11px;margin-top:2px">'+cmeta+'</div>':'')+'</div>';
      // 1-2 GOI Y MEM — user tu chon, khong ep. Vien xanh cho phuong an tot hon hien tai.
      const opts=pv.options||[];
      for(let i=0;i<opts.length;i++){ const o=opts[i];
        const better=cm&&((o.support_cm3||0)<(cm.support_cm3||0)-1);
        const saved=cm?Math.max(0,Math.round(((cm.support_cm3||0)-(o.support_cm3||0))*10)/10):0;
        h+='<div style="text-align:center"><div style="font-weight:700;margin-bottom:4px;color:'
         +(better?'#22c55e':'#93c5fd')+'">'+(better?'★ ':'')+'Gợi ý '+(i+1)+': xoay '+o.angle+'° trục '+o.axis
         +(saved>0?' — bớt ~'+saved+'cm³ support':'')+'</div>'
         +'<div style="border:2px solid '+(better?'rgba(34,197,94,.5)':'rgba(147,197,253,.35)')+';border-radius:10px;display:inline-block">'+o.svg+'</div>'
         +'<div class="mut" style="font-size:11px;margin-top:2px">support ~'+(o.support_cm3||0)+'cm³ · overhang '+o.overhang_pct+'% · bám '+o.bed_cm2+'cm² · cao '+o.height+'mm</div></div>';
      }
      h+='</div>';
      h+='<div class="mut" style="font-size:12px;margin-top:8px">'
       +(pv.current_is_best?'✓ Hướng hiện tại đang tốt nhất theo số liệu — 1-2 gợi ý trên chỉ để bạn CÂN NHẮC (vd cần mặt đẹp/chịu lực khác), không bắt buộc xoay. ':'Cân nhắc 1-2 gợi ý trên — chọn cái hợp mục đích (ít support / mặt đẹp / chịu lực). ')
       +'Trong Bambu Studio: chọn model → phím <b>R</b> → nhập góc quanh trục tương ứng.</div>';
    }
    h+='</div>';
  }

  if(j.flow){ const f=j.flow; const ov=Object.entries(f.over_ceiling||{});
    h+='<div class="card"><h3 style="margin-top:0">Trần lưu lượng</h3><table>'
     +'<tr><td>Nhựa chảy tối đa</td><td><b>'+f.mvs+' mm³/s</b></td></tr>'
     +'<tr><td>Layer height</td><td>'+f.layer_height+' mm</td></tr>'
     +'<tr><td>→ Tốc độ tối đa THẬT</td><td class="good"><b>'+f.v_max+' mm/s</b></td></tr></table>';
    if(ov.length){ h+='<table style="margin-top:8px"><tr><th>Đang đặt</th><th>Thực tế</th></tr>';
      for(const [k,v] of ov) h+='<tr><td>'+esc(k)+'</td><td class="bad">'+v+' mm/s → máy hãm còn '+f.v_max+'</td></tr>';
      h+='</table>'; }
    h+='</div>';
  }
  if(j.variable_layer){ const v=j.variable_layer;
    h+='<div class="card"><h3 style="margin-top:0">Variable Layer Height</h3><table>'
     +'<tr><td>Mỏng nhất / dày nhất</td><td>'+v.min+' / '+v.max+' mm</td></tr>'
     +'<tr><td>Trung bình</td><td>'+v.avg+' mm</td></tr>'
     +'<tr><td>Số lớp thực tế</td><td class="bad"><b>'+v.layers_actual+'</b></td></tr>'
     +'<tr><td>Nếu để phẳng</td><td class="good"><b>'+v.layers_flat+'</b></td></tr>'
     +'<tr><td>Cộng thêm</td><td class="bad"><b>+'+v.extra_layers+' lớp (+'+v.extra_pct+'%)</b></td></tr>'
     +'</table></div>';
  }
  if(j.config){ h+='<div class="card"><h3 style="margin-top:0">Cấu hình trong file</h3><table>';
    for(const [k,v] of Object.entries(j.config)) if(v!==null&&v!==undefined)
      h+='<tr><td class="mut">'+esc(k)+'</td><td>'+esc(Array.isArray(v)?v.join(", "):v)+'</td></tr>';
    h+='</table></div>';
  }
  if(j.export){ const e=j.export;
    h+='<div class="card"><h3 style="margin-top:0">Cấu hình tối ưu — sinh từ chính các vấn đề trên</h3>';
    for(const w of e.why) h+='<div class="tip">'+esc(w)+'</div>';
    if(e.guide&&e.guide.length){
      h+='<div style="margin-top:14px;border-top:1px solid rgba(255,255,255,.12);padding-top:12px">'
       +'<div style="font-weight:800;font-size:14px;margin-bottom:4px">📋 Chỉnh ở đâu trong Bambu Studio — đọc trước khi xuất</div>'
       +'<div class="mut" style="font-size:12px;margin-bottom:10px">Bật <b>Advanced</b> (góc trên phần Process) mới thấy đủ ô. Mỗi dòng = 1 ô trong Studio: <b>Tab › mục › tên tiếng Anh = giá trị</b>.</div>';
      const tabvi={Quality:"Quality (Chất lượng)",Strength:"Strength (Độ bền)",Speed:"Speed (Tốc độ)",Support:"Support (Đỡ)",Others:"Others (Khác)"};
      for(const g of e.guide){
        h+='<div style="margin:8px 0 4px;font-weight:700;color:#38bdf8">'+esc(tabvi[g.tab]||g.tab)+'</div>'
         +'<table style="width:100%;font-size:13px"><tr><th style="text-align:left">Mục</th><th style="text-align:left">Thông số (EN)</th><th style="text-align:right">Giá trị</th><th style="text-align:left">Vì sao (theo số liệu model)</th></tr>';
        for(const it of g.items)
          h+='<tr><td class="mut" style="vertical-align:top">'+esc(it.section)+'</td><td style="vertical-align:top">'+esc(it.en)+'</td><td style="text-align:right;vertical-align:top"><b>'+esc(it.value)+'</b></td><td class="mut" style="font-size:12px;line-height:1.5">'+esc(it.why||'')+'</td></tr>';
        h+='</table>';
      }
      h+='</div>';
    }
    h+='<div style="margin-top:10px;display:flex;gap:8px;flex-wrap:wrap;align-items:center">'
     +'<label class="mut" style="font-size:13px">Tên preset:</label>'
     +'<code style="font-size:12px;color:#93c5fd" id="pnamePrefix">'+esc(e.preset&&e.preset.name||"LP-PLA")+'</code>'
     +'<input id="pnameExtra" placeholder="thêm tên model/ghi chú (tùy chọn)" oninput="pnamePreview()" '
     +'style="flex:1;min-width:160px;padding:7px;border-radius:8px;border:1px solid #334;background:#0f1523;color:#e8ecf4;font-size:13px">'
     +'</div>'
     +'<div class="mut" id="pnameFull" style="font-size:12px;margin:5px 0 8px"></div>'
     +'<button class="btn" style="margin-top:4px" onclick="dl()">Tải preset .json (import vào Bambu Studio)</button>'
     +'<div class="mut" style="margin-top:9px;line-height:1.6">✅ <b>Checklist sau khi import</b> (File ▸ Import ▸ Import Configs):<br>'
     +'1️⃣ <b>CHỌN preset ở dropdown Process</b> — import xong Studio KHÔNG tự áp, đây là lỗi số 1.<br>'
     +'2️⃣ Có dùng support: tab Support bật <b>Advanced</b> → kiểm Support/raft interface = đúng khay, Top Z distance đúng như dòng giải thích ở trên.<br>'
     +'3️⃣ Bấm in: map khay AMS đúng nhựa/màu như file khai báo.<br>'
     +'4️⃣ Slice → Preview: kéo thanh lớp, nhìn lớp interface đổi màu ngay dưới mặt hẫng là chuẩn.</div></div>';
    window.__preset=e.preset; window.__pname=(j.name||"file").replace(/\.[^.]+$/,"");
    pnamePreview();
  }
// Chen text user go vao ten preset NGAY TRUOC che do (Fast/Balanced/HighQuality):
// LP-PLA-Lite-Balanced-0.2mm + "vase" -> LP-PLA-Lite-vase-Balanced-0.2mm
function pnameWith(base,extra){
  extra=(extra||"").trim().replace(/[^A-Za-z0-9_-]+/g,"-").replace(/^-+|-+$/g,"").slice(0,24);
  if(!extra) return base;
  const m=base.match(/^(LP-.+?)-(Fast|Balanced|HighQuality)-(.+)$/);
  return m ? m[1]+"-"+extra+"-"+m[2]+"-"+m[3] : base+"-"+extra;
}
function pnamePreview(){
  const p=window.__preset; if(!p) return;
  const ex=(document.getElementById("pnameExtra")||{}).value||"";
  const full=pnameWith(p.name||"LP-PLA-preset",ex);
  const el=document.getElementById("pnameFull"); if(el) el.innerHTML="→ Tên khi xuất: <b style=\"color:#22c55e\">"+esc(full)+"</b>";
}
  h+='<button class="btn go" id="e2e" onclick="optimize()">So sánh 3 chế độ — slice thật 4 lần (~15s)</button>'
   +'<div id="e2eout"></div>'
   +'<div class="card" style="margin-top:10px"><h3 style="margin-top:0">Slice + đẩy xuống máy in</h3>'
   +'<select id="smode" style="width:100%;padding:10px;border-radius:10px;margin-bottom:9px;'
   +'background:#0f172a;color:#e2e8f0;border:1px solid rgba(255,255,255,.15);font-size:14px">'
   +'<option value="balanced" selected>Cân bằng — 0.20mm (khuyên dùng)</option>'
   +'<option value="fast">Nhanh — 0.28mm</option>'
   +'<option value="quality">Đẹp — 0.16mm</option>'
   +'<option value="">Giữ nguyên config trong file (không áp preset)</option>'
   +'</select>'
   +'<div style="display:flex;gap:8px;flex-wrap:wrap">'
   +'<button class="btn go" style="margin-top:0;flex:1;min-width:180px" onclick="slice(false)">Slice + đẩy xuống máy in</button>'
   +'<button class="btn" style="margin-top:0;flex:1;min-width:180px;background:linear-gradient(160deg,#a78bfa,#7c3aed)" onclick="slice(true)">Slice để TẢI VỀ (.gcode.3mf)</button>'
   +'</div>'
   +'<div id="dlbox" style="margin-top:8px"></div>'
   +'<div class="mut" style="margin-top:7px;line-height:1.6">Cả hai dùng cấu hình máy A1 thật + khay AMS. <b>File .gcode.3mf đã slice sẵn (chứa G-code)</b>:<br>'
   +'• <b>In thẳng KHÔNG slice lại</b>: mở bằng <b>Bambu Handy</b> (điện thoại) hoặc copy vào thẻ SD/gửi LAN — máy chạy G-code có sẵn.<br>'
   +'• Mở trong <b>Bambu Studio (desktop)</b>: Studio nạp lại thành project để CHỈNH SỬA nên nút "Slice plate" sáng lại — đây là bản chất của Studio (không dùng G-code ngoài làm bản in cuối). Cấu hình đã nhúng nên bấm Slice lại ra <b>y hệt</b>, chỉ mất thời gian slice. Muốn khỏi slice lại thì in qua Handy/thẻ SD.</div></div>';
  document.getElementById("out").innerHTML=h;
}
function optimize(){
  if(!FILE){ toast("Chọn lại file"); return; }
  const b=document.getElementById("e2e"); b.disabled=true; b.textContent="Đang slice baseline + 3 chế độ…";
  const xhr=new XMLHttpRequest();
  xhr.open("POST","/api/optimize?name="+encodeURIComponent(FILE.name));
  xhr.onload=()=>{ let j={}; try{j=JSON.parse(xhr.responseText);}catch(e){}
    if(j.ok&&j.queued) pollOpt(); else { b.disabled=false; toast("Lỗi: "+(j.msg||xhr.status)); } };
  xhr.onerror=()=>{ b.disabled=false; toast("Mất kết nối"); };
  xhr.send(FILE);
}
async function pollOpt(){
  const b=document.getElementById("e2e");
  try{
    const j=await (await fetch("/api/optstatus",{cache:"no-store"})).json();
    if(j.state==="running"){ b.textContent=j.msg||"Đang xử lý…"; setTimeout(pollOpt,2500); return; }
    b.disabled=false; b.textContent="So sánh lại 3 chế độ";
    if(j.state==="error"){ toast("Lỗi: "+j.msg); return; }
    if(j.state==="done"&&j.report) renderE2E(j.report);
  }catch(e){ setTimeout(pollOpt,4000); }
}
function renderE2E(r){
  const b=r.baseline||{}; const MS=["fast","balanced","quality"];
  let h='<div class="card"><h3 style="margin-top:0">So sánh — mỗi dòng là 1 lần slice THẬT</h3>'
    +'<table><tr><th>Chế độ</th><th>Thời gian</th><th>Nhựa</th><th>Lớp</th></tr>'
    +'<tr style="background:rgba(255,255,255,.04)"><td><b>Mặc định</b><br><span class="mut">AUTO-balanced 0.20</span></td>'
    +'<td>'+esc(b.time||"?")+'</td><td>'+(b.weight_g||"?")+' g</td><td>'+(b.layers||"?")+'</td></tr>';
  for(const k of MS){
    const d=(r.modes||{})[k]; if(!d||d.error) continue;
    const tp=d.time_pct, cls=tp>2?"good":(tp<-2?"bad":"mut");
    h+='<tr><td><b>'+esc(d.label)+'</b></td><td class="'+cls+'">'+esc(d.time)
      +'<br><span class="mut">'+(tp>0?"−"+tp:"+"+(-tp))+'%</span></td>'
      +'<td>'+d.weight_g+' g</td><td>'+d.layers+'</td></tr>';
  }
  h+='</table></div>';
  for(const k of MS){
    const d=(r.modes||{})[k]; if(!d||d.error) continue;
    h+='<div class="card"><h3 style="margin-top:0">'+esc(d.label)+' — vì sao</h3>';
    for(const w of d.why) h+='<div class="tip">'+esc(w)+'</div>';
    h+='<button class="btn" style="margin-top:9px" onclick="dlp(\''+k+'\')">Tải preset '+esc(d.label)+' (.json)</button></div>';
  }
  window.__rep=r;
  document.getElementById("e2eout").innerHTML=h;
}
function dlp(k){
  const d=window.__rep.modes[k];
  const blob=new Blob([JSON.stringify(d.preset,null,4)],{type:"application/json"});
  const a=document.createElement("a"); a.href=URL.createObjectURL(blob);
  a.download=((d.preset&&d.preset.name)||((window.__rep.name||"file")+"-"+k))+".json";
  a.click(); URL.revokeObjectURL(a.href);
  toast("Đã tải — Import xong nhớ CHỌN preset ở dropdown Process (không tự áp)");
}
function kv(k,v){ return '<div class="kv"><span>'+k+'</span><b>'+esc(v)+'</b></div>'; }
function dl(){
  const p=Object.assign({},window.__preset);           // copy, khong sua ban goc
  const ex=(document.getElementById("pnameExtra")||{}).value||"";
  const full=pnameWith(p.name||(window.__pname+"-OPT-process"),ex);
  p.name=full; p.print_settings_id=full;                // ten trong Bambu = ten user go
  const blob=new Blob([JSON.stringify(p,null,4)],{type:"application/json"});
  const a=document.createElement("a");
  a.href=URL.createObjectURL(blob);
  a.download=full+".json";
  a.click(); URL.revokeObjectURL(a.href);
  toast("Đã tải: "+full+" — Import xong nhớ CHỌN preset ở dropdown Process");
}
async function slice(download){
  if(!FILE){ toast("Chọn lại file"); return; }
  const m=(document.getElementById("smode")||{value:""}).value;
  const db=document.getElementById("dlbox"); if(db) db.innerHTML="";
  const xhr=new XMLHttpRequest();
  xhr.open("POST","/api/upload?name="+encodeURIComponent(FILE.name)+(m?"&mode="+m:"")+(download?"&download=1":""));
  xhr.onload=()=>{ let j={}; try{j=JSON.parse(xhr.responseText);}catch(e){}
    if(j.ok&&j.queued){ toast(download?"Đang slice để tải về…":"Đang slice trên máy tính…"); poll(); }
    else if(j.ok){ toast("Đã đẩy xuống máy: "+j.name); }
    else toast("Lỗi: "+(j.msg||xhr.status)); };
  xhr.onerror=()=>toast("Mất kết nối");
  toast("Đang gửi file…"); xhr.send(FILE);
}
async function poll(){
  try{ const j=await (await fetch("/api/upstatus",{cache:"no-store"})).json();
    if(j.state==="slicing"||j.state==="pushing"){ toast(j.msg||"Đang xử lý…"); setTimeout(poll,3000); return; }
    if(j.state==="done"){ const s=j.stats||{}; toast("✔ "+j.msg);
      const db=document.getElementById("dlbox");
      if(j.download&&db){ db.innerHTML='<a class="btn" style="display:block;text-align:center;text-decoration:none;background:linear-gradient(160deg,#22c55e,#16a34a)" href="/api/sliced-download">⬇ Tải '+j.download+' — mở Bambu Studio/Handy để in</a>'; }
    }
    else if(j.state==="error") toast("Lỗi: "+j.msg);
  }catch(e){ setTimeout(poll,4000); }
}
</script></body></html>"""


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _qs_path(self):
        """Lay tham so ?path= da giai ma."""
        from urllib.parse import urlparse, parse_qs, unquote
        return unquote(parse_qs(urlparse(self.path).query).get("path", [""])[0])

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
                # Mau nhua THUC SU dung trong ban in nay (tu slice_info: color + used_g)
                info = JOB.get("info") or {}
                payload["job_filaments"] = (info.get("slice") or {}).get("filaments") or []
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
        elif path.startswith("/api/files"):
            self._send(200, json.dumps({"files": get_files(), "busy": is_busy()}), "application/json; charset=utf-8")
        elif path.startswith("/api/filethumb"):
            fpath = self._qs_path()
            if not fpath:
                self._send(400, "no path", "text/plain")
                return
            thumb, _ = ensure_file_meta(fpath)
            if thumb:
                self._send(200, thumb, "image/png")
            else:
                self._send(404, "no thumb", "text/plain")
        elif path.startswith("/api/printer-config"):
            with LOCK:
                conn = STATE.get("connected", False)
            self._send(200, json.dumps({
                "host": IP,
                "serial_set": bool(SERIAL),      # chi bao CO/CHUA — khong lo ky tu that
                "code_set": bool(CODE),
                "connected": conn,
            }), "application/json; charset=utf-8")
        elif path.startswith("/api/anstatus"):
            with ANJOB_LOCK:
                self._send(200, json.dumps(ANJOB, ensure_ascii=False),
                           "application/json; charset=utf-8")
        elif path.startswith("/api/optstatus"):
            with OPTJOB_LOCK:
                self._send(200, json.dumps(OPTJOB, ensure_ascii=False),
                           "application/json; charset=utf-8")
        elif path.startswith("/api/upstatus"):
            with UPJOB_LOCK:
                self._send(200, json.dumps(UPJOB), "application/json; charset=utf-8")
        elif path.startswith("/api/sliced-download"):
            with UPJOB_LOCK:
                fp, fn = LAST_SLICED.get("path"), LAST_SLICED.get("name")
            if not fp or not os.path.isfile(fp):
                self._send(404, json.dumps({"ok": False, "msg": "Chưa có file slice để tải"}),
                           "application/json; charset=utf-8")
                return
            with open(fp, "rb") as f:
                blob = f.read()
            self.send_response(200)
            self.send_header("Content-Type", "application/octet-stream")
            self.send_header("Content-Disposition",
                             f'attachment; filename="{os.path.basename(fn or "sliced.gcode.3mf")}"')
            self.send_header("Content-Length", str(len(blob)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(blob)
        elif path.startswith("/api/filemeta"):
            fpath = self._qs_path()
            if not fpath:
                self._send(400, json.dumps({"ok": False}), "application/json")
                return
            # NHANH: doc 96KB cuoi file qua FTP REST (muc luc zip) thay vi tai ca file
            # 30MB. Cache .json de lan sau tuc thi. Thumb van tai day du o /api/filethumb.
            key = _cache_key(os.path.basename(fpath))
            meta = os.path.join(CACHE_DIR, key + ".json")
            sliced = None
            if os.path.isfile(meta):
                try:
                    with open(meta, encoding="utf-8") as f:
                        sliced = json.load(f).get("sliced")
                except (OSError, ValueError):
                    pass
            if sliced is None:
                sliced = filament_ftp.probe_sliced(IP, CODE, fpath)
                if sliced is not None:
                    try:
                        os.makedirs(CACHE_DIR, exist_ok=True)
                        with open(meta, "w", encoding="utf-8") as f:
                            json.dump({"sliced": bool(sliced)}, f)
                    except OSError:
                        pass
                else:
                    # May Bambu KHONG ho tro FTP REST (502) -> probe nhanh bat luc.
                    # Roi ve tai DAY DU (cham lan dau, ensure_file_meta tu cache .json+.png)
                    _, sliced = ensure_file_meta(fpath)
            if sliced is None:
                self._send(200, json.dumps({"ok": False, "sliced": False}),
                           "application/json; charset=utf-8")
            else:
                self._send(200, json.dumps({"ok": True, "sliced": bool(sliced)}),
                           "application/json; charset=utf-8")
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
        elif path == "/files":
            self._send(200, FILES_PAGE, "text/html; charset=utf-8")
        elif path == "/analyze":
            self._send(200, ANALYZE_PAGE, "text/html; charset=utf-8")
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

    MAX_UPLOAD = 300 * 1024 * 1024      # 300 MB — .gcode.3mf that hiem khi qua 100

    def _do_upload(self):
        """Nhan raw bytes tu trinh duyet -> STOR len the SD cua may qua FTPS.

        Nguoi dung bam nut tren web moi chay. Chot chan: chi .3mf, cat ve
        basename (chan path traversal), gioi han dung luong.
        """
        from urllib.parse import urlparse, parse_qs, unquote
        raw = unquote(parse_qs(urlparse(self.path).query).get("name", [""])[0])
        name = os.path.basename(raw.replace("\\", "/")).strip()
        if not name or name in (".", ".."):
            self._send(400, json.dumps({"ok": False, "msg": "Thiếu tên file"}),
                       "application/json; charset=utf-8")
            return
        if not name.lower().endswith((".3mf", ".stl")):
            self._send(400, json.dumps({"ok": False, "msg": "Chỉ nhận file .3mf hoặc .stl"}),
                       "application/json; charset=utf-8")
            return
        try:
            n = int(self.headers.get("Content-Length", 0))
        except ValueError:
            n = 0
        if n <= 0:
            self._send(400, json.dumps({"ok": False, "msg": "File rỗng"}),
                       "application/json; charset=utf-8")
            return
        if n > self.MAX_UPLOAD:
            self._send(413, json.dumps({"ok": False, "msg": "File quá lớn (>300 MB)"}),
                       "application/json; charset=utf-8")
            return
        try:
            data = self.rfile.read(n)
        except OSError as e:
            self._send(400, json.dumps({"ok": False, "msg": f"Đọc file lỗi: {e}"}),
                       "application/json; charset=utf-8")
            return

        # Phan luong: file DA slice -> chuyen thang xuong may in nhu truoc.
        # File CHUA slice (du an tho) -> slice bang Bambu Studio CLI truoc (chay nen).
        os.makedirs(SLICE_DIR, exist_ok=True)
        src = os.path.join(SLICE_DIR, "in_" + name)
        try:
            with open(src, "wb") as f:
                f.write(data)
        except OSError as e:
            self._send(500, json.dumps({"ok": False, "msg": f"Ghi file tạm lỗi: {e}"}),
                       "application/json; charset=utf-8")
            return

        if filament_ftp.parse_is_sliced(src):
            try:
                os.remove(src)
            except OSError:
                pass
            with THUMB_LOCK:            # dung chung khoa FTP: khong tai/day song song
                ok, msg = filament_ftp.upload_file(IP, CODE, data, name)
            if ok:
                FILES_CACHE["ts"] = 0   # ep lam moi danh sach file
                self._send(200, json.dumps({"ok": True, "path": msg, "name": name,
                                            "sliced": True}),
                           "application/json; charset=utf-8")
            else:
                self._send(502, json.dumps({"ok": False, "msg": f"FTP lỗi: {msg}"}),
                           "application/json; charset=utf-8")
            return

        # Chua slice -> can CLI + chi 1 job mot luc
        if not slicer_cli.find_exe():
            self._send(501, json.dumps({"ok": False, "msg":
                "File CHƯA slice và máy chủ không có Bambu Studio — hãy slice rồi upload lại"}),
                "application/json; charset=utf-8")
            return
        with UPJOB_LOCK:
            if UPJOB["state"] in ("slicing", "pushing"):
                self._send(409, json.dumps({"ok": False, "msg":
                    f"Đang slice file khác ({UPJOB['name']}) — chờ xong đã"}),
                    "application/json; charset=utf-8")
                return
            UPJOB.update(state="slicing", name=name, msg="Bắt đầu slice…", stats=None)
        q = parse_qs(urlparse(self.path).query)
        mode = unquote(q.get("mode", [""])[0]).strip().lower()
        if mode not in ("fast", "balanced", "quality"):
            mode = None
        # download=1 -> CHI slice de tai ve (khong day xuong may)
        push = q.get("download", ["0"])[0] not in ("1", "true", "yes")
        threading.Thread(target=_slice_and_push, args=(name, src, mode, push), daemon=True).start()
        self._send(200, json.dumps({"ok": True, "queued": True, "name": name}),
                   "application/json; charset=utf-8")

    def _do_analyze(self):
        """Nhan file -> tra ve NGAY (queued) -> thread nen phan tich -> UI poll."""
        from urllib.parse import urlparse, parse_qs, unquote
        raw = unquote(parse_qs(urlparse(self.path).query).get("name", [""])[0])
        name = os.path.basename(raw.replace("\\", "/")).strip()
        if not name.lower().endswith((".3mf", ".stl")):
            self._send(400, json.dumps({"ok": False, "msg": "Chỉ phân tích .3mf hoặc .stl"}),
                       "application/json; charset=utf-8")
            return
        try:
            n = int(self.headers.get("Content-Length", 0))
        except ValueError:
            n = 0
        if n <= 0 or n > self.MAX_UPLOAD:
            self._send(400, json.dumps({"ok": False, "msg": "File rỗng hoặc quá lớn"}),
                       "application/json; charset=utf-8")
            return
        with ANJOB_LOCK:
            if ANJOB["state"] == "running":
                self._send(409, json.dumps({"ok": False, "msg":
                    f"Đang phân tích file khác ({ANJOB['name']}) — chờ chút"}),
                    "application/json; charset=utf-8")
                return
            ANJOB.update(state="running", name=name,
                         msg="Đang đọc mesh + tính toán…", result=None)
        os.makedirs(SLICE_DIR, exist_ok=True)
        tmp = os.path.join(SLICE_DIR, "an_" + name)
        try:
            with open(tmp, "wb") as f:
                f.write(self.rfile.read(n))
        except OSError as e:
            with ANJOB_LOCK:
                ANJOB.update(state="error", msg=str(e))
            self._send(500, json.dumps({"ok": False, "msg": f"Ghi file lỗi: {e}"}),
                       "application/json; charset=utf-8")
            return
        threading.Thread(target=_run_analyze, args=(name, tmp), daemon=True).start()
        self._send(200, json.dumps({"ok": True, "queued": True}),
                   "application/json; charset=utf-8")

    def _do_optimize(self):
        from urllib.parse import urlparse, parse_qs, unquote
        raw = unquote(parse_qs(urlparse(self.path).query).get("name", [""])[0])
        name = os.path.basename(raw.replace("\\", "/")).strip()
        if not name.lower().endswith((".3mf", ".stl")):
            self._send(400, json.dumps({"ok": False, "msg": "Chỉ nhận .3mf / .stl"}),
                       "application/json; charset=utf-8"); return
        with OPTJOB_LOCK:
            if OPTJOB["state"] == "running":
                self._send(409, json.dumps({"ok": False, "msg": "Đang tối ưu file khác"}),
                           "application/json; charset=utf-8"); return
            OPTJOB.update(state="running", name=name, msg="Bắt đầu…", report=None)
        try:
            n = int(self.headers.get("Content-Length", 0))
        except ValueError:
            n = 0
        os.makedirs(SLICE_DIR, exist_ok=True)
        tmp = os.path.join(SLICE_DIR, "opt_" + name)
        with open(tmp, "wb") as f:
            f.write(self.rfile.read(n))
        threading.Thread(target=_run_optimize, args=(name, tmp), daemon=True).start()
        self._send(200, json.dumps({"ok": True, "queued": True}),
                   "application/json; charset=utf-8")

    def _same_origin(self) -> bool:
        """Chan CSRF: trinh duyet LUON gui Origin voi cross-site POST fetch —
        khac Host la request tu trang web la, tu choi. curl/script noi bo khong
        gui Origin -> cho qua (khong phai vector CSRF)."""
        raw = self.headers.get("Origin") or self.headers.get("Referer") or ""
        if not raw:
            return True
        from urllib.parse import urlparse
        return urlparse(raw).netloc == (self.headers.get("Host") or "")

    def do_POST(self):
        if not self._same_origin():
            self._send(403, json.dumps({"ok": False, "msg": "Origin không khớp — chặn CSRF"}),
                       "application/json; charset=utf-8")
            return
        if self.path.startswith("/api/optimize"):
            self._do_optimize(); return
        if self.path.startswith("/api/analyze"):
            self._do_analyze()
            return
        if self.path == "/api/cmd/pause":
            ok, msg = cmd_print("pause")
        elif self.path == "/api/cmd/resume":
            ok, msg = cmd_print("resume")
        elif self.path == "/api/cmd/stop":
            ok, msg = cmd_print("stop")
        elif self.path == "/api/print":
            body = self._read_json()
            name = (body.get("name") or "").strip()
            fpath = (body.get("path") or "").strip()
            if not name:
                self._send(400, json.dumps({"ok": False, "msg": "thieu ten file"}), "application/json")
                return
            if is_busy():
                self._send(409, json.dumps({"ok": False, "msg": "Máy đang bận (đang in) — không thể in file mới"}), "application/json; charset=utf-8")
                return
            ok, msg = cmd_project_file(name, fpath)
            self._send(200, json.dumps({"ok": ok, "msg": msg}), "application/json; charset=utf-8")
            return
        elif self.path.startswith("/api/upload"):
            self._do_upload()
            return
        elif self.path == "/api/printer-config":
            body = self._read_json()
            host = (body.get("host") or "").strip() or IP
            serial = (body.get("serial") or "").strip() or SERIAL
            code = (body.get("code") or "").strip()
            # Doi HOST bat buoc nhap lai access code — chan viec lai hub tro sang server
            # la roi tu dong dem code cu theo (phat hien boi code-review CSRF).
            if host != IP and not code:
                self._send(400, json.dumps({"ok": False, "msg": "Đổi IP thì phải nhập lại Access Code (chống trỏ nhầm/tấn công)"}), "application/json; charset=utf-8")
                return
            code = code or CODE
            if re.fullmatch(r"[\d.]+", host or ""):
                import ipaddress
                try:
                    ipaddress.ip_address(host)
                except ValueError:
                    self._send(400, json.dumps({"ok": False, "msg": "IP không hợp lệ (octet 0-255)"}), "application/json; charset=utf-8")
                    return
            elif not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9.-]{0,63}", host or ""):
                self._send(400, json.dumps({"ok": False, "msg": "IP/host không hợp lệ"}), "application/json; charset=utf-8")
                return
            if not re.fullmatch(r"[A-Za-z0-9]{8}", code or ""):
                self._send(400, json.dumps({"ok": False, "msg": "Access code phải đúng 8 ký tự chữ/số (xem màn hình máy in: Cài đặt → WLAN)"}), "application/json; charset=utf-8")
                return
            if not re.fullmatch(r"[A-Za-z0-9]{10,20}", serial or ""):
                self._send(400, json.dumps({"ok": False, "msg": "Serial không hợp lệ (10-20 ký tự chữ/số)"}), "application/json; charset=utf-8")
                return
            try:
                update_printer_config(host, serial, code)
            except Exception as e:                       # noqa: BLE001 — ghi file loi (quyen/dia)
                self._send(500, json.dumps({"ok": False, "msg": f"Lưu cấu hình lỗi: {e}"}), "application/json; charset=utf-8")
                return
            self._send(200, json.dumps({"ok": True, "msg": "Đã lưu vào .env — đang kết nối lại máy in..."}), "application/json; charset=utf-8")
            return
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
