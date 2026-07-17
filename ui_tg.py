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


def finish_at(rem_min: int) -> str:
    """Gio XONG DU KIEN (bay gio + con lai) — Studio hien 'Estimated finish time',
    user chot 2026-07-17: nhin gio xong de sap xep cong viec, tien hon 'con 1h27m'."""
    import datetime
    t = datetime.datetime.now() + datetime.timedelta(minutes=max(0, int(rem_min or 0)))
    d = "" if t.day == datetime.datetime.now().day else " (mai)"
    return t.strftime("%H:%M") + d


def status_card(d: dict, connected: bool, weight: float | None = None,
                hub: str = "") -> str:
    """The TRANG THAI — bo cuc bam theo thanh tien do cua Bambu Studio (user chot):
    TEN FILE tren dau -> thanh + % -> lop · con lai -> GIO XONG DU KIEN -> link.
    """
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
    ic = ICON.get(gc, ICON["info"])
    out = [f"{ic} <b>{fn}</b>",                       # ten file TREN DAU nhu Studio
           f"<code>{bar(pct, 14)}</code> <b>{pct}%</b> · {LABEL.get(gc, gc)}"]
    if gc == "RUNNING" or pct:
        line = f"🧱 Lớp {d.get('layer_num', '?')}/{d.get('total_layer_num', '?')}"
        if rem:
            line += f"  ·  ⏳ còn {hm(rem)}"
        out.append(line)
        if rem and gc == "RUNNING":
            out.append(f"🏁 Xong lúc <b>~{finish_at(rem)}</b>")
    if weight:
        out.append(f"🎨 Nhựa ~{weight} g")
    if hub:
        out.append(f"🔗 {hub}")
    return "\n".join(out)


def dot(hexcol: str) -> str:
    """Ma mau cuon -> CHAM MAU emoji (Telegram khong render mau CSS). Bang mau co
    ban gan dung theo RGB — de nhin phat biet khe nao cuon nao, nhu so do AMS trong
    Bambu Studio (user chot 2026-07-17)."""
    h = (hexcol or "").lstrip("#")[:6]
    try:
        rv, gv, bv = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    except ValueError:
        return "⬜"
    mx, mn = max(rv, gv, bv), min(rv, gv, bv)
    if mx < 60:
        return "⚫"
    if mn > 200:
        return "⚪"
    if mx - mn < 30:
        return "🔘"                                   # xam
    if rv >= gv and rv >= bv:
        if bv < 100 and gv > 170:
            return "🟡"
        if bv < 100 and gv > 60:
            return "🟠"
        return "🔴"
    if gv >= rv and gv >= bv:
        return "🟢"
    return "🟣" if rv > 120 else "🔵"


def temps_card(d: dict, ams: list, colors: list | None = None,
               now: int = -1, hub: str = "") -> str:
    """The NHIET & KHAY — bo cuc bam theo man hinh Device cua Bambu Studio:
    nhiet 'hien tai / dich', quat %, va so do 4 khe co CHAM MAU + danh dau khe
    DANG DUNG (user: 'thong so va nhua nhiet do lam dep nhu Studio')."""
    def _t(v):
        try:
            return f"{float(v):.0f}"
        except (TypeError, ValueError):
            return "—"
    rows = [("🌡 Đầu phun", f"<b>{_t(d.get('nozzle_temper'))}</b> / "
                            f"{_t(d.get('nozzle_target_temper'))} °C"),
            ("🔥 Bàn in", f"<b>{_t(d.get('bed_temper'))}</b> / "
                          f"{_t(d.get('bed_target_temper'))} °C")]
    fan = d.get("cooling_fan_speed")
    if fan not in (None, ""):
        try:                                          # MQTT tra 0-15 -> doi ra %
            fv = int(fan)
            rows.append(("💨 Quạt", f"{fv if fv > 15 else round(fv / 15 * 100)}%"))
        except (TypeError, ValueError):
            pass
    body = ""
    if ams:
        cols = colors or []
        lines = ["", "<b>Khay AMS Lite</b>"]
        for i, t in enumerate(ams[:4], 1):
            c = cols[i - 1] if i - 1 < len(cols) else ""
            mark = " ◀ <b>đang dùng</b>" if (i - 1) == now else ""
            lines.append(f"{dot(c)} <code>Khe {i}</code>  {esc(t)}"
                         f"{f'  <code>{esc(c)}</code>' if c else ''}{mark}")
        body = "\n".join(lines)
    return card("NHIỆT & KHAY", rows, body=body, icon="🌡", link=hub)


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