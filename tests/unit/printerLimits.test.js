'use strict';
const { test } = require('node:test');
const assert = require('node:assert');
const { loadPure } = require('./lib/loadPure');
const { printerLimits } = loadPure();

const PS = {
  nozzle_diameter: ['0.4'],
  layer_height: '0.2',
  filament_max_volumetric_speed: ['22'],
  inner_wall_line_width: '0.45',
  sparse_infill_line_width: '0.45',
  internal_solid_infill_line_width: '0.42',
  outer_wall_line_width: '0.42',
  top_surface_line_width: '0.45',
  printer_settings_id: 'Bambu Lab A1 0.4 nozzle',
};

test('trần lưu lượng theo từng vùng', () => {
  const L = printerLimits(PS);
  assert.equal(L.nozzle, 0.4);
  assert.equal(L.maxvol, 22);
  assert.ok(Math.abs(L.vmax.inner_wall - 244.4) < 0.5);
  assert.ok(Math.abs(L.vmax.internal_solid_infill - 261.9) < 0.5);
});

test('sàn/trần layer = giao của máy và quy tắc 25–75% nozzle', () => {
  const L = printerLimits(PS);
  assert.equal(L.layerMin, 0.10);
  assert.equal(L.layerMax, 0.28);
});

test('nozzle 0.2 bị đánh dấu', () => {
  const L = printerLimits({ ...PS, nozzle_diameter: ['0.2'], filament_max_volumetric_speed: ['2'] });
  assert.equal(L.smallNozzle, true);
});
