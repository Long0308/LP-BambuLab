"use strict";
/* 02-analyze: phân tích từng .3mf — pageerror=0, findings>0, luật scarf & overhang */
const { launch, openHub, analyze, close, Suite, fixture } = require("./lib/hub");

const FILES = [
  "A1_bed_dragchain_RV01.3mf",
  "A1_side_drag_chain_V1.1.3mf",
  "A1_X2026.6.6版.3mf",
  "AMS+Lite+Top+Mount-Final.3mf",
  "Body 14 - LP.3mf",
  "Compact_poop_bucket_S_with_drawer_(A1,_A1_mini).3mf",
  "Dimond_Back_A1_AMS_ball_and_socket_5_point_clip_drag_chain_Bambu_PLA_Basic.3mf",
  "organic+controller+support.3mf",
  "简约风超实用收纳盒（化妆盒）.3mf",
];

module.exports = async function run() {
  const s = new Suite("02-analyze");
  const browser = await launch();
  try {
    for (const name of FILES) {
      const { page, errors } = await openHub(browser);
      try {
        await analyze(page, fixture(name));

        // pageerror = 0
        s.eq(`[${name}] pageerror = 0`, errors.length, 0, `errors: ${errors.join(" | ")}`);

        // findings > 0
        const nFind = await page.evaluate(() => (lastAnalysis && lastAnalysis.findings ? lastAnalysis.findings.length : -1));
        s.check(`[${name}] số finding > 0`, nFind > 0, `findings = ${nFind}`);

        // --- luật SCARF: tính lại độc lập bằng unzip() trên chính file đã upload ---
        const scarf = await page.evaluate(async () => {
          const inp = document.querySelector("#file");
          const f = inp.files[0];
          const buf = await f.arrayBuffer();
          const files = await unzip(buf);
          let cfg = null;
          for (const k in files) {
            if (k.toLowerCase().endsWith("project_settings.config")) {
              cfg = JSON.parse(td(files[k]));
              break;
            }
          }
          const fo = (v) => (Array.isArray(v) ? (v[0] == null ? "" : v[0]) : v == null ? "" : v);
          const filament = cfg ? String(fo(cfg.filament_scarf_seam_type) || "").toLowerCase() : "";
          const process = cfg ? String(fo(cfg.seam_slope_type) || "").toLowerCase() : "";
          const present = (lastAnalysis.findings || []).some((x) => x[1] === "Scarf seam bị Filament TẮT âm thầm");
          return { hasCfg: !!cfg, filament, process, present };
        });
        const expectScarf = scarf.filament === "none" && !!scarf.process && scarf.process !== "none";
        s.check(
          `[${name}] scarf finding ${expectScarf ? "PHẢI có" : "KHÔNG được có"} (fil='${scarf.filament}' proc='${scarf.process}')`,
          scarf.present === expectScarf,
          `kỳ vọng present=${expectScarf}, thực tế=${scarf.present} (hasCfg=${scarf.hasCfg})`
        );

        // --- luật OVERHANG: geo.down (đã trừ mặt đáy) ---
        const oh = await page.evaluate(() => {
          const down = lastAnalysis && lastAnalysis.geo ? lastAnalysis.geo.down : null;
          const present = (lastAnalysis.findings || []).some((x) => x[1] === "Gần như KHÔNG cần support");
          return { down, present };
        });
        const expectOh = oh.down != null && oh.down <= 2;
        s.check(
          `[${name}] overhang finding ${expectOh ? "PHẢI có" : "KHÔNG được có"} (down=${oh.down == null ? "null" : oh.down.toFixed(2)}%)`,
          oh.present === expectOh,
          `kỳ vọng present=${expectOh}, thực tế=${oh.present}`
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
