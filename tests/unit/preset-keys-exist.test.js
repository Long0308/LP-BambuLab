'use strict';
const { test } = require('node:test');
const assert = require('node:assert');
const fs = require('fs');
const path = require('path');
const { loadPure } = require('./lib/loadPure');
const { geoFeatures, printerLimits, optimize, buildPresets, MODES } = loadPure();
const { ARCHETYPES } = require('./fixtures/meshes');

/* Gõ sai một tên key thì Bambu Studio bỏ qua nó KHÔNG báo lỗi — preset trông như import
   được nhưng thiếu mất thiết lập. PrintConfig.cpp là danh sách key hợp lệ duy nhất. */
const SRC = fs.readFileSync(path.join(__dirname, '..', '..', 'PrintConfig.cpp'), 'utf8');

/* Không phải key nào cũng có `this->add("...")`. Các ô override của filament được sinh
   trong VÒNG LẶP (PrintConfig.cpp:6273 `add_nullable(opt_key, ...)`) từ hai mảng hằng.
   Bỏ qua chúng thì phép kiểm này báo oan chính key hợp lệ. */
const generated = new Set();
for (const arr of ['filament_overhang_override_keys', 'filament_extruder_override_keys']) {
  const m = new RegExp(`${arr}\\s*=\\s*\\{([\\s\\S]*?)\\};`).exec(SRC);
  if (m) for (const x of m[1].matchAll(/"([^"]+)"/g)) generated.add(x[1]);
}
const exists = k => SRC.includes(`this->add("${k}"`) || SRC.includes(`add_nullable("${k}"`) || generated.has(k);

/* Chốt chặn: nếu regex trên hỏng (đổi format nguồn, escape sai) thì `generated` rỗng và
   mọi phép kiểm dưới sẽ xanh vì lý do sai. Bắt nó chết ngay tại đây. */
test('phép kiểm không được xanh vì lý do sai', () => {
  assert.ok(generated.size >= 7, `chỉ trích được ${generated.size} key sinh động — regex hỏng`);
  assert.ok(exists('layer_height'), 'key có thật phải nhận là có');
  assert.ok(exists('filament_enable_overhang_speed'), 'key sinh trong vòng lặp phải nhận là có');
  assert.ok(!exists('khong_ton_tai_dau_ca'), 'key bịa phải bị bắt');
});

/* Key phong bì của preset, không phải option của engine. */
const ENVELOPE = new Set(['from', 'version', 'name', 'inherits', 'print_settings_id',
  'filament_settings_id', 'print_extruder_id', 'print_extruder_variant', 'filament_extruder_variant']);

const PS = {
  nozzle_diameter: ['0.4'], layer_height: '0.2', filament_max_volumetric_speed: ['22'],
  inner_wall_line_width: '0.45', sparse_infill_line_width: '0.45',
  internal_solid_infill_line_width: '0.42', outer_wall_line_width: '0.42', top_surface_line_width: '0.45',
  filament_type: ['PLA'], top_shell_layers: '5', top_shell_thickness: '1.0',
  seam_slope_type: 'all', filament_scarf_seam_type: ['none'],
  enable_pressure_advance: ['1'], elefant_foot_compensation: '0.12', brim_object_gap: '0.1',
  support_style: 'default', enable_prime_tower: '1', override_process_overhang_speed: ['0'],
};

test('mọi key preset xuất ra đều tồn tại trong PrintConfig.cpp', () => {
  const seen = new Set();
  for (const { tris } of ARCHETYPES)
    for (const goal of ['Chi tiết trang trí', 'Công năng cơ khí'])
      for (const m of Object.keys(MODES)) {
        const P = optimize(geoFeatures(tris), printerLimits(PS), 'PLA Matte', goal, PS, m, 22);
        const [{ process, filament }] = buildPresets([P], 'PLA Matte');
        for (const o of [process, filament])
          for (const k in o) if (!ENVELOPE.has(k)) seen.add(k);
      }
  assert.ok(seen.size > 20, `chỉ thấy ${seen.size} key — fixture chưa phủ đủ`);
  const bad = [...seen].filter(k => !exists(k));
  assert.deepEqual(bad, [], `key không có trong PrintConfig.cpp: ${bad.join(', ')}`);
});

test('mọi key trong ARRAY_KEYS cũng phải là option thật', () => {
  /* ARRAY_KEYS quyết định mảng-hay-vô-hướng; một tên chết ở đây là bẫy câm. */
  const src = fs.readFileSync(path.join(__dirname, '..', '..', 'BambuLab-A1-Hub.html'), 'utf8');
  const m = /const ARRAY_KEYS=new Set\(\[([\s\S]*?)\]\)/.exec(src);
  assert.ok(m, 'không tìm thấy ARRAY_KEYS');
  const keys = [...m[1].matchAll(/"([^"]+)"/g)].map(x => x[1]);
  assert.ok(keys.length >= 14);
  assert.deepEqual(keys.filter(k => !exists(k)), []);
});
