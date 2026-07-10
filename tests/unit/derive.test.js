'use strict';
const { test } = require('node:test');
const assert = require('node:assert');
const { loadPure } = require('./lib/loadPure');
const { printerLimits, derive, checkInvariants } = loadPure();

const BASE = {
  nozzle_diameter: ['0.4'], layer_height: '0.2', filament_max_volumetric_speed: ['22'],
  inner_wall_line_width: '0.45', sparse_infill_line_width: '0.45',
  internal_solid_infill_line_width: '0.42', outer_wall_line_width: '0.42', top_surface_line_width: '0.45',
  inner_wall_speed: ['240'], sparse_infill_speed: ['240'], internal_solid_infill_speed: ['255'],
  outer_wall_speed: ['200'], top_surface_speed: ['150'],
  top_shell_layers: '5', top_shell_thickness: '1.0',
  bottom_shell_layers: '3', bottom_shell_thickness: '0',
  seam_slope_type: 'all', filament_scarf_seam_type: ['all'],
  support_style: 'tree_hybrid', enable_prime_tower: '0',
  elefant_foot_compensation: '0.12', brim_object_gap: '0',
  override_process_overhang_speed: ['0'],
};

const ids = ps => checkInvariants(ps, printerLimits(ps), derive(ps, printerLimits(ps))).map(x => x.id);

test('I1: tốc độ vượt trần bị bắt', () => {
  const ps = { ...BASE, layer_height: '0.24' };
  const L = printerLimits(ps);
  const v = checkInvariants(ps, L, derive(ps, L));
  assert.ok(v.some(x => x.id === 'I1'), 'phải bắt I1 ở layer 0.24 với 240/255');
});

test('I1: không báo oan ở layer 0.20', () => {
  const L = printerLimits(BASE);
  const v = checkInvariants(BASE, L, derive(BASE, L));
  assert.ok(!v.some(x => x.id === 'I1'));
});

test('I2: top_shell_layers=4 @0.20 với thickness 1.0 → engine tự tăng', () => {
  const ps = { ...BASE, top_shell_layers: '4' };
  const L = printerLimits(ps);
  const d = derive(ps, L);
  assert.equal(d.effTopLayers, 5);
  const v = checkInvariants(ps, L, d);
  assert.ok(v.some(x => x.id === 'I2'));
});

test('I3: layer ngoài [layerMin, layerMax] bị kẹp', () => {
  assert.ok(ids({ ...BASE, layer_height: '0.32' }).includes('I3'), 'trên trần 0.28');
  assert.ok(ids({ ...BASE, layer_height: '0.06' }).includes('I3'), 'dưới sàn 0.10');
});

test('I4: filament tắt scarf bị bắt', () => {
  const ps = { ...BASE, filament_scarf_seam_type: ['none'] };
  const L = printerLimits(ps);
  const v = checkInvariants(ps, L, derive(ps, L));
  assert.ok(v.some(x => x.id === 'I4'));
});

test('I5: VLH + organic + prime tower bị bắt', () => {
  const ps = { ...BASE, support_style: 'default', support_type: 'tree(auto)', enable_prime_tower: '1' };
  const L = printerLimits(ps);
  const d = derive(ps, L);
  const v = checkInvariants(ps, L, d, /* vlhWanted */ true);
  assert.ok(v.some(x => x.id === 'I5'));
});

test('I6: elephant foot > 0 mà brim_object_gap > 0', () => {
  const ps = { ...BASE, brim_object_gap: '0.1' };
  const L = printerLimits(ps);
  const v = checkInvariants(ps, L, derive(ps, L));
  assert.ok(v.some(x => x.id === 'I6'));
});

/* Tab.cpp:4256 — override_process_overhang_speed gác đúng 6 key filament:
   filament_enable_overhang_speed, filament_bridge_speed, filament_overhang_{1..4}_4_speed,
   filament_overhang_totally_speed. Không gác overhang_fan_speed (đó là quạt). */
test('I7: đặt filament_bridge_speed mà override tắt → giá trị bị bỏ qua', () => {
  assert.ok(ids({ ...BASE, filament_bridge_speed: ['50'] }).includes('I7'));
  assert.ok(ids({ ...BASE, filament_overhang_totally_speed: ['10'] }).includes('I7'));
});

test('I7: bật override thì không báo', () => {
  const ps = { ...BASE, filament_bridge_speed: ['50'], override_process_overhang_speed: ['1'] };
  assert.ok(!ids(ps).includes('I7'));
});

test('I7: overhang_fan_speed KHÔNG bị gác (là quạt, không phải tốc độ)', () => {
  assert.ok(!ids({ ...BASE, overhang_fan_speed: ['100'] }).includes('I7'),
    'tầng 4 đặt overhang_fan_speed; nếu I7 bắt nhầm thì golden test sẽ đỏ oan');
});

test('BASE sạch: không vi phạm gì (trừ khi bật VLH)', () => {
  const L = printerLimits(BASE);
  const v = checkInvariants(BASE, L, derive(BASE, L));
  assert.deepEqual(v.map(x => x.id), []);
});
