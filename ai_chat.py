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
import urllib.request

import printer_config

DEFAULT_MODEL = "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free"


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
    """Chuoi FALLBACK model (user chot 2026-07-17: 'co tien trong tai khoan ma dung
    free thi PHAI fallback'): free chinh -> free du phong -> TRA PHI re nhat.
    gpt-5-nano ($0.05/1M input, co vision) — 1 cau ~\\$0.0001, coi nhu bao hiem."""
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
            return out
    return None