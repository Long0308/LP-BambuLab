"use strict";
/* 03-time: đọc thời gian/khối lượng theo phiên bản Bambu Studio */
const { launch, openHub, analyze, close, Suite, fixture } = require("./lib/hub");

/* lấy text của ô .stat theo nhãn (l) trong #result */
function statByLabel(page, label) {
  return page.evaluate((label) => {
    const stats = [...document.querySelectorAll("#result .stat")];
    for (const st of stats) {
      const l = st.querySelector(".l");
      const v = st.querySelector(".v");
      if (l && l.textContent.trim() === label) return v ? v.textContent.trim() : "";
    }
    return "__NOT_FOUND__";
  }, label);
}

module.exports = async function run() {
  const s = new Suite("03-time");
  const browser = await launch();
  try {
    // --- Body 14: Bambu Studio 2.x, KHÔNG có <plate> ---
    {
      const name = "Body 14 - LP.3mf";
      const { page } = await openHub(browser);
      try {
        await analyze(page, fixture(name));
        const resultText = await page.evaluate(() => document.querySelector("#result").textContent || "");
        s.check(`[${name}] #result chứa 'KHÔNG phải lỗi thao tác'`, resultText.includes("KHÔNG phải lỗi thao tác"), "không thấy chuỗi");
        s.check(`[${name}] #result chứa 'cách duy nhất'`, resultText.includes("cách duy nhất"), "không thấy chuỗi");
        const t = await statByLabel(page, "Thời gian in");
        s.check(`[${name}] ô 'Thời gian in' = 'chưa slice'`, t.includes("chưa slice"), `thực tế: '${t}'`);
      } catch (e) {
        s.check(`[${name}] phân tích không lỗi/timeout`, false, String((e && e.message) || e));
      } finally {
        await page.close();
      }
    }

    // --- A1_bed_dragchain_RV01: client 1.10.x, CÓ <plate> (prediction=14171s, weight=74.93g) ---
    {
      const name = "A1_bed_dragchain_RV01.3mf";
      const { page } = await openHub(browser);
      try {
        await analyze(page, fixture(name));
        const t = await statByLabel(page, "Thời gian in");
        const w = await statByLabel(page, "Khối lượng");
        const resultText = await page.evaluate(() => document.querySelector("#result").textContent || "");
        s.check(`[${name}] ô 'Thời gian in' = '3h 56m'`, t.includes("3h 56m"), `thực tế: '${t}'`);
        s.check(`[${name}] ô 'Khối lượng' = '75 g'`, w.includes("75 g"), `thực tế: '${w}'`);
        s.check(
          `[${name}] #result KHÔNG chứa 'KHÔNG phải lỗi thao tác'`,
          !resultText.includes("KHÔNG phải lỗi thao tác"),
          "lại thấy chuỗi lỗi-thao-tác"
        );
      } catch (e) {
        s.check(`[${name}] phân tích không lỗi/timeout`, false, String((e && e.message) || e));
      } finally {
        await page.close();
      }
    }
  } finally {
    await close(browser);
  }
  return s;
};
