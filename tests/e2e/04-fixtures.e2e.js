"use strict";
/* 04-fixtures: chứng minh CHIỀU DƯƠNG của các luật bẫy bằng fixture tự dựng.
 * Downloads không có file nào rơi vào các ca này (boxson.3mf đã bị xoá), nên
 * thiếu fixture là luật "pass" mãi mãi dù có chết cũng không ai biết.
 *  - scarf-trap.3mf     : filament_scarf_seam_type=none + seam_slope_type=external
 *  - nozzle-02-trap.3mf : printer preset "0.2 nozzle" trên vật 204mm (maxvol 2)
 */
const path = require("path");
const { launch, openHub, analyze, close, Suite } = require("./lib/hub");

const FIX = (name) => path.join(__dirname, "fixtures", name);

function getFindings(page) {
  return page.evaluate(() =>
    [...document.querySelectorAll("#result .find")].map((x) => ({
      lv: x.querySelector(".badge") ? x.querySelector(".badge").textContent.trim() : "?",
      t: x.querySelector("b") ? x.querySelector("b").textContent.trim() : "",
    }))
  );
}

module.exports = async function run() {
  const s = new Suite("04-fixtures");
  const browser = await launch();
  try {
    // --- scarf-trap: process bật scarf, filament để none → LỖI phải bắn ---
    {
      const name = "scarf-trap.3mf";
      const { page, errors } = await openHub(browser);
      try {
        await analyze(page, FIX(name));
        const finds = await getFindings(page);
        const hit = finds.find((f) => /Scarf seam bị Filament TẮT âm thầm/.test(f.t));
        s.check(`[${name}] LỖI scarf PHẢI bắn (chiều dương)`, !!hit, "không thấy finding");
        if (hit) s.eq(`[${name}] mức độ = LỖI`, hit.lv, "LỖI");
        s.eq(`[${name}] pageerror = 0`, errors.length, 0, errors[0]);
      } finally {
        await page.close();
      }
    }

    // --- nozzle-02-trap: preset 0.2 nozzle + vật 204mm → LỖI phải bắn ---
    {
      const name = "nozzle-02-trap.3mf";
      const { page, errors } = await openHub(browser);
      try {
        await analyze(page, FIX(name));
        const finds = await getFindings(page);
        const hit = finds.find((f) => /ĐẦU PHUN 0\.2mm cho vật LỚN/.test(f.t));
        s.check(`[${name}] LỖI 'ĐẦU PHUN 0.2mm cho vật LỚN' PHẢI bắn`, !!hit, "không thấy finding; có: " + finds.map((f) => f.t).join(" | "));
        if (hit) s.eq(`[${name}] mức độ = LỖI`, hit.lv, "LỖI");
        // maxvol=2 ⇒ mọi tốc độ đều vượt trần ⇒ luật vượt-trần (giờ là THÔNG TIN) cũng phải hiện
        const overInfo = finds.find((f) => /VƯỢT trần lưu lượng/.test(f.t));
        s.check(`[${name}] luật vượt-trần hiện (maxvol=2)`, !!overInfo, "không thấy");
        if (overInfo) s.eq(`[${name}] vượt-trần là THÔNG TIN, không phải CẢNH BÁO`, overInfo.lv, "THÔNG TIN");
        s.eq(`[${name}] pageerror = 0`, errors.length, 0, errors[0]);
      } finally {
        await page.close();
      }
    }
  } finally {
    await close(browser);
  }
  return s;
};
