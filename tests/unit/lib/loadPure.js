'use strict';
const fs = require('fs');
const path = require('path');

const HUB = path.join(__dirname, '..', '..', '..', 'BambuLab-A1-Hub.html');
const START = '/* PURE:START */';
const END = '/* PURE:END */';

/** Trích khối hàm thuần khỏi hub HTML rồi eval trong node.
 *  Giữ hub là 1 file offline duy nhất mà vẫn test được bằng `node --test`. */
function loadPure() {
  const src = fs.readFileSync(HUB, 'utf8');
  const i = src.indexOf(START);
  const j = src.indexOf(END);
  if (i < 0 || j < 0) throw new Error('Không tìm thấy marker PURE:START / PURE:END trong hub');
  const body = src.slice(i + START.length, j);
  const names = ['geoFeatures', 'printerLimits', 'derive', 'checkInvariants', 'optimize', 'MODES', 'buildPresets', 'PATTERNS'];
  const fn = new Function(`${body}\n; return {${names.join(',')}};`);
  return fn();
}

module.exports = { loadPure };
