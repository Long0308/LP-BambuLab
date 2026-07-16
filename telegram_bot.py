#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Bot Telegram 2 CHIEU — nut bam nhanh + hoi dap AI ngay trong Telegram.

Ban phim thuong truc (reply keyboard):
  📊 Tình hình in   → trang thai %, lop, con bao lau
  📷 Ảnh bàn in     → chup frame camera A1 gui vao chat
  🌡️ Nhiệt & khay   → nozzle/bed + 4 khe AMS
  Go cau hoi bat ky → AI (ai_chat, kem trang thai may) tra loi

BAO MAT: chi tra loi TELEGRAM_CHAT_ID trong .env — nguoi la nhan bot thi im lang.
Thread long-poll getUpdates rieng, mang loi thi ngu 5s thu lai (VN hay bop Telegram).
Cac ham lay du lieu (status/frame) duoc TIEM tu bambu_web de khoi import vong.
"""
from __future__ import annotations

import json
import threading
import time
import urllib.request
import uuid

import ai_chat
import notify

BTN_STATUS = "📊 Tình hình in"
BTN_PHOTO = "📷 Ảnh bàn in"
BTN_TEMP = "🌡️ Nhiệt & khay"
_KEYBOARD = {"keyboard": [[{"text": BTN_STATUS}, {"text": BTN_PHOTO}],
                          [{"text": BTN_TEMP}]],
             "resize_keyboard": True, "is_persistent": True}


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


def _send(token: str, chat: str, text: str) -> None:
    _api(token, "sendMessage", {"chat_id": chat, "text": text,
                                "reply_markup": _KEYBOARD}, timeout=20)


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


def _handle(token: str, chat: str, text: str, hooks: dict) -> None:
    t = (text or "").strip()
    if t in ("/start", "/help"):
        _send(token, chat, "Bot máy in A1 sẵn sàng — bấm nút bên dưới hoặc gõ câu hỏi "
                           "bất kỳ (AI trả lời, biết trạng thái máy).")
    elif t == BTN_STATUS or t == "/status":
        _send(token, chat, hooks["status"]())
    elif t == BTN_TEMP:
        _send(token, chat, hooks["temps"]())
    elif t == BTN_PHOTO or t == "/photo":
        jpg = hooks["frame"]()
        if jpg:
            _send_photo(token, chat, jpg, caption=hooks["status"]())
        else:
            _send(token, chat, "Camera chưa có hình (máy tắt / đang kết nối) — thử lại.")
    else:
        a = ai_chat.ask(t, context=hooks["status"]() + "\n" + hooks["temps"]()) \
            or "AI không phản hồi (model free có thể hết lượt hôm nay) — thử lại sau."
        _send(token, chat, a)


def loop(hooks: dict) -> None:
    """Thread nen: long-poll getUpdates. hooks = {'status':fn, 'temps':fn, 'frame':fn}."""
    offset = 0
    while True:
        token, me = _cfg()
        if not token or not me:
            time.sleep(30)                     # chua cau hinh — cho user dien .env
            continue
        try:
            r = _api(token, "getUpdates",
                     {"timeout": 50, "offset": offset,
                      "allowed_updates": ["message"]})
            for u in r.get("result", []):
                offset = max(offset, u["update_id"] + 1)
                m = u.get("message") or {}
                chat = str((m.get("chat") or {}).get("id") or "")
                if chat != str(me):
                    continue                    # nguoi la — im lang tuyet doi
                try:
                    _handle(token, chat, m.get("text") or "", hooks)
                except Exception:               # noqa: BLE001 — 1 tin loi khong giet loop
                    pass
        except Exception:                       # noqa: BLE001 — mang VN chap chon
            time.sleep(5)


def start(hooks: dict) -> None:
    threading.Thread(target=loop, args=(hooks,), daemon=True).start()