'use strict';
const { test } = require('node:test');
const assert = require('node:assert');
const { loadPure } = require('./lib/loadPure');
const { box, sphere, bridge } = require('./fixtures/meshes');

const { geoFeatures } = loadPure();

test('hộp 100x100x50: đáy KHÔNG bị tính là overhang', () => {
  const F = geoFeatures(box(100, 100, 50));
  assert.equal(F.down_cm2.toFixed(1), '0.0', 'hộp không có overhang thật');
  assert.equal(F.firstArea_cm2.toFixed(0), '100', 'đáy 100 cm²');
  assert.equal(F.topArea_cm2.toFixed(0), '100', 'mặt trên 100 cm²');
  assert.equal(F.islands, 1);
});

test('hộp 200x150: baseDiag = đường chéo đáy = 250mm', () => {
  const F = geoFeatures(box(200, 150, 20));
  assert.ok(Math.abs(F.baseDiag_mm - 250) < 0.5, `baseDiag=${F.baseDiag_mm}`);
});

test('cột 20x20x150: aspect = 7.5', () => {
  const F = geoFeatures(box(20, 20, 150));
  assert.ok(Math.abs(F.aspect - 7.5) < 0.01);
});

test('cầu R40: overhang thật 10–18%, tiếp xúc đáy ~0', () => {
  const F = geoFeatures(sphere(40));
  assert.ok(F.down > 10 && F.down < 18, `down=${F.down}`);
  assert.ok(F.firstArea_cm2 < 1, `firstArea=${F.firstArea_cm2}`);
});

test('cầu R40: ba dải góc đều có diện tích, gần-đứng nhiều nhất', () => {
  const F = geoFeatures(sphere(40));
  assert.ok(F.bands.lo > 0 && F.bands.mid > 0 && F.bands.hi > 0);
  assert.ok(F.bands.hi > F.bands.mid, 'mặt gần đứng nhiều hơn mặt cong 25–50°');
});

test('zSlope: bin theo Z, thetaP10 hợp lệ', () => {
  const F = geoFeatures(sphere(40));
  assert.ok(F.zSlope.length >= 4);
  for (const b of F.zSlope) {
    assert.ok(b.z1 > b.z0);
    if (b.area > 0) assert.ok(b.thetaP10 >= 0 && b.thetaP10 <= 90);
  }
});

test('bridge: có mặt 75–90° (mặt dưới dầm)', () => {
  const F = geoFeatures(bridge());
  assert.ok(F.ohBins['75-90'] > 10, `ohBins 75-90 = ${F.ohBins['75-90']} cm²`);
});

test('vase côn loe: nhiều mặt θ>=50 (thành gần đứng)', () => {
  const { frustum } = require('./fixtures/meshes');
  const F = geoFeatures(frustum(40, 55, 150));
  assert.ok(F.bands.hi > 100, `bands.hi = ${F.bands.hi} cm²`);
  assert.equal(F.down_cm2.toFixed(1), '0.0', 'thành loe ra ngoài không phải overhang');
});

test('topPlateaus: hộp có đúng 1 mảng phẳng trên', () => {
  const F = geoFeatures(box(100, 100, 50));
  assert.equal(F.topPlateaus.length, 1);
  assert.ok(Math.abs(F.topPlateaus[0].z - 50) < 0.6);
  assert.ok(Math.abs(F.topPlateaus[0].area_cm2 - 100) < 0.5);
});
