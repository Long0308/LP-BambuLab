'use strict';
const { test } = require('node:test');
const assert = require('node:assert');
const { loadPure } = require('./lib/loadPure');
const { ARCHETYPES } = require('./fixtures/meshes');
const { geoFeatures, printerLimits, optimize } = loadPure();

const PS = {
  nozzle_diameter: ['0.4'], layer_height: '0.2', filament_max_volumetric_speed: ['22'],
  inner_wall_line_width: '0.45', sparse_infill_line_width: '0.45',
  internal_solid_infill_line_width: '0.42', outer_wall_line_width: '0.42', top_surface_line_width: '0.45',
  filament_type: ['PLA'], top_shell_layers: '5', top_shell_thickness: '1.0',
  seam_slope_type: 'all', filament_scarf_seam_type: ['all'],
  enable_pressure_advance: ['1'], filament_flow_ratio: ['0.98'],
  elefant_foot_compensation: '0.12', brim_object_gap: '0',
  support_style: 'tree_hybrid', enable_prime_tower: '0',
  override_process_overhang_speed: ['0'],
};

/* Kỳ vọng chốt từ spec §9. Đổi luật mà bảng này đổi ⇒ phải giải trình trong PR.
 *
 * GIẢI TRÌNH 2026-07-10 — `hop-lon-phang`: gyroid → adaptivecubic.
 * wiki Bambu khuyên gyroid cho vật đế lớn phẳng, nhưng CƠ CHẾ nó nêu là "Grid và Triangle
 * tạo ứng suất kéo theo phương tuyến". adaptivecubic không thuộc họ đó nên tránh được đúng
 * cơ chế ấy. Số của OrcaSlicer (đo bằng Klipper Estimator): gyroid có điểm thời gian 8/8 —
 * cao nhất bảng, gấp 4 lần adaptivecubic (2) — trong khi sức bền 6/6 chỉ NGANG grid và cubic.
 * Ràng buộc người dùng đặt ra: cấu hình tối ưu không được chậm hơn file gốc. Nên chọn
 * adaptivecubic và cảnh báo rõ; nếu in xong vẫn cong vênh thì đổi tay sang gyroid.
 */
const EXPECT = {
  'hop-lon-phang':  { brim_type: 'outer_only', sparse_infill_pattern: 'adaptivecubic', enable_support: 0, accel: false },
  'cot-cao-manh':   { brim_type: 'outer_only', enable_support: 0, accel: true },
  'cau-R40':        { brim_type: 'outer_only', enable_support: 1, support_type: 'tree(auto)', accel: false },
  'vase-con-loe':   { enable_support: 0, vlh: true },
  'tru-dung':       { enable_support: 0 },
  'bridge-2-chan':  { enable_support: 1, enable_overhang_speed: 1 },
};

for (const { name, tris } of ARCHETYPES) {
  test(`golden: ${name}`, () => {
    const F = geoFeatures(tris);
    const P = optimize(F, printerLimits(PS), 'PLA Matte', 'Chi tiết trang trí', PS, 'balanced');
    const e = EXPECT[name];
    if (e.brim_type) assert.equal(P.deltaProcess.brim_type, e.brim_type, 'brim_type');
    if (e.sparse_infill_pattern) assert.equal(P.deltaProcess.sparse_infill_pattern, e.sparse_infill_pattern, 'infill pattern');
    if ('enable_support' in e) assert.equal(P.deltaProcess.enable_support, e.enable_support, 'enable_support');
    if (e.support_type) assert.equal(P.deltaProcess.support_type, e.support_type, 'support_type');
    if ('accel' in e) assert.equal(P.deltaProcess.default_acceleration !== undefined, e.accel, 'giảm accel?');
    if (e.enable_overhang_speed) assert.equal(P.deltaProcess.enable_overhang_speed, 1, 'overhang speed');
    if (e.vlh) assert.ok(P.vlhRanges.length > 0, 'phải sinh VLH ranges');
    assert.deepEqual(P.violations, [], `còn bất biến vỡ: ${JSON.stringify(P.violations)}`);
  });
}

test('golden: hình cầu KHÔNG bị hạ accel (bug đã bắt trong prototype)', () => {
  const F = geoFeatures(ARCHETYPES.find(a => a.name === 'cau-R40').tris);
  const P = optimize(F, printerLimits(PS), 'PLA Matte', 'Chi tiết trang trí', PS, 'balanced');
  assert.equal(P.deltaProcess.default_acceleration, undefined);
});

test('golden: cả 6 dạng vật × 3 mode đều không còn bất biến vỡ', () => {
  for (const { name, tris } of ARCHETYPES)
    for (const m of ['quality', 'balanced', 'fast']) {
      const P = optimize(geoFeatures(tris), printerLimits(PS), 'PLA Matte', 'Chi tiết trang trí', PS, m);
      assert.deepEqual(P.violations, [], `${name} / ${m}: ${JSON.stringify(P.violations)}`);
    }
});
