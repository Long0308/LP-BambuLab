'use strict';
/* Báo cáo: với MỖI .3mf → cấu hình chính + toàn bộ finding của hub.
   Dùng để soi bằng mắt xem hub có phán đúng không. Không phải test (không assert). */
const fs = require('fs');
const path = require('path');
const { launch, openHub, analyze, close } = require('./lib/hub');

const DIR = 'C:\\Users\\philong.pham\\Downloads\\';
const files = fs.readdirSync(DIR).filter(f => f.toLowerCase().endsWith('.3mf')).map(f => DIR + f);
const EXTRA = path.join(__dirname, 'fixtures', 'scarf-trap.3mf');
if (fs.existsSync(EXTRA)) files.push(EXTRA);

const CFG_KEYS = [
  'printer_settings_id', 'nozzle_diameter', 'filament_settings_id', 'filament_max_volumetric_speed',
  'layer_height', 'wall_loops', 'wall_sequence', 'sparse_infill_pattern', 'sparse_infill_density',
  'top_shell_layers', 'top_shell_thickness',
  'enable_support', 'support_type', 'support_style', 'support_on_build_plate_only',
  'seam_slope_type', 'filament_scarf_seam_type', 'enable_prime_tower', 'brim_type',
  'outer_wall_speed', 'inner_wall_speed', 'sparse_infill_speed', 'internal_solid_infill_speed',
  'inner_wall_line_width', 'internal_solid_infill_line_width',
];

(async () => {
  const b = await launch();
  let totalErr = 0;

  for (const f of files) {
    const { page, errors } = await openHub(b);
    await page.select('#mat', 'PLA Matte').catch(() => {});
    await page.select('#uc', 'Chi tiết trang trí').catch(() => {});
    let ok = true;
    try { await analyze(page, f); } catch (e) { ok = false; }

    const name = path.basename(f);
    console.log('\n' + '='.repeat(96));
    console.log(name);
    console.log('='.repeat(96));

    if (!ok) { console.log('  ⏱ TIMEOUT / không phân tích được'); await page.close(); continue; }

    const data = await page.evaluate(async (keys) => {
      const file = document.querySelector('#file').files[0];
      const zip = await unzip(await file.arrayBuffer());
      let ps = null;
      for (const k in zip) if (k.toLowerCase().endsWith('project_settings.config')) { ps = JSON.parse(new TextDecoder().decode(zip[k])); break; }
      const g = k => { const v = ps ? ps[k] : undefined; return Array.isArray(v) ? v[0] : v; };
      const cfg = {}; keys.forEach(k => cfg[k] = g(k));
      const finds = [...document.querySelectorAll('#result .find')].map(x => ({
        lv: x.querySelector('.badge') ? x.querySelector('.badge').innerText.trim() : '?',
        t: x.querySelector('b').innerText.trim(),
      }));
      const stats = [...document.querySelectorAll('#result .stat')].map(s => s.innerText.replace(/\s+/g, ' ').trim());
      const geo = (typeof lastAnalysis !== 'undefined' && lastAnalysis) ? lastAnalysis.geo : null;
      return { cfg, finds, stats, geo: geo && { down: geo.down, down_cm2: geo.down_cm2, base: geo.base, top: geo.top, vert: geo.vert, dx: geo.dx, dy: geo.dy, dz: geo.dz, tris: geo.tris } };
    }, CFG_KEYS);

    if (data.geo) {
      const g = data.geo;
      console.log(`  hình học: ${g.dx.toFixed(0)}×${g.dy.toFixed(0)}×${g.dz.toFixed(0)} mm · ${g.tris} tam giác`);
      console.log(`            overhang THẬT ${g.down.toFixed(2)}% (${g.down_cm2.toFixed(1)} cm²) · đáy ${g.base.toFixed(1)}% · mặt trên ${g.top.toFixed(1)}% · thành đứng ${g.vert.toFixed(1)}%`);
    }
    console.log('  ' + data.stats.join('   |   '));

    console.log('\n  ── CẤU HÌNH ──');
    for (const k of CFG_KEYS) {
      const v = data.cfg[k];
      if (v === undefined || v === null) continue;
      console.log(`     ${k.padEnd(34)} = ${v}`);
    }

    // trần lưu lượng
    const c = data.cfg;
    const lh = parseFloat(c.layer_height), mv = parseFloat(c.filament_max_volumetric_speed);
    if (lh && mv) {
      console.log('\n  ── TRẦN LƯU LƯỢNG ──');
      for (const [n, wk, sk] of [['inner_wall', 'inner_wall_line_width', 'inner_wall_speed'],
                                 ['internal_solid', 'internal_solid_infill_line_width', 'internal_solid_infill_speed']]) {
        const w = parseFloat(c[wk]), s = parseFloat(c[sk]);
        if (!w || !s) continue;
        const vmax = mv / (lh * w);
        console.log(`     ${n.padEnd(16)} speed=${s.toFixed(0).padStart(4)}  v_max=${vmax.toFixed(0).padStart(4)}  ${s > vmax + 1 ? '⚠ VƯỢT TRẦN' : 'ok'}`);
      }
    }
    // bất biến I2
    const tl = parseInt(c.top_shell_layers, 10), tt = parseFloat(c.top_shell_thickness);
    if (tl && tt > 0 && lh) {
      const eff = Math.max(tl, Math.ceil(tt / lh));
      if (eff > tl) console.log(`\n  ⚠ I2: top_shell_layers=${tl} × ${lh} = ${(tl * lh).toFixed(2)}mm < ${tt}mm ⇒ engine tự nâng lên ${eff} lớp`);
    }

    console.log('\n  ── HUB PHÁN (' + data.finds.length + ' finding) ──');
    const order = { 'LỖI': 0, 'CẢNH BÁO': 1, 'THÔNG TIN': 2, 'OK': 3 };
    data.finds.sort((a, b2) => (order[a.lv] ?? 9) - (order[b2.lv] ?? 9));
    data.finds.forEach(x => console.log(`     [${x.lv.padEnd(9)}] ${x.t}`));

    if (errors.length) { totalErr += errors.length; console.log('\n  ✗ PAGEERROR: ' + errors[0]); }
    await page.close();
  }

  await close(b);
  console.log('\n' + '='.repeat(96));
  console.log(`${files.length} file · pageerror tổng: ${totalErr}`);
})();
