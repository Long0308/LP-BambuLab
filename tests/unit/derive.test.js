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

/* Stock '0.20mm Standard @BBL A1' CỐ Ý đặt inner_wall=300 / sparse_infill=270, trên trần
   244.4, để bộ giới hạn lưu lượng tự ghì theo nhựa đang nạp. Đó là tính năng.
   I1 chỉ là lỗi khi optimizer tự ghi một con số rồi tưởng nó được tôn trọng — nên khi
   optimize() truyền `owned`, I1 chỉ soi đúng những key đó. Không có `owned` (audit preset
   rời) thì soi toàn bộ, vì lúc đó mọi key trong file đều là do người dùng chịu trách nhiệm. */
const STOCK_OVER_CAP = { ...BASE, inner_wall_speed: ['300'], sparse_infill_speed: ['270'] };

test('I1: có `owned` → bỏ qua tốc độ stock kế thừa, không ghi đè chúng', () => {
  const L = printerLimits(STOCK_OVER_CAP);
  const d = derive(STOCK_OVER_CAP, L);
  const owned = new Set(['internal_solid_infill_speed']);
  const v = checkInvariants(STOCK_OVER_CAP, L, d, false, owned);
  assert.deepEqual(v.filter(x => x.id === 'I1').map(x => x.key), [],
    'stock 300/270 trên trần là chủ ý của Bambu, optimizer không sở hữu → không đụng');
});

test('I1: có `owned` → vẫn bắt key optimizer tự ghi mà vượt trần', () => {
  const ps = { ...STOCK_OVER_CAP, layer_height: '0.24' };
  const L = printerLimits(ps);
  const v = checkInvariants(ps, L, derive(ps, L), false, new Set(['internal_solid_infill_speed']));
  assert.deepEqual(v.filter(x => x.id === 'I1').map(x => x.key), ['internal_solid_infill_speed'],
    'chỉ key sở hữu bị bắt, inner_wall/sparse_infill kế thừa thì không');
});

test('I1: không truyền `owned` → soi toàn bộ (audit preset rời)', () => {
  const L = printerLimits(STOCK_OVER_CAP);
  const v = checkInvariants(STOCK_OVER_CAP, L, derive(STOCK_OVER_CAP, L));
  assert.deepEqual(v.filter(x => x.id === 'I1').map(x => x.key),
    ['inner_wall_speed', 'sparse_infill_speed']);
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

/* PrintConfig.cpp:93-101 — filament_overhang_override_keys có đúng 7 key. Nhưng
   Tab.cpp:4256-4269 gác chúng bằng HAI điều kiện khác nhau:
     · filament_enable_overhang_speed, filament_bridge_speed  → chỉ cần override
     · 5 key filament_overhang_*_speed                        → override AND enable
   overhang_fan_speed không nằm trong danh sách (đó là quạt, không phải tốc độ). */
test('I7: đặt filament_bridge_speed mà override tắt → giá trị không có hiệu lực', () => {
  assert.ok(ids({ ...BASE, filament_bridge_speed: ['50'] }).includes('I7'));
  assert.ok(ids({ ...BASE, filament_overhang_totally_speed: ['10'] }).includes('I7'));
});

test('I7: bật override thì không báo (nhóm chỉ cần override)', () => {
  const ps = { ...BASE, filament_bridge_speed: ['50'], override_process_overhang_speed: ['1'] };
  assert.ok(!ids(ps).includes('I7'));
});

test('I7: 5 key phần trăm cần CẢ override lẫn filament_enable_overhang_speed', () => {
  const on = { ...BASE, override_process_overhang_speed: ['1'] };
  assert.ok(ids({ ...on, filament_enable_overhang_speed: ['0'], filament_overhang_1_4_speed: ['100'] }).includes('I7'),
    'override bật nhưng enable tắt → Tab.cpp:4269 vẫn khoá 5 ô này');
  assert.ok(!ids({ ...on, filament_enable_overhang_speed: ['1'], filament_overhang_1_4_speed: ['100'] }).includes('I7'),
    'bật cả hai → hợp lệ');
});

/* File .3mf thật mang config ĐÃ PHÂN GIẢI: cả 7 key filament_* đều có giá trị, phần lớn
   bằng đúng key process tương ứng (PrintConfig.cpp:6275 ghép cặp bằng cách bỏ tiền tố
   'filament_'). Nếu bằng nhau thì cổng đóng cũng chẳng mất gì → không được báo.
   Đo trên 'Body 14 - LP.3mf': 6/7 key trùng, chỉ filament_bridge_speed=25 vs bridge_speed=50. */
test('I7: giá trị filament TRÙNG key process → không báo (nhiễu do phân giải config)', () => {
  const noise = { ...BASE,
    filament_enable_overhang_speed: ['1'], enable_overhang_speed: ['1'],
    filament_overhang_2_4_speed: ['50'], overhang_2_4_speed: ['50'] };
  assert.ok(!ids(noise).includes('I7'), 'trùng giá trị thì cổng đóng cũng không mất gì');
});

test('I7: chỉ báo key thật sự LỆCH khỏi process', () => {
  const real = { ...BASE, filament_bridge_speed: ['25'], bridge_speed: ['50'],
                 filament_enable_overhang_speed: ['1'], enable_overhang_speed: ['1'] };
  const v = checkInvariants(real, printerLimits(real), derive(real, printerLimits(real)));
  const i7 = v.find(x => x.id === 'I7');
  assert.ok(i7, 'bridge 25 vs 50 là override thật, cổng đóng → mất');
  assert.ok(/filament_bridge_speed/.test(i7.msg));
  assert.ok(!/filament_enable_overhang_speed/.test(i7.msg), 'key trùng giá trị không được kể tên');
});

test('I7: overhang_fan_speed KHÔNG bị gác (là quạt, không phải tốc độ)', () => {
  assert.ok(!ids({ ...BASE, overhang_fan_speed: ['100'] }).includes('I7'),
    'tầng 4 đặt overhang_fan_speed; nếu I7 bắt nhầm thì golden test sẽ đỏ oan');
});

/* PrintConfig.cpp:7423-7437 — spiral_mode ép cứng top_shell_layers=0 lúc slice,
   bất kể top_shell_thickness. Preset vase hợp lệ không được báo I2. */
test('I2: spiral_mode ép top_shell_layers=0 → không báo oan preset vase', () => {
  const ps = { ...BASE, spiral_mode: '1', wall_loops: '1', top_shell_layers: '0', top_shell_thickness: '0.8' };
  const L = printerLimits(ps);
  const d = derive(ps, L);
  assert.equal(d.effTopLayers, 0, 'engine ép 0, derive phải phản ánh đúng');
  assert.ok(!checkInvariants(ps, L, d).includes('I2'));
  assert.ok(!ids(ps).includes('I2'));
});

/* Task 7-11 ghép cấu hình bằng Object.assign({}, ps, deltaProcess, deltaFilament),
   trong đó delta là SỐ JS thô chứ không phải mảng chuỗi. Khoá hành vi đó lại. */
test('nhận số JS thô như nhận mảng chuỗi', () => {
  const raw = { ...BASE, layer_height: 0.24, inner_wall_speed: 240, brim_object_gap: 0.1,
                elefant_foot_compensation: 0.12, enable_prime_tower: 0 };
  const v = ids(raw);
  assert.ok(v.includes('I1'), 'flow 25.92 > 22 dù speed là số thô');
  assert.ok(v.includes('I6'), 'brim_object_gap số thô 0.1 > 0');
});

test('I3: đúng biên [layerMin, layerMax] thì không báo', () => {
  assert.ok(!ids({ ...BASE, layer_height: 0.10 }).includes('I3'), 'sàn 0.10');
  assert.ok(!ids({ ...BASE, layer_height: 0.28, inner_wall_speed: 100, sparse_infill_speed: 100,
                   internal_solid_infill_speed: 100, outer_wall_speed: 100, top_surface_speed: 100 }).includes('I3'), 'trần 0.28');
});

test('cfg rỗng: không nổ, không bịa vi phạm', () => {
  const L = printerLimits({});
  assert.deepEqual(checkInvariants({}, L, derive({}, L)).map(x => x.id), []);
});

test('BASE sạch: không vi phạm gì (trừ khi bật VLH)', () => {
  const L = printerLimits(BASE);
  const v = checkInvariants(BASE, L, derive(BASE, L));
  assert.deepEqual(v.map(x => x.id), []);
});
