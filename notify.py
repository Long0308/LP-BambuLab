#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Bao chuong ve dien thoai khi may in XONG / LOI — ntfy + Telegram + Discord.

Cau hinh trong file .env (canh bambu_web.py — cung cho voi BAMBU_HOST), chi can
dien kenh nao muon dung, bo trong = tat kenh do:

  # ntfy (don gian nhat — cai app ntfy tren iPhone/Android, subscribe topic)
  NTFY_TOPIC=lp-bambu-a1-abc123        # tu dat, cang kho doan cang kin
  NTFY_SERVER=https://ntfy.sh          # mac dinh, tu host duoc thi doi

  # Telegram (tao bot qua @BotFather -> token; chat_id lay qua @userinfobot)
  TELEGRAM_BOT_TOKEN=123456:ABC-xyz
  TELEGRAM_CHAT_ID=123456789

  # Discord (Server Settings > Integrations > Webhooks > New Webhook > Copy URL)
  DISCORD_WEBHOOK=https://discord.com/api/webhooks/...

Gui "fire-and-forget" trong thread rieng — mat mang cung KHONG lam hub cham/treo.
"""
from __future__ import annotations

import json
import os
import re
import threading
import time
import urllib.request

import printer_config


def _env() -> dict:
    """Doc .env moi lan goi (sua .env khong can restart hub) + os.environ de len."""
    data = {}
    try:
        data = printer_config._parse_dotenv(printer_config.env_path())  # noqa: SLF001
    except Exception:                                     # noqa: BLE001
        pass
    for k in ("NTFY_TOPIC", "NTFY_SERVER", "TELEGRAM_BOT_TOKEN",
              "TELEGRAM_CHAT_ID", "DISCORD_WEBHOOK", "HUB_URL"):
        if os.environ.get(k):
            data[k] = os.environ[k]
    return data


def hub_url() -> str:
    """Link dashboard (Tailscale) — dinh kem vao tin bao loi de user mo camera ngay."""
    return (_env().get("HUB_URL") or "https://administrator.tail2d2fb4.ts.net/").strip()


def channels() -> list[str]:
    """Kenh dang bat (de hien tren UI cho user biet da cau hinh chua)."""
    e = _env()
    out = []
    if e.get("NTFY_TOPIC"):
        out.append("ntfy")
    if e.get("TELEGRAM_BOT_TOKEN") and e.get("TELEGRAM_CHAT_ID"):
        out.append("telegram")
    if e.get("DISCORD_WEBHOOK"):
        out.append("discord")
    return out


def _post(url: str, data: bytes, headers: dict, tries: int = 3) -> None:
    """POST co RETRY — mang VN hay bop/chan api.telegram.org chap chon (do that:
    luc duoc luc 'handshake timed out'), thu lai 2-3 lan la qua duoc phan lon."""
    last: Exception | None = None
    for _ in range(tries):
        try:
            req = urllib.request.Request(url, data=data, headers=headers, method="POST")
            urllib.request.urlopen(req, timeout=15).read()
            return
        except Exception as e:                          # noqa: BLE001
            last = e
    raise last if last else RuntimeError("post fail")


def _log(line: str) -> None:
    """Nhat ky gui tin -> notify.log (canh bambu_web) — soi duoc vi sao tin khong den."""
    try:
        with open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                               "notify.log"), "a", encoding="utf-8") as f:
            f.write(time.strftime("%Y-%m-%d %H:%M:%S ") + line + "\n")
    except OSError:
        pass


_TAG = re.compile(r"<[^>]+>")


def _plain(s: str) -> str:
    """Bo the HTML cho kenh khong hieu HTML (ntfy header / Discord) + tra lai
    ky tu da escape. Telegram thi giu nguyen the."""
    return (_TAG.sub("", s or "").replace("&lt;", "<").replace("&gt;", ">")
            .replace("&amp;", "&"))


def _send_all(title: str, body: str, urgent: bool, html: bool = True) -> list[str]:
    """Gui 1 tin di moi kenh. body co the chua the HTML (ui_tg.card) — Telegram
    render, ntfy/Discord tu lược the (user: 'moc tien do phai dep nhu tinh hinh in')."""
    e = _env()
    sent: list[str] = []
    t_plain, b_plain = _plain(title), _plain(body)
    if e.get("NTFY_TOPIC"):
        try:
            _post(f"{e.get('NTFY_SERVER') or 'https://ntfy.sh'}/{e['NTFY_TOPIC']}",
                  b_plain.encode("utf-8"),
                  {"Title": t_plain.encode("utf-8").decode("latin-1"),  # header latin-1
                   "Priority": "urgent" if urgent else "high",
                   "Tags": "rotating_light" if urgent else "white_check_mark"})
            sent.append("ntfy")
        except Exception as ex:                            # noqa: BLE001
            sent.append(f"ntfy:LOI {ex}")
    if e.get("TELEGRAM_BOT_TOKEN") and e.get("TELEGRAM_CHAT_ID"):
        for attempt in (True, False):        # HTML loi (the la) -> gui lai dang tho
            use_html = html and attempt
            p = {"chat_id": e["TELEGRAM_CHAT_ID"],
                 "text": (f"{title}\n{body}" if use_html
                          else f"{'🚨' if urgent else '✅'} {t_plain}\n{b_plain}")}
            if use_html:
                p["parse_mode"] = "HTML"
            try:
                _post(f"https://api.telegram.org/bot{e['TELEGRAM_BOT_TOKEN']}/sendMessage",
                      json.dumps(p).encode(), {"Content-Type": "application/json"})
                sent.append("telegram")
                break
            except Exception as ex:                        # noqa: BLE001
                if not use_html:                           # ca 2 lan deu hong
                    sent.append(f"telegram:LOI {ex}")
    if e.get("DISCORD_WEBHOOK"):
        try:
            _post(e["DISCORD_WEBHOOK"],
                  json.dumps({"content": f"{'🚨' if urgent else '✅'} **{t_plain}**\n"
                                         f"{b_plain}"}).encode(),
                  {"Content-Type": "application/json"})
            sent.append("discord")
        except Exception as ex:                            # noqa: BLE001
            sent.append(f"discord:LOI {ex}")
    _log(f"[{t_plain}] -> {', '.join(sent) or 'KHONG CO KENH'}")
    return sent


def send(title: str, body: str, urgent: bool = False) -> None:
    """Gui khong chan (thread nen) — goi tu MQTT handler an toan."""
    threading.Thread(target=_send_all, args=(title, body, urgent), daemon=True).start()


def send_sync(title: str, body: str, urgent: bool = False) -> list[str]:
    """Gui dong bo — cho /api/notify-test tra ket qua tung kenh."""
    return _send_all(title, body, urgent)


def alarm(title: str, body: str, times: int = 10, gap_s: float = 3.0) -> None:
    """BAO DONG DON DAP — gui lien tiep `times` tin cach nhau vai giay de danh thuc
    (user chot 2026-07-16: loi la spam 10 tin nhu bao dong). Chay thread nen."""
    def _run():
        for i in range(times):
            _send_all(f"{title} ({i + 1}/{times})", body, urgent=True)
            time.sleep(gap_s)
    threading.Thread(target=_run, daemon=True).start()


def send_photos_telegram(jpgs: list, caption: str = "") -> bool:
    """Gui NHIEU anh thanh 1 ALBUM (sendMediaGroup) — user thay DUNG cac frame AI da
    nhin, tu doi chieu duoc (user hoi 2026-07-17: 'AI phan tich anh nao?'). Caption
    gan vao anh dau. Loi -> fallback gui 1 anh net nhat."""
    e = _env()
    tok, chat = e.get("TELEGRAM_BOT_TOKEN"), e.get("TELEGRAM_CHAT_ID")
    jpgs = [j for j in (jpgs or []) if j]
    if not (tok and chat and jpgs):
        return False
    if len(jpgs) == 1:
        return send_photo_telegram(jpgs[0], caption)
    import uuid
    b = uuid.uuid4().hex
    media, parts = [], []
    for i, jpg in enumerate(jpgs[:10]):          # Telegram cho toi da 10 anh/album
        name = f"f{i}"
        m = {"type": "photo", "media": f"attach://{name}"}
        if i == 0 and caption:
            m["caption"] = caption[:1024]
        media.append(m)
        parts.append((name, jpg))
    body = (f"--{b}\r\nContent-Disposition: form-data; name=\"chat_id\"\r\n\r\n{chat}\r\n"
            f"--{b}\r\nContent-Disposition: form-data; name=\"media\"\r\n\r\n"
            f"{json.dumps(media)}\r\n").encode("utf-8")
    for name, jpg in parts:
        body += (f"--{b}\r\nContent-Disposition: form-data; name=\"{name}\"; "
                 f"filename=\"{name}.jpg\"\r\nContent-Type: image/jpeg\r\n\r\n").encode()
        body += jpg + b"\r\n"
    body += f"--{b}--\r\n".encode()
    try:
        _post(f"https://api.telegram.org/bot{tok}/sendMediaGroup", body,
              {"Content-Type": f"multipart/form-data; boundary={b}"})
        return True
    except Exception:                                   # noqa: BLE001
        return send_photo_telegram(max(jpgs, key=len), caption)


def send_photo_telegram(jpg: bytes, caption: str = "") -> bool:
    """Gui ANH (frame camera) vao Telegram — best-effort, loi thi thoi."""
    e = _env()
    tok, chat = e.get("TELEGRAM_BOT_TOKEN"), e.get("TELEGRAM_CHAT_ID")
    if not (tok and chat and jpg):
        return False
    import uuid
    b = uuid.uuid4().hex
    body = (f"--{b}\r\nContent-Disposition: form-data; name=\"chat_id\"\r\n\r\n{chat}\r\n"
            f"--{b}\r\nContent-Disposition: form-data; name=\"caption\"\r\n\r\n{caption}\r\n"
            f"--{b}\r\nContent-Disposition: form-data; name=\"photo\"; "
            f"filename=\"cam.jpg\"\r\nContent-Type: image/jpeg\r\n\r\n").encode("utf-8")
    body += jpg + f"\r\n--{b}--\r\n".encode("utf-8")
    try:
        _post(f"https://api.telegram.org/bot{tok}/sendPhoto", body,
              {"Content-Type": f"multipart/form-data; boundary={b}"})
        return True
    except Exception:                                   # noqa: BLE001
        return False