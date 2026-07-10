"use strict";
/* 05-optimizer: bộ tối ưu chạy NGAY trong luồng phân tích, và im lặng là lỗi.
 *  - scarf-trap.3mf      : có mesh → bảng so sánh + nút xuất preset
 *  - no-mesh.gcode.3mf   : .gcode.3mf bị Bambu tước 3D/Objects/*.model → vẫn ra cấu hình
 *                          thuần-config, nhưng PHẢI nói rõ nhóm quyết định nào bị bỏ
 *  - nozzle-02-trap.3mf  : layer ngoài {0.16,0.20,0.24} → không có preset stock để
 *                          `inherits` → phải ẩn nút xuất và giải thích, không để bấm rồi alert
 */
const path = require("path");
const { launch, openHub, analyze, close, Suite } = require("./lib/hub");

const FIX = (name) => path.join(__dirname, "fixtures", name);
const WAIT = 60000;

async function plan(page) {
  await page
    .waitForFunction(() => /Cấu hình tối ưu/.test(document.querySelector("#result").innerText), { timeout: WAIT })
    .catch(() => {});
  return page.evaluate(() => {
    const r = document.querySelector("#result");
    const txt = r ? r.innerText : "";
    const hdr = (t) => [...t.querySelectorAll("tr:first-child th")].map((c) => c.innerText.trim().toLowerCase());
    const cmp = [...r.querySelectorAll("table")].find((t) => {
      const h = hdr(t);
      return h[0] === "key" && h[1] === "hiện tại";
    });
    return {
      hasSection: /Cấu hình tối ưu/.test(txt),
      hasBtn: !!document.querySelector("#expOpt"),
      noMesh: /không mang lưới hình học/.test(txt),
      cantExport: /Chưa xuất được preset/.test(txt),
      cmpRows: cmp ? cmp.querySelectorAll("tr").length - 1 : 0,
      cell: (k) => null,
      rows: cmp ? [...cmp.querySelectorAll("tr")].map((tr) => [...tr.querySelectorAll("td")].map((c) => c.innerText.trim())) : [],
    };
  });
}

module.exports = async function run() {
  const s = new Suite("05-optimizer");
  const browser = await launch();
  try {
    // --- có mesh: đầy đủ, có nút xuất ---
    {
      const name = "scarf-trap.3mf";
      const { page, errors } = await openHub(browser);
      try {
        await analyze(page, FIX(name));
        const p = await plan(page);
        s.check(`[${name}] bảng "Cấu hình tối ưu" phải hiện`, p.hasSection);
        s.check(`[${name}] có nút xuất preset`, p.hasBtn);
        s.check(`[${name}] KHÔNG báo thiếu mesh`, !p.noMesh);
        s.check(`[${name}] bảng so sánh có dòng`, p.cmpRows > 5, `chỉ ${p.cmpRows} dòng`);
        s.eq(`[${name}] pageerror = 0`, errors.length, 0, errors[0]);
      } finally {
        await page.close();
      }
    }

    // --- .gcode.3mf không mesh: vẫn ra cấu hình, và phải NÓI vì sao thiếu ---
    {
      const name = "no-mesh.gcode.3mf";
      const { page, errors } = await openHub(browser);
      try {
        await analyze(page, FIX(name));
        const p = await plan(page);
        s.check(`[${name}] vẫn sinh cấu hình từ Process config`, p.hasSection);
        s.check(`[${name}] PHẢI nói rõ thiếu mesh (im lặng là lỗi)`, p.noMesh);
        s.check(`[${name}] vẫn xuất được preset thuần-config`, p.hasBtn);
        const keys = p.rows.map((r) => r[0]);
        s.check(`[${name}] có inner_wall_speed (không cần mesh)`, keys.includes("inner_wall_speed"), keys.join(","));
        s.check(`[${name}] KHÔNG đoán enable_support`, !keys.includes("enable_support"), keys.join(","));
        s.check(`[${name}] KHÔNG đoán brim_type`, !keys.includes("brim_type"), keys.join(","));
        s.eq(`[${name}] pageerror = 0`, errors.length, 0, errors[0]);
      } finally {
        await page.close();
      }
    }

    // --- nozzle 0.2: không có preset stock để inherits → ẩn nút, giải thích ---
    {
      const name = "nozzle-02-trap.3mf";
      const { page, errors } = await openHub(browser);
      try {
        await analyze(page, FIX(name));
        const p = await plan(page);
        s.check(`[${name}] bảng tối ưu vẫn hiện (để chỉnh tay)`, p.hasSection);
        s.check(`[${name}] PHẢI ẩn nút xuất`, !p.hasBtn);
        s.check(`[${name}] PHẢI giải thích vì sao chưa xuất được`, p.cantExport);
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
