#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Hoi dap + soan tin bao bang AI qua OpenRouter.

Model mac dinh: NVIDIA Nemotron 3 Nano Omni (FREE — user chon 2026-07-16).
Doi model: them OPENROUTER_MODEL vao .env. Key: OPENROUTER_API_KEY trong .env.

Nguyen tac: AI la LOP TRANG TRI — moi cho goi deu phai co fallback khi AI
loi/cham/het quota (tra None, caller tu dung text thuong). KHONG de AI chan
luong bao chuong.
"""
from __future__ import annotations

import base64
import json
import os
import threading
import urllib.request

import printer_config

# Bo dem SU DUNG local (ai_usage.json canh file nay — gitignore): dem so lan
# chat/vision/roi-xuong-tra-phi de bao cao "con uoc bao nhieu lan" tren Telegram.
_USAGE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ai_usage.json")
_USAGE_LOCK = threading.Lock()


def _count(kind: str) -> None:
    with _USAGE_LOCK:
        try:
            d = json.load(open(_USAGE_PATH, encoding="utf-8"))
        except (OSError, ValueError):
            d = {}
        d[kind] = int(d.get(kind, 0)) + 1
        try:
            json.dump(d, open(_USAGE_PATH, "w", encoding="utf-8"))
        except OSError:
            pass


def _counts() -> dict:
    try:
        return json.load(open(_USAGE_PATH, encoding="utf-8"))
    except (OSError, ValueError):
        return {}

DEFAULT_MODEL = "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free"

# Gia THAT 1 cau hoi cua hub (~463 token vao = system prompt co bang so + cau hoi,
# ~120 token ra), tinh tu bang gia OpenRouter 2026-07-17. Dung cho bao cao /usage.
# DeepSeek KHONG co ban free tren OpenRouter (tra 11 model) — v4-flash re nhat va
# do that tra loi dung + nhanh nhat (5s vs 15s cua Nemotron free).
CHAT_COST = {
    "deepseek/deepseek-v4-flash": 0.000069,     # $0.098/1M in · $0.20/1M out
    "deepseek/deepseek-v4-pro": 0.000306,       # $0.435/1M in · $0.87/1M out
    "deepseek/deepseek-v3.2": 0.000173,
    "openai/gpt-5-nano": 0.000071,
}


def _knowledge() -> str:
    """Kho so DA KIEM CHUNG cua hub — nhung vao system prompt de AI KHONG bia so
    nguoc voi ground truth (test that: model free tra loi 'Matte 190°C' — sai bet,
    hub da chot 230°C chong ket). Import tre de khoi vong lap module."""
    try:
        import analyzer
        rows = []
        for k, v in analyzer.FIL_EXPORT.items():
            s = v["safe"]
            rows.append(f"- {k}: {s['nozzle_temperature']}°C, tran chay "
                        f"{s['filament_max_volumetric_speed']} mm³/s, flow "
                        f"{s['filament_flow_ratio']}, bàn {s['hot_plate_temp']}°C")
        return "\n".join(rows)
    except Exception:                                   # noqa: BLE001
        return ""


SYSTEM = ("Bạn là chuyên gia in 3D cho máy Bambu Lab A1 (khung hở, bàn dời trục Y, "
          "AMS Lite 4 khe, nozzle 0.4). Trả lời NGẮN GỌN bằng tiếng Việt, đúng trọng "
          "tâm, ưu tiên số liệu cụ thể. Không chào hỏi rườm rà.\n\n"
          "BẢNG SỐ ĐÃ KIỂM CHỨNG (nguồn: official Bambu 2 tầng profile + cộng đồng, "
          "hub đã audit) — khi được hỏi về nhiệt/tốc/bàn PHẢI dùng đúng bảng này, "
          "KHÔNG tự bịa số khác:\n" + _knowledge() + "\n\n"
          "Quy tắc bổ sung đã kiểm chứng: PLA Matte/Metal dễ KẸT (hạt độn) → 230°C + "
          "hạ trần chảy còn 12; vật cao ≥120mm → hạ accel 3000-5000 + travel 380 chống "
          "lệch trục; gờ rãnh nhịp ngắn → bật Don't support bridges thay vì chống support; "
          "ngân sách preset: mục tiêu +1h30 (sai số +2h) so với default 0.20mm.")


def _cfg() -> tuple[str | None, str]:
    try:
        env = printer_config._parse_dotenv(printer_config.env_path())  # noqa: SLF001
    except Exception:                                  # noqa: BLE001
        env = {}
    return env.get("OPENROUTER_API_KEY"), env.get("OPENROUTER_MODEL") or DEFAULT_MODEL


def enabled() -> bool:
    return bool(_cfg()[0])


def _call(model: str, key: str, messages: list, max_tokens: int, timeout: int) -> str | None:
    body = json.dumps({"model": model, "messages": messages,
                       "max_tokens": max_tokens}).encode("utf-8")
    req = urllib.request.Request(
        "https://openrouter.ai/api/v1/chat/completions", data=body, method="POST",
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json",
                 "HTTP-Referer": "https://github.com/Long0308/LP-BambuLab",
                 "X-Title": "LP-BambuLab Hub"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            d = json.loads(r.read().decode("utf-8", "ignore"))
        msg = (d.get("choices") or [{}])[0].get("message") or {}
        out = (msg.get("content") or "").strip()
        return out or None
    except Exception:                                   # noqa: BLE001 — AI chi la trang tri
        return None


def _chain(primary: str, vision: bool = False) -> list[str]:
    """Chuoi FALLBACK model. Thu tu: model chinh (.env) -> free du phong -> paid.

    Chat text mac dinh (user chot 2026-07-17 lan 2): deepseek-v4-flash TRA PHI
    ($0.098/1M in, ~$0.0002/cau) — do that tren cau ky thuat: dung so 230/12,
    5s (Nemotron free 15s), tieng Viet sach (free viet sai 'tran chay'/'ket khiet').
    DeepSeek KHONG co ban free tren OpenRouter (tra 11 model, 2026-07-17) va KHONG
    co vision -> vision van dung gemini-2.5-flash-lite, du phong Nano Omni free.
    """
    try:
        env = printer_config._parse_dotenv(printer_config.env_path())  # noqa: SLF001
    except Exception:                                   # noqa: BLE001
        env = {}
    # Vision: gpt-5-nano DO THAT khong tra loi anh -> du phong vision la Nano Omni
    # free (co vision, da test OK), roi moi toi paid text-capable cuoi chuoi.
    paid = env.get("OPENROUTER_PAID_MODEL") or "openai/gpt-5-nano"
    chain = [primary]
    if DEFAULT_MODEL not in chain:
        chain.append(DEFAULT_MODEL)                     # Nano Omni free du phong (co vision)
    if not vision and paid not in chain:
        chain.append(paid)
    return chain


def ask(question: str, context: str = "", system: str = SYSTEM,
        timeout: int = 45, max_tokens: int = 700) -> str | None:
    """Hoi 1 cau -> tra loi text; tu FALLBACK qua chuoi model, None khi het chuoi."""
    key, model = _cfg()
    if not key or not question.strip():
        return None
    user = question if not context else f"{question}\n\n[Bối cảnh máy in hiện tại]\n{context}"
    msgs = [{"role": "system", "content": system}, {"role": "user", "content": user}]
    for m in _chain(model):
        out = _call(m, key, msgs, max_tokens, timeout)
        if out:
            _count("chat")
            if not m.endswith(":free"):
                _count("chat_paid")
            return out
    return None


def ask_vision(question: str, images: list[bytes], context: str = "",
               timeout: int = 90, max_tokens: int = 800) -> str | None:
    """Hoi kem ANH (frame camera / render model) — model VISION rieng.

    Mac dinh Nemotron 3 Nano Omni free (co vision) — model hoi dap text (Super 120B)
    KHONG nhin duoc anh nen phai tach. Doi bang OPENROUTER_VISION_MODEL trong .env.
    """
    key, _ = _cfg()
    if not key or not images:
        return None
    try:
        env = printer_config._parse_dotenv(printer_config.env_path())  # noqa: SLF001
    except Exception:                                   # noqa: BLE001
        env = {}
    model = env.get("OPENROUTER_VISION_MODEL") or DEFAULT_MODEL
    user = question if not context else f"{question}\n\n[Bối cảnh máy in hiện tại]\n{context}"
    content: list = [{"type": "text", "text": user}]
    for jpg in images[:3]:                              # toi da 3 anh (loat chong FP ban chay)
        content.append({"type": "image_url", "image_url": {
            "url": "data:image/jpeg;base64," + base64.b64encode(jpg).decode("ascii")}})
    msgs = [{"role": "system", "content": SYSTEM},
            {"role": "user", "content": content}]
    for m in _chain(model, vision=True):                # vision free -> paid co vision
        out = _call(m, key, msgs, max_tokens, timeout)
        if out:
            _count("vision")
            if not m.endswith(":free"):
                _count("vision_paid")
            return out
    return None


def usage_report() -> str:
    """Bao cao chi phi AI cho Telegram: so du, hub da dung, uoc con bao nhieu lan.

    So tien tu OpenRouter API that (/auth/key = chi tieu cua KEY nay, /credits =
    tai khoan); so LAN tu bo dem local. Gia vision ~$0.0004/lan (gemini-2.5-flash-
    lite $0.10/1M, ~3 anh/lan — do that 2026-07-17: 12 lan soi + chat = $0.0032).
    """
    key, _ = _cfg()
    if not key:
        return "Chưa cấu hình OPENROUTER_API_KEY."
    bal = spent_key = None
    try:
        req = urllib.request.Request("https://openrouter.ai/api/v1/auth/key",
                                     headers={"Authorization": f"Bearer {key}"})
        d = json.loads(urllib.request.urlopen(req, timeout=15).read()).get("data") or {}
        spent_key = float(d.get("usage") or 0)
        req = urllib.request.Request("https://openrouter.ai/api/v1/credits",
                                     headers={"Authorization": f"Bearer {key}"})
        c = json.loads(urllib.request.urlopen(req, timeout=15).read()).get("data") or {}
        bal = float(c.get("total_credits") or 0) - float(c.get("total_usage") or 0)
    except Exception:                                   # noqa: BLE001
        pass
    n = _counts()
    nv, nc = int(n.get("vision", 0)), int(n.get("chat", 0))
    vp, cp = int(n.get("vision_paid", 0)), int(n.get("chat_paid", 0))
    # gia vision trung binh THAT cua hub: tien key / so lan tra phi (fallback 0.0004)
    v_cost = (spent_key / vp) if (spent_key and vp) else 0.0004
    lines = ["💰 <b>Chi phí AI (OpenRouter)</b>"]
    if bal is not None:
        lines.append(f"Số dư tài khoản: <b>${bal:.2f}</b>")
    if spent_key is not None:
        lines.append(f"Hub đã tiêu (key này): <b>${spent_key:.4f}</b>")
    lines.append(f"Đã gọi: {nc} chat ({cp} lần rơi xuống trả phí) · {nv} vision "
                 f"({vp} trả phí)")
    lines.append(f"Giá vision TB: ~${v_cost:.4f}/lần soi")
    if bal is not None and v_cost > 0:
        lines.append(f"→ Còn ước <b>~{int(bal / v_cost):,} lần phân tích vision</b>")
    _, cm = _cfg()
    if cm.endswith(":free"):
        lines.append(f"Chat text: FREE $0 ({cm.split('/')[-1]}).")
    else:
        # Gia/cau tinh THAT theo do dai prompt hub (system + cau hoi + tra loi)
        c = CHAT_COST.get(cm, 0.0002)
        lines.append(f"Chat text: {cm.split('/')[-1]} ~${c:.6f}/câu")
        if bal is not None:
            lines.append(f"→ Hoặc ~{int(bal / c):,} câu chat")
    return "\n".join(lines)