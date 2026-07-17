#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""UI cho tin nhan Telegram — mot NGUON DUY NHAT de moi tin cung mot ngon ngu.

Telegram chi cho <b> <i> <u> <s> <code> <pre> <a> <blockquote> — KHONG co CSS,
khong SVG. Nen "UI" o day = 4 thu:
  1. PHAN CAP: dong 1 la ket qua (icon + trang thai), chi tiet o duoi, link cuoi.
  2. MONOSPACE: thanh tien do + bang so dat trong <code> de KHONG XO LECH khi
     font Telegram doi be rong (emoji/chu Viet co dau rong khac nhau).
  3. THE NHAT QUAN: moi tin deu <b>tieu de</b> -> than -> link. Nhin 1 giay biet
     dang doc gi, khong phai do.
  4. EMOJI = TRANG THAI, khong phai trang tri: 1 emoji dau dong, dung bang co dinh
     ben duoi (skill ui-ux-pro-max cam emoji lam icon — nhung Telegram khong co he
     icon nao khac; bu lai bang cach dung NHAT QUAN va tiet che, moi tin 1 icon
     chinh + toi da 1 icon/dong chi tiet).
Text luon _esc() truoc khi nhung (ten file co the co & < >).
"""
from __future__ import annotations

import html as _html

# Bang icon TRANG THAI — dung o MOI noi (bot, alarm, moc tien do). Doi o day =
# doi toan bo, khong the lech nhu truoc.
ICON = {
    "IDLE": "💤", "RUNNING": "🖨", "PAUSE": "⏸", "FINISH": "✅",
    "FAILED": "🚨", "PREPARE": "⚙️", "SLICING": "⚙️", "OFFLINE": "🔌",
    "ok": "✅", "warn": "⚠️", "bad": "🚨", "info": "ℹ️", "ai": "🤖",
    "cam": "📷", "money": "💰", "tip": "💡",
}
LABEL = {"IDLE": "Đang rảnh", "RUNNING": "ĐANG IN", "PAUSE": "TẠM DỪNG",
         "FINISH": "IN XONG", "FAILED": "IN LỖI", "PREPARE": "Đang chuẩn bị",
         "SLICING": "Đang slice"}


def esc(s) -> str:
    return _html.escape(str(s if s is not None else ""))


def bar(pct: int, width: int = 12) -> str:
    """Thanh tien do monospace. Ky tu khoi day/rong CUNG BE RONG -> khong xo lech.
    Dat trong <code> de Telegram render font deu."""
    pct = max(0, min(100, int(pct or 0)))
    fill = round(pct * width / 100)
    return "█" * fill + "░" * (width - fill)


def hm(minutes: int) -> str:
    m = max(0, int(minutes or 0))
    return f"{m // 60}h{m % 60:02d}m" if m >= 60 else f"{m}m"


def card(title: str, rows: list[tuple[str, str]] | None = None,
         body: str = "", link: str = "", icon: str = "") -> str:
    """1 THE tin nhan: tieu de dam -> cac dong nhan/gia tri -> than -> link.

    rows: [(nhan, gia tri)] — nhan can le trai bang <code> nen cot gia tri thang hang.
    """
    pre = f"{icon} " if icon else ""
    out = [f"{pre}<b>{title}</b>"]
    if rows:
        w = max((len(r[0]) for r in rows), default=0)
        out += [f"<code>{r[0].ljust(w)}</code>  {r[1]}" for r in rows]
    if body:
        out.append(body)
    if link:
        out.append(f"🔗 {link}")
    return "\n".join(out)


def quote(text: str, expandable: bool = True) -> str:
    """Tra loi AI dai -> blockquote thu gon duoc, khong lam ngop khung chat."""
    tag = "<blockquote expandable>" if expandable else "<blockquote>"
    return f"{tag}{esc(text)}</blockquote>"


def status_card(d: dict, connected: bool, weight: float | None = None,
                hub: str = "") -> str:
    """The TRANG THAI — dung chung cho nut '📊 Tình hình in' va boi canh AI."""
    if not connected and not d:
        return card("MÁY IN OFFLINE", icon=ICON["OFFLINE"],
                    body="Máy tắt hoặc mất kết nối — sẽ tự báo khi bật lại.")
    gc = str(d.get("gcode_state") or "?")
    try:
        pct = int(d.get("mc_percent") or 0)
        rem = int(d.get("mc_remaining_time") or 0)
    except (TypeError, ValueError):
        pct, rem = 0, 0
    fn = esc(d.get("subtask_name") or d.get("gcode_file") or "—")
    rows = [("Tiến độ", f"<code>{bar(pct)}</code> <b>{pct}%</b>")]
    if gc == "RUNNING" or pct:
        rows += [("Lớp", f"{d.get('layer_num', '?')}/{d.get('total_layer_num', '?')}"),
                 ("Còn lại", f"~{hm(rem)}")]
    if weight:
        rows.append(("Nhựa", f"~{weight} g"))
    return card(f"{LABEL.get(gc, gc)} · {fn}", rows,
                icon=ICON.get(gc, ICON["info"]), link=hub)


def temps_card(d: dict, ams: list, hub: str = "") -> str:
    def _t(v):
        try:
            return f"{float(v):.0f}"
        except (TypeError, ValueError):
            return "?"
    rows = [("Đầu phun", f"<code>{_t(d.get('nozzle_temper')):>3}→"
                         f"{_t(d.get('nozzle_target_temper')):>3}°C</code>"),
            ("Bàn in", f"<code>{_t(d.get('bed_temper')):>3}→"
                       f"{_t(d.get('bed_target_temper')):>3}°C</code>")]
    for i, t in enumerate(ams[:4], 1):
        rows.append((f"Khe {i}", esc(t)))
    return card("NHIỆT & KHAY AMS", rows, icon="🌡")


def verdict_of(text: str) -> tuple[str, str]:
    """Doc ket luan AI vision -> (icon, nhan) — dung cho caption anh + tin bao.

    CHI doc DONG DAU (dong 'KQ: ...'), khong quet ca bai: cau ly do 'KHÔNG có dấu
    hiệu hỏng' chua chuoi 'HONG' -> quet ca bai la bao HONG nguoc (bug that
    2026-07-17). Thu tu kiem: ON -> NGHI NGO -> HONG.
    """
    import re
    import unicodedata
    raw = (text or "").strip().split("\n", 1)[0]
    # bo dau tieng Viet -> 'ỔN'->'ON', 'HỎNG'->'HONG' (model tra ca 2 kieu)
    flat = "".join(c for c in unicodedata.normalize("NFD", raw)
                   if unicodedata.category(c) != "Mn").upper().replace("Đ", "D")
    # CHI lay NHAN ngay sau 'KQ:' den dau ngat cau — khong quet ca dong: cau ly do
    # 'khong co dau hieu HONG' nam cung dong se lam bao HONG nguoc (bug that).
    m = re.search(r"KQ\s*:?\s*([A-Z\s]{2,12})", flat)
    lab = (m.group(1) if m else flat)[:12].strip()
    if lab.startswith("NGHI"):
        return ICON["warn"], "NGHI NGỜ"
    if lab.startswith("HONG"):
        return ICON["bad"], "HỎNG"
    if lab.startswith("ON"):
        return ICON["ok"], "ỔN"
    return ICON["info"], "?"