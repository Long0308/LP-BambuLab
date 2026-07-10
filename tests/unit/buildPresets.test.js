'use strict';
const { test } = require('node:test');
const assert = require('node:assert');
const { loadPure } = require('./lib/loadPure');
const { geoFeatures, printerLimits, optimize, buildPresets, MODES } = loadPure();
const { box } = require('./fixtures/meshes');

const PS = {
  nozzle_diameter: ['0.4'], layer_height: '0.2', filament_max_volumetric_speed: ['16'],
  inner_wall_line_width: '0.45', sparse_infill_line_width: '0.45',
  internal_solid_infill_line_width: '0.42', outer_wall_line_width: '0.42', top_surface_line_width: '0.45',
  filament_type: ['PLA'], top_shell_layers: '5', top_shell_thickness: '1.0',
  seam_slope_type: 'all', filament_scarf_seam_type: ['none'],
  enable_pressure_advance: ['1'], elefant_foot_compensation: '0.12', brim_object_gap: '0.1',
  support_style: 'default', enable_prime_tower: '1', override_process_overhang_speed: ['0'],
};
const plans = () => Object.keys(MODES).map(m =>
  optimize(geoFeatures(box(200, 150, 20)), printerLimits(PS), 'PLA Matte', 'Chi tiết trang trí', PS, m, 22));

test('mỗi mode ra 1 cặp process + filament, tên khớp nhau', () => {
  const out = buildPresets(plans(), 'PLA Matte');
  assert.equal(out.length, 3);
  const b = out.find(x => x.mode === 'balanced');
  assert.equal(b.name, 'AUTO-balanced-0.20mm');
  assert.equal(b.process.name, b.name);
  assert.equal(b.process.print_settings_id, b.name);
  assert.deepEqual(b.filament.filament_settings_id, [b.name]);
});

/* Tên preset stock đọc từ %APPDATA%\BambuStudio\system\BBL\, sai một chữ là Studio từ chối. */
test('inherits trỏ đúng preset stock theo layer height', () => {
  const out = buildPresets(plans(), 'PLA Matte');
  assert.equal(out.find(x => x.mode === 'quality').process.inherits, '0.16mm Optimal @BBL A1');
  assert.equal(out.find(x => x.mode === 'balanced').process.inherits, '0.20mm Standard @BBL A1');
  assert.equal(out.find(x => x.mode === 'fast').process.inherits, '0.24mm Draft @BBL A1');
  out.forEach(x => assert.equal(x.filament.inherits, 'Bambu PLA Matte @BBL A1'));
});

/* coFloats/coInts/coBools per-extruder phải là MẢNG; còn lại vô hướng. Kiểu lấy từ
   preset stock đã giải chuỗi inherits, không đoán. Sai kiểu → Studio từ chối import. */
test('kiểu MẢNG vs vô hướng đúng như preset stock', () => {
  const b = buildPresets(plans(), 'PLA Matte').find(x => x.mode === 'balanced');
  assert.deepEqual(b.process.inner_wall_speed, ['244']);
  assert.deepEqual(b.process.initial_layer_speed, ['25']);
  assert.equal(b.process.layer_height, '0.2');
  assert.equal(b.process.top_shell_layers, '5');
  assert.equal(b.process.brim_type, 'outer_only');
  assert.deepEqual(b.filament.close_fan_the_first_x_layers, ['3']);
  assert.deepEqual(b.filament.filament_scarf_seam_type, ['all']);
  assert.deepEqual(b.filament.textured_plate_temp, ['65']);
});

test('phong bì đủ key Bambu đòi', () => {
  const b = buildPresets(plans(), 'PLA Matte').find(x => x.mode === 'balanced');
  for (const k of ['from', 'version', 'name', 'inherits', 'print_settings_id', 'print_extruder_id', 'print_extruder_variant'])
    assert.ok(k in b.process, 'process thiếu ' + k);
  for (const k of ['from', 'version', 'name', 'inherits', 'filament_settings_id', 'filament_extruder_variant'])
    assert.ok(k in b.filament, 'filament thiếu ' + k);
});

test('không có giá trị rác: undefined, NaN, hay rác float', () => {
  for (const x of buildPresets(plans(), 'PLA Matte'))
    for (const o of [x.process, x.filament])
      for (const k in o) {
        const vals = Array.isArray(o[k]) ? o[k] : [o[k]];
        vals.forEach(v => {
          assert.ok(typeof v === 'string', `${k} phải là chuỗi, đang là ${typeof v}`);
          assert.ok(!/undefined|NaN|e-\d/.test(v), `${k} = "${v}" là rác`);
          assert.ok(!/\d\.\d{5,}/.test(v), `${k} = "${v}" có rác float`);
        });
      }
});

/* Nozzle 0.2 cho layer 0.14 — không có preset stock A1 0.4 nào để kế thừa. Phải ném
   lỗi rõ ràng, tuyệt đối không âm thầm rơi về '0.20mm Standard'. */
test('layer không có preset stock → ném lỗi, không đoán bừa', () => {
  const ps = { ...PS, nozzle_diameter: ['0.2'], filament_max_volumetric_speed: ['2'] };
  const p = [optimize(geoFeatures(box(20, 20, 20)), printerLimits(ps), 'PLA Matte', 'Chi tiết trang trí', ps, 'balanced', 2)];
  assert.throws(() => buildPresets(p, 'PLA Matte'), /0\.14|không có preset stock/i);
});
