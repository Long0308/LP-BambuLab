'use strict';
const { test } = require('node:test');
const assert = require('node:assert');
const { loadPure } = require('./lib/loadPure');
const { geoFeatures, printerLimits, optimize, MODES, PATTERNS } = loadPure();
const { box, sphere, frustum, bridge, ledge } = require('./fixtures/meshes');

/* Kế thừa '0.20mm Standard @BBL A1' + Bambu PLA Matte (maxvol 22). */
const PS = {
  nozzle_diameter: ['0.4'], layer_height: '0.2', filament_max_volumetric_speed: ['22'],
  inner_wall_line_width: '0.45', sparse_infill_line_width: '0.45',
  internal_solid_infill_line_width: '0.42', outer_wall_line_width: '0.42', top_surface_line_width: '0.45',
  filament_type: ['PLA'], curr_bed_type: 'Textured PEI Plate',
  top_shell_layers: '5', top_shell_thickness: '1.0',
  bottom_shell_layers: '3', bottom_shell_thickness: '0',
  inner_wall_speed: ['300'], sparse_infill_speed: ['270'], internal_solid_infill_speed: ['250'],
  outer_wall_speed: ['200'], top_surface_speed: ['150'],
  seam_slope_type: 'all', filament_scarf_seam_type: ['all'],
  enable_pressure_advance: ['0'], filament_flow_ratio: ['0.98'],
  elefant_foot_compensation: '0.12', brim_object_gap: '0',
  support_style: 'tree_hybrid', enable_prime_tower: '0',
  override_process_overhang_speed: ['0'],
};
const DECOR = 'Chi tiết trang trí';
const run = (tris, goal = DECOR, mode = 'balanced', ps = PS) =>
  optimize(geoFeatures(tris), printerLimits(ps), 'PLA Matte', goal, ps, mode);

/* ---------- Tầng 0: hiệu chuẩn ---------- */
test('Tầng 0: chưa hiệu chuẩn thì cảnh báo, KHÔNG bịa giá trị K', () => {
  const P = run(box(100, 100, 50));
  assert.ok(P.calibration.some(c => /Flow Dynamics/.test(c.msg)));
  assert.equal(P.deltaFilament.pressure_advance, undefined, 'không được đề xuất giá trị K');
});

/* ---------- Tầng 1: first layer ---------- */
test('Tầng 1: luôn đặt close_fan 3 và initial_layer_speed 25', () => {
  const P = run(box(100, 100, 50));
  assert.equal(P.deltaFilament.close_fan_the_first_x_layers, 3);
  assert.equal(P.deltaProcess.initial_layer_speed, 25);
});

/* ---------- Tầng 2: warping ---------- */
/* wiki Bambu khuyên gyroid cho đế lớn, nhưng cơ chế nó nêu là "Grid/Triangle tạo ứng suất
   theo phương tuyến". adaptivecubic không thuộc họ đó, mà Orca đo được nó rẻ nhất bảng
   (vật liệu 2, thời gian 2) trong khi gyroid đắt nhất (thời gian 8) và bền không hơn. */
test('Tầng 2: đế lớn → brim 8mm + adaptivecubic (KHÔNG gyroid) + bed 65', () => {
  const P = run(box(200, 150, 20));
  assert.equal(P.deltaProcess.brim_type, 'outer_only');
  assert.equal(P.deltaProcess.brim_width, 8);
  assert.equal(P.deltaProcess.sparse_infill_pattern, 'adaptivecubic');
  assert.notEqual(P.deltaProcess.sparse_infill_pattern, 'gyroid', 'gyroid chậm gấp 4 mà bền không hơn');
  assert.ok(P.warnings.some(w => /gyroid/i.test(w.msg)), 'phải nói rõ vì sao lệch khỏi wiki');
  assert.equal(P.deltaFilament.textured_plate_temp, 65);
});

test('Tầng 2 khoá pattern, tầng 5 bị chặn và ghi conflict', () => {
  const P = run(box(200, 150, 20));
  assert.equal(P.deltaProcess.sparse_infill_pattern, 'adaptivecubic');
  assert.ok(P.conflicts.some(c => c.key === 'sparse_infill_pattern' && c.tier === 5));
});

test('Hình cầu: KHÔNG hạ acceleration (aspect 1.0), nhưng CÓ brim vì tiếp xúc bé', () => {
  const P = run(sphere(40));
  assert.equal(P.deltaProcess.default_acceleration, undefined, 'cầu không cao mảnh');
  assert.equal(P.deltaProcess.brim_type, 'outer_only');
});

test('Cột cao mảnh: CÓ hạ acceleration', () => {
  const P = run(box(20, 20, 150));
  assert.ok(P.deltaProcess.default_acceleration < 6000);
});

/* ---------- Tầng 3 + 3b + 4b ---------- */
/* Ở vùng dốc <25°, ngay tại sàn 0.08 bậc thang vẫn còn 0.33mm ⇒ hạ layer là vô ích.
   Tầng 3 phải chữa bằng top shell + monotonic, tuyệt đối không đụng layer_height —
   layer_height chỉ do mode quyết, và bị khoá ở tầng 1. */
test('Tầng 3: chữa bề mặt bằng top shell/monotonic, KHÔNG hạ layer_height', () => {
  const P = run(sphere(40));
  assert.equal(P.deltaProcess.top_surface_pattern, 'monotonicline');
  const lhReasons = P.reasons.filter(r => r.key === 'layer_height');
  assert.equal(lhReasons.length, 1, 'chỉ một nơi được ghi layer_height');
  assert.equal(lhReasons[0].tier, 1, 'và đó là tầng 1 (mode), không phải tầng 3');
  assert.equal(lhReasons[0].src, 'mode');
});

test('Tầng 3b: goal chức năng → wall_loops tăng TRƯỚC, layer <= 0.25', () => {
  const P = run(box(100, 100, 50), 'Công năng cơ khí');
  assert.ok(P.deltaProcess.wall_loops >= 3);
  assert.equal(P.deltaProcess.infill_wall_overlap, '15%');
  assert.ok(P.limits.layerMaxEff <= 0.25);
});

/* Tầng 3b chọn gyroid để CHỊU LỰC. Tầng 5 muốn adaptivecubic để tiết kiệm nhựa.
   `put()` chỉ khoá key ở tầng ≤2 thì tầng 5 sẽ ghi đè và xoá mất lựa chọn chịu lực —
   không golden test nào bắt được vì chúng đều dùng mục tiêu trang trí. */
test('Tầng 5 KHÔNG được ghi đè pattern chịu lực của tầng 3b (đế nhỏ, mục tiêu cơ khí)', () => {
  const P = run(box(60, 60, 40), 'Công năng cơ khí');   // đế 36 cm² → tầng 2 không chạm pattern
  assert.equal(P.deltaProcess.sparse_infill_pattern, 'cubic');
  assert.ok(P.conflicts.some(c => c.key === 'sparse_infill_pattern' && c.tier === 5),
    'phải ghi nhận tầng 5 bị chặn');
});

/* ---------- CHỐT CHẶN THỜI GIAN ----------
   "Tối ưu thì thời gian ít nhất phải bằng file gốc." Mode Chắc cố ý hạ layer, mục tiêu cơ
   khí cố ý đổi thời gian lấy độ bền — hai ca đó được phép. Còn lại: cấm. */
const FILE_10 = { ...PS, sparse_infill_density: '10%', sparse_infill_pattern: 'adaptivecubic',
                  wall_loops: '2', inner_wall_speed: ['300'], sparse_infill_speed: ['270'],
                  internal_solid_infill_speed: ['250'], outer_wall_speed: ['200'], top_surface_speed: ['150'] };
const runF = (tris, goal, mode) =>
  optimize(geoFeatures(tris), printerLimits(FILE_10), 'PLA Matte', goal, FILE_10, mode, 22);

test('Cân bằng/Nhanh: KHÔNG key nào chậm hơn file gốc', () => {
  for (const m of ['balanced', 'fast'])
    for (const tris of [box(200, 150, 20), box(100, 100, 50), sphere(40), bridge(), ledge()])
      for (const goal of ['Thông thường', 'Chi tiết trang trí']) {
        const P = runF(tris, goal, m);
        assert.deepEqual(P.timeGuard, [], `${m}/${goal}: ${JSON.stringify(P.timeGuard)}`);
      }
});

test('Không chịu lực: mật độ KHÔNG được nâng trên mức của file', () => {
  assert.equal(runF(box(100, 100, 50), 'Thông thường', 'balanced').deltaProcess.sparse_infill_density, '10%',
    'file 10%, mode Cân bằng muốn 15% → phải giữ 10%');
  assert.equal(runF(box(100, 100, 50), 'Thông thường', 'quality').deltaProcess.sparse_infill_density, '10%');
  assert.equal(runF(box(100, 100, 50), 'Thông thường', 'fast').deltaProcess.sparse_infill_density, '10%');
});

test('Chịu lực: ĐƯỢC nâng mật độ, và chốt chặn không cản', () => {
  const P = runF(box(100, 100, 50), 'Công năng cơ khí', 'balanced');
  assert.equal(P.deltaProcess.sparse_infill_density, '25%');
  assert.deepEqual(P.timeGuard, [], 'mục tiêu cơ khí được phép chậm hơn');
  assert.ok(P.slower.some(x => x.key === 'sparse_infill_density'), 'nhưng vẫn phải ghi nhận là chậm hơn');
});

test('Mật độ file cao hơn mode → HẠ xuống (nhanh hơn)', () => {
  const ps = { ...FILE_10, sparse_infill_density: '30%' };
  const P = optimize(geoFeatures(box(100, 100, 50)), printerLimits(ps), 'PLA Matte', 'Thông thường', ps, 'fast', 22);
  assert.equal(P.deltaProcess.sparse_infill_density, '10%');
  assert.deepEqual(P.timeGuard, []);
});

/* Tốc độ KHÔNG được so bằng số thô: stock 300 mm/s bị trần ghì còn 244.4, nên 300 → 244
   thật ra không chậm đi. Phải so bằng lưu lượng hữu hiệu. */
test('Chốt chặn không báo oan tốc độ bị trần ghì (300 → 244)', () => {
  const P = runF(box(100, 100, 50), 'Thông thường', 'balanced');
  assert.equal(P.deltaProcess.inner_wall_speed, 244);
  assert.ok(!P.slower.some(x => x.key === 'inner_wall_speed'),
    'file ghi 300 nhưng engine chạy 244.4; ghi 244 không phải chậm đi');
});

test('Nhanh: layer dày hơn → tốc độ trần thấp hơn, nhưng lưu lượng không giảm', () => {
  const P = runF(box(100, 100, 50), 'Thông thường', 'fast');
  assert.equal(P.deltaProcess.layer_height, 0.24);
  assert.equal(P.deltaProcess.inner_wall_speed, 203, 'trần ở 0.24');
  assert.deepEqual(P.timeGuard, [], '203 ở layer 0.24 có lưu lượng ≈ 244 ở layer 0.20');
});

/* ---------- Bảng pattern ---------- */
test('PATTERNS: đủ dữ liệu, gyroid chậm nhất, adaptivecubic rẻ nhất trong nhóm chịu lực khá', () => {
  const by = Object.fromEntries(PATTERNS.map(p => [p.v, p]));
  assert.equal(by.gyroid.time, 8);
  assert.equal(by.gyroid.xy, by.cubic.xy, 'gyroid không bền hơn cubic');
  assert.ok(by.cubic.time < by.gyroid.time);
  assert.equal(by.adaptivecubic.mat, 2);
  assert.equal(by.adaptivecubic.time, 2);
  assert.equal(by['zig-zag'].label, 'Rectilinear', 'Bambu gọi zig-zag là Rectilinear');
  PATTERNS.forEach(p => {
    for (const k of ['v', 'label', 'desc', 'use']) assert.ok(p[k], `${p.v} thiếu ${k}`);
    for (const k of ['xy', 'z', 'mat', 'time']) assert.equal(typeof p[k], 'number', `${p.v}.${k}`);
  });
});

test('PATTERNS: mọi giá trị đều là enum thật của PrintConfig', () => {
  const src = require('fs').readFileSync(require('path').join(__dirname, '..', '..', 'PrintConfig.cpp'), 'utf8');
  const block = /def = this->add\("sparse_infill_pattern"[\s\S]*?set_default_value/.exec(src)[0];
  const valid = new Set([...block.matchAll(/enum_values\.push_back\("([^"]+)"\)/g)].map(m => m[1]));
  assert.ok(valid.size >= 20, `chỉ đọc được ${valid.size} enum — regex hỏng`);
  PATTERNS.forEach(p => assert.ok(valid.has(p.v), `${p.v} không phải enum của Bambu`));
});

test('Tầng 3b KHÔNG bật cho đồ trang trí', () => {
  const P = run(box(100, 100, 50));
  assert.equal(P.deltaProcess.wall_loops, undefined);
});

test('Tầng 4b: mặt trên lớn + infill thưa → cảnh báo võng', () => {
  const P = run(box(200, 150, 20), DECOR, 'fast');
  assert.ok(P.warnings.some(w => /võng/i.test(w.msg)), JSON.stringify(P.warnings));
});

/* ---------- wall_sequence ----------
   PrintConfig.cpp:2045-2050 — giá trị THẬT là chuỗi "inner wall/outer wall", còn
   "inner/outer" chỉ là NHÃN hiển thị. Ghi nhãn thì Studio bỏ qua im lặng.
   wiki Bambu (quality-advance-settings): "If orders of outer/inner or inner/outer/inner
   are used, the outer wall is completely overhanging with no adhesion on both sides,
   resulting in poor overhang quality." ⇒ có overhang thì phải để inner/outer. */
test('wall_sequence: có overhang → inner wall/outer wall', () => {
  assert.equal(run(sphere(40)).deltaProcess.wall_sequence, 'inner wall/outer wall');
  assert.equal(run(bridge()).deltaProcess.wall_sequence, 'inner wall/outer wall');
});

test('wall_sequence: ít overhang + ≥3 thành → inner wall/outer wall/inner wall', () => {
  const P = run(box(100, 100, 50), 'Công năng cơ khí');   // tầng 3b đặt wall_loops = 3
  assert.equal(P.deltaProcess.wall_loops, 3);
  assert.equal(P.deltaProcess.wall_sequence, 'inner wall/outer wall/inner wall');
});

test('wall_sequence: ít overhang + 2 thành → outer wall/inner wall', () => {
  const P = run(box(100, 100, 50));   // trang trí, wall_loops kế thừa = 2
  assert.equal(P.deltaProcess.wall_loops, undefined);
  assert.equal(P.deltaProcess.wall_sequence, 'outer wall/inner wall');
});

test('wall_sequence: không mesh → không đoán', () => {
  const P = optimize(null, printerLimits(PS), 'PLA Matte', DECOR, PS, 'balanced', 22);
  assert.equal(P.deltaProcess.wall_sequence, undefined);
  assert.ok(P.skipped.some(s => /thứ tự thành|wall_sequence/i.test(s)), P.skipped.join(' · '));
});

test('wall_sequence: chỉ dùng 3 chuỗi hợp lệ của PrintConfig', () => {
  const ok = new Set(['inner wall/outer wall', 'outer wall/inner wall', 'inner wall/outer wall/inner wall']);
  for (const tris of [box(100, 100, 50), sphere(40), bridge(), ledge()])
    for (const goal of ['Thông thường', 'Chi tiết trang trí', 'Công năng cơ khí']) {
      const v = run(tris, goal).deltaProcess.wall_sequence;
      assert.ok(ok.has(v), `giá trị lạ: ${JSON.stringify(v)}`);
    }
});

/* ---------- Tầng 4: support / bridge / VLH ---------- */
test('Support: 3 khoảng rạch ròi, không có vùng xám', () => {
  assert.equal(run(box(100, 100, 50)).deltaProcess.enable_support, 0, 'overhang 0% → tắt');
  const P2 = run(sphere(40));
  assert.equal(P2.deltaProcess.enable_support, 1);
  assert.equal(P2.deltaProcess.support_type, 'tree(auto)', 'overhang 14% > 8% → auto');
});

/* Dải GIỮA (overhang 2–8%). `tree(manual)` KHÔNG sinh support nào nếu chưa sơn enforcer —
   ghi nó vào preset là cái bẫy: ai áp preset mà không đọc cảnh báo sẽ in ra vật gãy.
   Lý do của chính luật nói "ít overhang + đồ trang trí", nên nó chỉ được phép chạy khi
   mục tiêu ĐÚNG LÀ trang trí. Với mọi mục tiêu khác: bật support, để support_type kế thừa. */
test('Dải giữa + mục tiêu trang trí → tree(manual) + cảnh báo', () => {
  const P = run(ledge(), 'Chi tiết trang trí');
  assert.equal(P.deltaProcess.enable_support, 1);
  assert.equal(P.deltaProcess.support_type, 'tree(manual)');
  assert.ok(P.warnings.some(w => /enforcer/i.test(w.msg)));
});

test('Dải giữa + mục tiêu KHÁC → không được ghi tree(manual)', () => {
  for (const goal of ['Thông thường', 'Công năng cơ khí']) {
    const P = run(ledge(), goal);
    assert.equal(P.deltaProcess.enable_support, 1, goal + ': vẫn phải bật support');
    assert.equal(P.deltaProcess.support_type, undefined,
      goal + ": không được ghi tree(manual) — nó KHÔNG sinh support nếu chưa sơn enforcer");
  }
});

test('Dải giữa: fixture đúng nằm trong 2–8%', () => {
  const F = geoFeatures(ledge());
  assert.ok(F.down > 2 && F.down <= 8, `down=${F.down}`);
});

test('Bridge: bật enable_overhang_speed + overhang_fan_speed', () => {
  const P = run(bridge());
  assert.equal(P.deltaProcess.enable_overhang_speed, 1);
  assert.equal(P.deltaFilament.overhang_fan_speed, 100);
});

test('VLH: vase có nhiều mặt dốc → sinh ranges + gỡ blocker', () => {
  const P = run(frustum(40, 55, 150));
  assert.ok(P.vlhRanges.length > 0);
  assert.equal(P.deltaProcess.support_style, 'tree_hybrid');
  assert.equal(P.deltaProcess.enable_prime_tower, 0);
});

test('VLH: mọi layer nằm trong [layerMin, layerMaxEff]', () => {
  const P = run(sphere(40));
  for (const r of P.vlhRanges) {
    assert.ok(r.layer >= P.limits.layerMin - 1e-9, `layer ${r.layer} < min`);
    assert.ok(r.layer <= P.limits.layerMaxEff + 1e-9, `layer ${r.layer} > max`);
    assert.ok(r.z1 > r.z0);
  }
});

/* ---------- Tầng 5: tốc độ vùng khuất = floor(trần) ----------
   Đo preset stock trên máy (2026-07-10, đã giải chuỗi inherits):
     0.16mm Optimal : inner 300 < trần 305.6 · internal_solid 300 < trần 327.4  (bỏ lỡ 9.1%)
     0.20mm Standard: inner 300 > trần 244.4 · internal_solid 250 < trần 261.9  (bỏ lỡ 4.8%)
     0.24mm Draft   : cả ba đều TRÊN trần → engine đã ghì về v_max
   Ghi đúng floor(trần): flow = lh × w × floor(cap) ≤ maxvol nên I1 không bao giờ bắn;
   tệ nhất kém bản kế thừa 0.4%, tốt nhất hơn 9.1%. Và số trong preset = số chạy thật.
   TUYỆT ĐỐI không đụng outer_wall (bề mặt) và top_surface (tầng 3 đã đặt). */
test('Tầng 5: ba vùng khuất = floor(trần), không đụng outer_wall', () => {
  const P = run(box(100, 100, 50));           // balanced, layer 0.20, maxvol 22
  assert.equal(P.deltaProcess.inner_wall_speed, 244, '22/(0.20×0.45)=244.4');
  assert.equal(P.deltaProcess.sparse_infill_speed, 244);
  assert.equal(P.deltaProcess.internal_solid_infill_speed, 261, '22/(0.20×0.42)=261.9');
  assert.equal(P.deltaProcess.outer_wall_speed, undefined, 'cấm chạm outer wall');
  assert.ok(!P.reasons.some(r => r.tier === 5 && /^(outer_wall|top_surface)_speed$/.test(r.key)),
    'tầng 5 không được đụng hai vùng lộ bề mặt');
  assert.deepEqual(P.violations, [], 'floor(trần) không bao giờ vượt trần');
});

test('top_surface_speed do tầng 3 đặt, chỉ khi vật có mặt dốc', () => {
  assert.equal(run(sphere(40)).deltaProcess.top_surface_speed, 150);
  assert.equal(run(box(100, 100, 50)).deltaProcess.top_surface_speed, undefined, 'hộp không có mặt dốc');
});

test('Tầng 5: trần đổi theo layer height của mode', () => {
  assert.equal(run(box(100, 100, 50), DECOR, 'quality').deltaProcess.inner_wall_speed, 305, 'layer 0.16');
  assert.equal(run(box(100, 100, 50), DECOR, 'fast').deltaProcess.inner_wall_speed, 203, 'layer 0.24');
});

test('Tầng 5: nozzle 0.2 maxvol 2 → tốc độ bé xíu nhưng vẫn hợp lệ, không âm', () => {
  const ps = { ...PS, nozzle_diameter: ['0.2'], filament_max_volumetric_speed: ['2'],
               inner_wall_line_width: '0.25', sparse_infill_line_width: '0.25',
               internal_solid_infill_line_width: '0.25', outer_wall_line_width: '0.25', top_surface_line_width: '0.25' };
  const P = optimize(geoFeatures(box(20, 20, 20)), printerLimits(ps), 'PLA Matte', DECOR, ps, 'balanced');
  assert.ok(P.deltaProcess.inner_wall_speed > 0);
  assert.deepEqual(P.violations, []);
});

test('Tầng 5: tắt prime tower khi không cần VLH', () => {
  assert.equal(run(box(100, 100, 50)).deltaProcess.enable_prime_tower, 0);
});

/* ---------- 3 mode ---------- */
test('3 mode có layer height tăng dần, đều trong [layerMin, layerMax]', () => {
  const L = printerLimits(PS);
  const lh = ['quality', 'balanced', 'fast'].map(m => run(box(100, 100, 50), DECOR, m).deltaProcess.layer_height);
  assert.deepEqual(lh, [0.16, 0.20, 0.24]);
  lh.forEach(x => { assert.ok(x >= L.layerMin && x <= L.layerMax, `${x} ngoài [${L.layerMin},${L.layerMax}]`); });
});

test('mode đổi layer → top_shell_layers phải đủ dày (I2 không được vỡ)', () => {
  for (const [m, want] of [['quality', 7], ['balanced', 5], ['fast', 5]]) {
    const P = run(box(100, 100, 50), DECOR, m);
    assert.equal(P.deltaProcess.top_shell_layers, want, `mode ${m}: ceil(1.0/${P.deltaProcess.layer_height})`);
  }
});

test('mode nhanh: infill thưa nhất, mode chắc: dày nhất', () => {
  const d = m => run(box(100, 100, 50), DECOR, m).deltaProcess.sparse_infill_density;
  assert.equal(d('fast'), '10%');
  assert.equal(d('quality'), '20%');
});

test('MODES lộ ra tên tiếng Việt để UI dùng', () => {
  assert.deepEqual(Object.keys(MODES), ['quality', 'balanced', 'fast']);
  assert.equal(MODES.balanced.name, 'Cân bằng');
});

/* ---------- Không có mesh (.gcode.3mf) ----------
   Bambu tước mesh khỏi bản đã slice: `.gcode.3mf` chỉ còn 3D/3dmodel.model rỗng, phần
   3D/Objects/*.model bị bỏ. Nhưng project_settings.config thì vẫn đủ. Optimizer KHÔNG
   cần thời gian in, chỉ cần hình học + config — nên thiếu mesh thì vẫn ra được mọi
   quyết định thuần-config, và phải NÓI RÕ cái gì bị bỏ thay vì im lặng. */
const noGeo = (mode = 'balanced', goal = DECOR) =>
  optimize(null, printerLimits(PS), 'PLA Matte', goal, PS, mode, 22);

test('không mesh: vẫn ra quyết định thuần-config', () => {
  const P = noGeo();
  assert.equal(P.deltaProcess.layer_height, 0.2);
  assert.equal(P.deltaProcess.inner_wall_speed, 244, 'trần lưu lượng không cần mesh');
  assert.equal(P.deltaProcess.internal_solid_infill_speed, 261);
  assert.equal(P.deltaProcess.top_shell_layers, 5, 'ceil(1.0/0.20) — không cần mesh');
  assert.equal(P.deltaProcess.wall_generator, 'arachne');
  assert.equal(P.deltaProcess.enable_prime_tower, 0);
  assert.equal(P.deltaProcess.seam_slope_type, 'all');
  assert.equal(P.deltaFilament.filament_scarf_seam_type, 'all');
  assert.equal(P.deltaFilament.close_fan_the_first_x_layers, 3);
  assert.deepEqual(P.violations, [], JSON.stringify(P.violations));
});

test('không mesh: TUYỆT ĐỐI không đoán quyết định cần hình học', () => {
  const P = noGeo();
  for (const k of ['brim_type', 'brim_width', 'enable_support', 'support_type',
                   'default_acceleration', 'enable_overhang_speed', 'ironing_type',
                   'top_surface_pattern', 'sparse_infill_pattern'])
    assert.equal(P.deltaProcess[k], undefined, k + ' cần mesh, không được đoán');
  assert.equal(P.deltaFilament.textured_plate_temp, undefined, 'bed 65 phụ thuộc diện tích đế');
  assert.equal(P.deltaFilament.overhang_fan_speed, undefined);
  assert.equal(P.vlhRanges.length, 0);
});

test('không mesh: liệt kê đúng những gì bị bỏ', () => {
  const P = noGeo();
  const s = P.skipped.join(' · ');
  assert.ok(P.skipped.length >= 4, s);
  for (const t of [/brim|cong vênh/i, /support/i, /overhang|bridge/i, /Variable layer height|VLH/i])
    assert.ok(t.test(s), 'thiếu mục bị bỏ: ' + t + ' trong "' + s + '"');
});

test('có mesh: skipped rỗng', () => {
  assert.deepEqual(run(box(200, 150, 20)).skipped, []);
});

test('không mesh: infill theo mode vẫn đặt (mật độ không cần hình học)', () => {
  assert.equal(noGeo('fast').deltaProcess.sparse_infill_density, '10%');
  assert.equal(noGeo('quality').deltaProcess.sparse_infill_density, '20%');
});

test('không mesh + goal cơ khí: tầng 3b vẫn chạy (không cần hình học)', () => {
  const P = noGeo('balanced', 'Công năng cơ khí');
  assert.ok(P.deltaProcess.wall_loops >= 3);
  assert.equal(P.deltaProcess.infill_wall_overlap, '15%');
  assert.equal(P.deltaProcess.sparse_infill_pattern, 'cubic', 'tầng 3b chọn pattern chịu lực, không cần hình học');
});

/* ---------- Nhựa đích khác nhựa trong file ---------- */
/* File 'Body 14 - LP.3mf' gán object vào slot 1 = PLA Lite (maxvol 16), nhưng preset
   xuất ra inherits 'Bambu PLA Matte @BBL A1' (maxvol 22). Trần lưu lượng phải tính theo
   nhựa ĐÍCH, nếu không tốc độ ghi ra chậm hơn thực tế 23%. */
test('maxvol đích ghi đè maxvol trong file', () => {
  const lite = { ...PS, filament_max_volumetric_speed: ['16'] };
  const P = optimize(geoFeatures(box(100, 100, 50)), printerLimits(lite), 'PLA Matte', DECOR, lite, 'balanced', 22);
  assert.equal(P.limits.maxvol, 22);
  assert.equal(P.deltaProcess.inner_wall_speed, 244, '22/(0.20×0.45)=244.4 — không phải 177 của PLA Lite');
});

test('không truyền maxvol đích → dùng của file', () => {
  const lite = { ...PS, filament_max_volumetric_speed: ['16'] };
  const P = optimize(geoFeatures(box(100, 100, 50)), printerLimits(lite), 'PLA Lite', DECOR, lite, 'balanced');
  assert.equal(P.deltaProcess.inner_wall_speed, 177, '16/(0.20×0.45)=177.8');
});

/* ---------- Số sạch, không rác dấu phẩy động ---------- */
test('mọi số ghi ra đều sạch, không có 0.24000000000000002', () => {
  for (const m of ['quality', 'balanced', 'fast']) {
    const P = run(box(100, 100, 50), DECOR, m);
    for (const bag of [P.deltaProcess, P.deltaFilament])
      for (const k in bag) {
        const v = bag[k];
        if (typeof v !== 'number') continue;
        assert.equal(String(v), String(+v.toFixed(3)), `${m}/${k} = ${v} có rác float`);
      }
  }
});

/* ---------- Scarf seam: giữ ý định của file ---------- */
/* Stock '0.20mm Standard @BBL A1' có seam_slope_type = 'none'. Preset xuất ra kế thừa nó,
   nên nếu file bật scarf mà ta không mang theo thì scarf bị tắt âm thầm. */
test('file bật scarf → preset mang theo cả process lẫn filament', () => {
  const ps = { ...PS, seam_slope_type: 'all', filament_scarf_seam_type: ['none'] };
  const P = optimize(geoFeatures(box(100, 100, 50)), printerLimits(ps), 'PLA Matte', DECOR, ps, 'balanced');
  assert.equal(P.deltaProcess.seam_slope_type, 'all', 'phải ghi rõ, kẻo kế thừa stock = none');
  assert.equal(P.deltaFilament.filament_scarf_seam_type, 'all', 'filament luôn đè process');
  assert.deepEqual(P.violations, []);
});

test('file tắt scarf → không đụng vào', () => {
  const ps = { ...PS, seam_slope_type: 'none', filament_scarf_seam_type: ['none'] };
  const P = optimize(geoFeatures(box(100, 100, 50)), printerLimits(ps), 'PLA Matte', DECOR, ps, 'balanced');
  assert.equal(P.deltaProcess.seam_slope_type, undefined);
  assert.equal(P.deltaFilament.filament_scarf_seam_type, undefined);
});

/* ---------- I7 không được tự bật cổng ---------- */
/* File thật có filament_bridge_speed=25 vs bridge_speed=50, override=0. Bật cổng sẽ đổi
   bridge từ 50 xuống 25 — đổi hành vi âm thầm. Optimizer không sở hữu key đó ⇒ không đụng. */
test('Fixpoint KHÔNG tự bật override_process_overhang_speed cho key nó không sở hữu', () => {
  const ps = { ...PS, filament_bridge_speed: ['25'], bridge_speed: ['50'] };
  const P = optimize(geoFeatures(box(100, 100, 50)), printerLimits(ps), 'PLA Matte', DECOR, ps, 'balanced');
  assert.equal(P.deltaFilament.override_process_overhang_speed, undefined);
  assert.equal(P.deltaFilament.filament_enable_overhang_speed, undefined);
  assert.deepEqual(P.violations, [], 'I7 phải bị `owned` lọc, không được kẹt lại');
});

test('Fixpoint: I6 được sửa — brim_object_gap về 0', () => {
  const ps = { ...PS, brim_object_gap: '0.1' };
  const P = optimize(geoFeatures(box(200, 150, 20)), printerLimits(ps), 'PLA Matte', DECOR, ps, 'balanced');
  assert.equal(P.deltaProcess.brim_object_gap, 0);
});

test('Fixpoint: I1 sửa bằng cách XOÁ key, không hạ xuống số chậm hơn', () => {
  /* ép tầng 5 giả lập ghi tốc độ vượt trần bằng cách chọn mode fast (layer 0.24 → trần thấp) */
  const ps = { ...PS, top_shell_thickness: '1.0' };
  const P = optimize(geoFeatures(box(100, 100, 50)), printerLimits(ps), 'PLA Matte', DECOR, ps, 'fast');
  assert.deepEqual(P.violations, [], JSON.stringify(P.violations));
});

test('Không còn bất biến nào vỡ sau fixpoint, ở cả 3 mode', () => {
  for (const m of ['quality', 'balanced', 'fast'])
    for (const tris of [box(200, 150, 20), sphere(40), frustum(40, 55, 150), bridge()]) {
      const P = run(tris, DECOR, m);
      assert.deepEqual(P.violations, [], `mode ${m}: ${JSON.stringify(P.violations)}`);
    }
});
