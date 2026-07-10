"use strict";
/* 01-smoke: cấu trúc tab/panel, chuyển tab, OPTIONS, tab ky-thuat */
const { launch, openHub, close, Suite } = require("./lib/hub");

module.exports = async function run() {
  const s = new Suite("01-smoke");
  const browser = await launch();
  try {
    const { page, errors } = await openHub(browser);

    // --- tập tab & panel ---
    const info = await page.evaluate(() => {
      const tabs = [...document.querySelectorAll("button[data-tab]")].map((b) => b.dataset.tab);
      const panels = [...document.querySelectorAll('section[role="tabpanel"]')].map((p) => p.id);
      return { tabs, panels };
    });
    s.eq("Đúng 8 button[data-tab]", info.tabs.length, 8);
    s.eq("Đúng 8 section[role=tabpanel]", info.panels.length, 8);
    const tabSet = [...info.tabs].sort().join(",");
    const panelSet = [...info.panels].sort().join(",");
    s.check("Tập id tab khớp tập id panel", tabSet === panelSet, `tabs=[${tabSet}] vs panels=[${panelSet}]`);

    // --- bấm từng tab: panel đúng có 'on', panel khác không ---
    for (const id of info.tabs) {
      await page.click(`button[data-tab="${id}"]`);
      const res = await page.evaluate((id, ids) => {
        const target = document.getElementById(id);
        const targetOn = !!target && target.classList.contains("on");
        const othersOff = ids
          .filter((x) => x !== id)
          .every((x) => {
            const p = document.getElementById(x);
            return p && !p.classList.contains("on");
          });
        return { targetOn, othersOff };
      }, id, info.panels);
      s.check(`Tab '${id}': panel tương ứng bật (class on)`, res.targetOn, "panel không có class on");
      s.check(`Tab '${id}': các panel khác tắt`, res.othersOff, "còn panel khác giữ class on");
    }

    s.eq("pageerror = 0 sau khi bấm hết 8 tab", errors.length, 0, `errors: ${errors.join(" | ")}`);

    // --- OPTIONS (đọc bằng tên trần trong page) ---
    const opt = await page.evaluate(() => {
      const names = (arr) => (arr || []).map((x) => (Array.isArray(x) ? String(x[0]) : String(x)));
      return {
        stLen: OPTIONS.support_type.length,
        stNames: names(OPTIONS.support_type),
        styleExists: !!OPTIONS.support_style,
        styleLen: OPTIONS.support_style ? OPTIONS.support_style.length : -1,
        brimNames: names(OPTIONS.brim_type),
      };
    });
    s.eq("OPTIONS.support_type có đúng 4 mục", opt.stLen, 4);
    s.check(
      "OPTIONS.support_type KHÔNG chứa 'hybrid(auto)'",
      !opt.stNames.some((n) => n.includes("hybrid(auto)")),
      `stNames: ${opt.stNames.join(" | ")}`
    );
    s.check("OPTIONS.support_style tồn tại", opt.styleExists, "không có OPTIONS.support_style");
    s.eq("OPTIONS.support_style có 7 mục", opt.styleLen, 7);
    s.check(
      "OPTIONS.brim_type chứa 'auto_brim'",
      opt.brimNames.some((n) => n.includes("auto_brim")),
      `brimNames: ${opt.brimNames.join(" | ")}`
    );
    s.check(
      "OPTIONS.brim_type chứa 'Painted'",
      opt.brimNames.some((n) => n.includes("Painted")),
      `brimNames: ${opt.brimNames.join(" | ")}`
    );

    // --- tab ky-thuat: EXTRACT / TRANSFORM / >=50 <tr> ---
    await page.click('button[data-tab="ky-thuat"]');
    const kt = await page.evaluate(() => {
      const el = document.getElementById("ky-thuat");
      return { html: el.innerHTML, trCount: el.querySelectorAll("tr").length };
    });
    s.check("Tab ky-thuat chứa 'EXTRACT'", kt.html.includes("EXTRACT"), "không thấy EXTRACT");
    s.check("Tab ky-thuat chứa 'TRANSFORM'", kt.html.includes("TRANSFORM"), "không thấy TRANSFORM");
    s.check("Bảng tra key ky-thuat có >= 50 <tr>", kt.trCount >= 50, `chỉ có ${kt.trCount} <tr>`);
  } finally {
    await close(browser);
  }
  return s;
};
