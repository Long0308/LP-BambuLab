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
import threading
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
              "TELEGRAM_CHAT_ID", "DISCORD_WEBHOOK"):
        if os.environ.get(k):
            data[k] = os.environ[k]
    return data


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


def _send_all(title: str, body: str, urgent: bool) -> list[str]:
    e = _env()
    sent: list[str] = []
    if e.get("NTFY_TOPIC"):
        try:
            _post(f"{e.get('NTFY_SERVER') or 'https://ntfy.sh'}/{e['NTFY_TOPIC']}",
                  body.encode("utf-8"),
                  {"Title": title.encode("utf-8").decode("latin-1"),  # header phai latin-1
                   "Priority": "urgent" if urgent else "high",
                   "Tags": "rotating_light" if urgent else "white_check_mark"})
            sent.append("ntfy")
        except Exception as ex:                            # noqa: BLE001
            sent.append(f"ntfy:LOI {ex}")
    if e.get("TELEGRAM_BOT_TOKEN") and e.get("TELEGRAM_CHAT_ID"):
        try:
            _post(f"https://api.telegram.org/bot{e['TELEGRAM_BOT_TOKEN']}/sendMessage",
                  json.dumps({"chat_id": e["TELEGRAM_CHAT_ID"],
                              "text": f"{'🚨' if urgent else '✅'} {title}\n{body}"}).encode(),
                  {"Content-Type": "application/json"})
            sent.append("telegram")
        except Exception as ex:                            # noqa: BLE001
            sent.append(f"telegram:LOI {ex}")
    if e.get("DISCORD_WEBHOOK"):
        try:
            _post(e["DISCORD_WEBHOOK"],
                  json.dumps({"content": f"{'🚨' if urgent else '✅'} **{title}**\n{body}"}).encode(),
                  {"Content-Type": "application/json"})
            sent.append("discord")
        except Exception as ex:                            # noqa: BLE001
            sent.append(f"discord:LOI {ex}")
    return sent


def send(title: str, body: str, urgent: bool = False) -> None:
    """Gui khong chan (thread nen) — goi tu MQTT handler an toan."""
    threading.Thread(target=_send_all, args=(title, body, urgent), daemon=True).start()


def send_sync(title: str, body: str, urgent: bool = False) -> list[str]:
    """Gui dong bo — cho /api/notify-test tra ket qua tung kenh."""
    return _send_all(title, body, urgent)