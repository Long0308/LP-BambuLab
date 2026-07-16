#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Bot Telegram 2 CHIEU v2 — nut nhanh + AI vision + DIEU KHIEN may in.

Ban phim thuong truc:
  📊 Tình hình in      → bao cao HTML dep (thanh tien do, lop, gio, GAM NHUA)
  📷 Ảnh bàn in        → chup camera A1 gui vao chat
  🔍 Phân tích bản in  → AI VISION nhin anh camera + anh render model -> danh gia
  🌡️ Nhiệt & khay      → nozzle/bed + 4 khe AMS
  💡 Mẹo in            → AI meo theo nhua/model dang in
  🧯 Hỏi lỗi           → ma loi hien tai + AI giai thich
  ⏸ Tạm dừng / ▶️ Tiếp tục → lenh truc tiep
  ⏹ DỪNG HẲN           → 2 BUOC: bot hoi lai, phai go 'DUNG XAC NHAN' trong 60s
  Go cau hoi bat ky    → AI; cau hoi nhac anh/nhin/san pham -> tu dinh kem anh (vision)

BAO MAT: chi tra loi TELEGRAM_CHAT_ID trong .env — nguoi la im lang tuyet doi.
hooks tiem tu bambu_web (khong import vong): status_html/status/temps/frame/thumb/
cmd(pause|resume|stop)/err.
"""
from __future__ import annotations

import json
import threading
import time
import urllib.request
import uuid

import ai_chat
import notify

B_STATUS, B_PHOTO = "📊 Tình hình in", "📷 Ảnh bàn in"
B_ANALYZE, B_TEMP = "🔍 Phân tích bản in", "🌡️ Nhiệt & khay"
B_TIP, B_ERR = "💡 Mẹo in", "🧯 Hỏi lỗi"
B_PAUSE, B_RESUME, B_STOP = "⏸ Tạm dừng", "▶️ Tiếp tục", "⏹ DỪNG HẲN"
STOP_WORD = "DUNG XAC NHAN"

_KEYBOARD = {"keyboard": [
    [{"text": B_STATUS}, {"text": B_PHOTO}],
    [{"text": B_ANALYZE}, {"text": B_TEMP}],
    [{"text": B_TIP}, {"text": B_ERR}],
    [{"text": B_PAUSE}, {"text": B_RESUME}, {"text": B_STOP}],
], "resize_keyboard": True, "is_persistent": True}

# tu khoa -> cau hoi tu do se duoc dinh kem ANH (camera + render model) cho AI vision
_VISION_WORDS = ("ảnh", "anh ban in", "hình", "hinh", "nhìn", "nhin", "camera",
                 "sản phẩm", "san pham", "spaghetti", "hỏng", "hong", "bong",
                 "lệch", "lech", "xơ", "xo", "bề mặt", "be mat")

_PEND = {"stop_until": 0.0}


def _cfg() -> tuple[str | None, str | None]:
    e = notify._env()                                    # noqa: SLF001 — cung nguon .env
    return e.get("TELEGRAM_BOT_TOKEN"), e.get("TELEGRAM_CHAT_ID")


def _api(token: str, method: str, payload: dict, timeout: int = 65) -> dict:
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/{method}",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8", "ignore"))


def _send(token: str, chat: str, text: str, html: bool = True) -> None:
    p = {"chat_id": chat, "text": text, "reply_markup": _KEYBOARD}
    if html:
        p["parse_mode"] = "HTML"
    try:
        _api(token, "sendMessage", p, timeout=20)
    except Exception:                                    # noqa: BLE001
        if html:                                         # HTML loi (ky tu la) -> gui tho
            _send(token, chat, text, html=False)


def _send_photo(token: str, chat: str, jpg: bytes, caption: str = "") -> None:
    b = uuid.uuid4().hex
    body = (f"--{b}\r\nContent-Disposition: form-data; name=\"chat_id\"\r\n\r\n{chat}\r\n"
            f"--{b}\r\nContent-Disposition: form-data; name=\"caption\"\r\n\r\n{caption}\r\n"
            f"--{b}\r\nContent-Disposition: form-data; name=\"photo\"; "
            f"filename=\"cam.jpg\"\r\nContent-Type: image/jpeg\r\n\r\n").encode("utf-8")
    body += jpg + f"\r\n--{b}--\r\n".encode("utf-8")
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/sendPhoto", data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={b}"}, method="POST")
    urllib.request.urlopen(req, timeout=30).read()


def _images(hooks: dict) -> list[bytes]:
    """Anh cho AI vision: [camera that, render model] — cai nao co thi lay."""
    out = []
    cam = hooks["frame"]()
    if cam:
        out.append(cam)
    th = (hooks.get("thumb") or (lambda: None))()
    if th:
        out.append(th)
    return out


def _handle(token: str, chat: str, text: str, hooks: dict) -> None:  # noqa: PLR0912
    t = (text or "").strip()
    tl = t.lower()
    if t in ("/start", "/help"):
        _send(token, chat, "🖨 <b>Bot máy in A1</b> — bấm nút bên dưới, hoặc gõ câu hỏi "
                           "bất kỳ (AI trả lời; câu hỏi nhắc tới ảnh/sản phẩm sẽ tự kèm "
                           "ảnh camera cho AI nhìn).")
    elif t in (B_STATUS, "/status"):
        _send(token, chat, hooks["status_html"]())
    elif t == B_TEMP:
        _send(token, chat, hooks["temps"]())
    elif t in (B_PHOTO, "/photo"):
        jpg = hooks["frame"]()
        if jpg:
            _send_photo(token, chat, jpg, caption=hooks["status"]())
        else:
            _send(token, chat, "Camera chưa có hình (máy tắt / đang kết nối) — thử lại.")
    elif t == B_ANALYZE:
        _send(token, chat, "🔍 Đang chụp camera + phân tích bằng AI vision…", html=False)
        imgs = _images(hooks)
        if not imgs:
            _send(token, chat, "Không lấy được ảnh camera — máy tắt?")
            return
        a = ai_chat.ask_vision(
            "Ảnh 1 là camera bàn in THẬT (nếu có ảnh 2 thì đó là render model chuẩn để "
            "đối chiếu hình dạng). Kiểm tra bản in: có spaghetti/bong lớp/lệch trục/xơ "
            "nhựa/cong vênh không? Nhận xét ngắn gọn từng ý, chốt 1 dòng: ✅ ỔN / "
            "⚠️ NGHI NGỜ / ❌ HỎNG.", imgs, context=hooks["status"]()) \
            or "AI vision không phản hồi (hết lượt free hôm nay?) — xem ảnh bằng nút 📷."
        _send(token, chat, a, html=False)
    elif t == B_TIP:
        a = ai_chat.ask("Cho 3 mẹo NGẮN, cụ thể, đúng với nhựa và bản in đang chạy "
                        "(theo bối cảnh). Mỗi mẹo 1 dòng bắt đầu bằng 💡.",
                        context=hooks["status"]() + "\n" + hooks["temps"]()) \
            or "AI không phản hồi — thử lại sau."
        _send(token, chat, a, html=False)
    elif t == B_ERR:
        err = (hooks.get("err") or (lambda: 0))()
        if not err:
            _send(token, chat, "✅ Máy KHÔNG báo mã lỗi nào. Nếu thấy in xấu, bấm "
                               "🔍 Phân tích bản in để AI soi ảnh camera.")
        else:
            a = ai_chat.ask(f"Máy Bambu A1 đang báo mã lỗi {err} (hex {err:X}). Giải thích "
                            f"ngắn khả năng nguyên nhân + cách xử lý theo mã HMS Bambu.",
                            context=hooks["status"]()) or ""
            _send(token, chat, f"🚨 Mã lỗi <b>{err}</b> (hex {err:X})\n{a}\n"
                               f"Tra chính thức: wiki.bambulab.com · {notify.hub_url()}")
    elif t == B_PAUSE:
        ok, msg = hooks["cmd"]("pause")
        _send(token, chat, "⏸ Đã gửi lệnh TẠM DỪNG." if ok else f"Lỗi: {msg}")
    elif t == B_RESUME:
        ok, msg = hooks["cmd"]("resume")
        _send(token, chat, "▶️ Đã gửi lệnh TIẾP TỤC." if ok else f"Lỗi: {msg}")
    elif t == B_STOP:
        _PEND["stop_until"] = time.time() + 60
        _send(token, chat, f"⚠️ DỪNG HẲN sẽ HỦY bản in, không tiếp tục lại được.\n"
                           f"Chắc chắn thì gõ đúng: <b>{STOP_WORD}</b> (trong 60 giây).")
    elif tl.replace("ừ", "u").replace("ậ", "a").replace("dừng", "dung").upper().replace("Đ", "D") == STOP_WORD \
            or t.upper() == STOP_WORD:
        if time.time() <= _PEND["stop_until"]:
            _PEND["stop_until"] = 0
            ok, msg = hooks["cmd"]("stop")
            _send(token, chat, "⏹ Đã gửi lệnh DỪNG HẲN." if ok else f"Lỗi: {msg}")
        else:
            _send(token, chat, "Hết hạn xác nhận — bấm ⏹ DỪNG HẲN lại nếu vẫn muốn dừng.")
    elif t.startswith("/"):
        # lenh go sai (vd /strart) — nhac lenh dung, khong dot luot AI vo ich
        _send(token, chat, "Lệnh không có. Dùng: /start · /status · /photo · /help "
                           "— hoặc bấm nút bên dưới.")
    else:
        # cau hoi tu do — nhac toi anh/nhin/san pham thi kem ANH cho AI vision
        if any(w in tl for w in _VISION_WORDS):
            imgs = _images(hooks)
            if imgs:
                a = ai_chat.ask_vision(
                    t + "\n(Ảnh 1 = camera bàn in thật; ảnh 2 nếu có = render model.)",
                    imgs, context=hooks["status"]()) \
                    or "AI vision không phản hồi — thử lại sau."
                _send(token, chat, a, html=False)
                return
        a = ai_chat.ask(t, context=hooks["status"]() + "\n" + hooks["temps"]()) \
            or "AI không phản hồi (model free có thể hết lượt hôm nay) — thử lại sau."
        _send(token, chat, a, html=False)


def _register_commands(token: str) -> None:
    """Dang ky menu lenh '/' cua Telegram (hien goi y khi go /) — tu lanh moi lan chay."""
    try:
        _api(token, "setMyCommands", {"commands": [
            {"command": "start", "description": "Mở bàn phím nút nhanh"},
            {"command": "status", "description": "📊 Tình hình in"},
            {"command": "photo", "description": "📷 Ảnh bàn in từ camera"},
            {"command": "help", "description": "Hướng dẫn dùng bot"},
        ]}, timeout=20)
    except Exception:                                    # noqa: BLE001
        pass


def loop(hooks: dict) -> None:
    """Thread nen: long-poll getUpdates; moi tin xu ly o thread rieng (vision cham)."""
    offset = 0
    registered = False
    while True:
        token, me = _cfg()
        if not token or not me:
            time.sleep(30)
            continue
        if not registered:
            _register_commands(token)
            registered = True
        try:
            r = _api(token, "getUpdates",
                     {"timeout": 50, "offset": offset, "allowed_updates": ["message"]})
            for u in r.get("result", []):
                offset = max(offset, u["update_id"] + 1)
                m = u.get("message") or {}
                chat = str((m.get("chat") or {}).get("id") or "")
                if chat != str(me):
                    continue                    # nguoi la — im lang tuyet doi
                threading.Thread(target=_handle,
                                 args=(token, chat, m.get("text") or "", hooks),
                                 daemon=True).start()
        except Exception:                       # noqa: BLE001 — mang VN chap chon
            time.sleep(5)


def start(hooks: dict) -> None:
    threading.Thread(target=loop, args=(hooks,), daemon=True).start()