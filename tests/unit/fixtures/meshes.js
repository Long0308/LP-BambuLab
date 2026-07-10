'use strict';
/* 6 dạng vật tổng hợp — đáp án hình học biết trước.
   Mỗi hàm trả về mảng tam giác [[p1,p2,p3],...], p = [x,y,z]. Đơn vị mm. */

function box(dx, dy, dz, z0 = 0) {
  const x0 = -dx / 2, y0 = -dy / 2;
  const v = [[x0,y0,z0],[x0+dx,y0,z0],[x0+dx,y0+dy,z0],[x0,y0+dy,z0],
             [x0,y0,z0+dz],[x0+dx,y0,z0+dz],[x0+dx,y0+dy,z0+dz],[x0,y0+dy,z0+dz]];
  const f = [[0,2,1],[0,3,2],[4,5,6],[4,6,7],[0,1,5],[0,5,4],
             [1,2,6],[1,6,5],[2,3,7],[2,7,6],[3,0,4],[3,4,7]];
  return f.map(([a,b,c]) => [v[a], v[b], v[c]]);
}

function sphere(r, seg = 40) {
  const T = [];
  const P = (t, p) => [r*Math.sin(t)*Math.cos(p), r*Math.sin(t)*Math.sin(p), r + r*Math.cos(t)];
  for (let i = 0; i < seg; i++) {
    const t0 = Math.PI*i/seg, t1 = Math.PI*(i+1)/seg;
    for (let j = 0; j < seg*2; j++) {
      const p0 = Math.PI*j/seg, p1 = Math.PI*(j+1)/seg;
      const a = P(t0,p0), b = P(t1,p0), c = P(t1,p1), d = P(t0,p1);
      T.push([a,b,c]); T.push([a,c,d]);
    }
  }
  return T;
}

function frustum(r0, r1, h, seg = 64) {
  const T = [];
  for (let j = 0; j < seg; j++) {
    const p0 = 2*Math.PI*j/seg, p1 = 2*Math.PI*(j+1)/seg;
    const a = [r0*Math.cos(p0), r0*Math.sin(p0), 0], b = [r0*Math.cos(p1), r0*Math.sin(p1), 0];
    const c = [r1*Math.cos(p1), r1*Math.sin(p1), h], d = [r1*Math.cos(p0), r1*Math.sin(p0), h];
    T.push([a,b,c], [a,c,d], [[0,0,0], b, a], [[0,0,h], d, c]);
  }
  return T;
}

function bridge() {
  const shift = (T, dx, dy, dz) => T.map(t => t.map(p => [p[0]+dx, p[1]+dy, p[2]+dz]));
  return [...box(20,20,50), ...shift(box(20,20,50), 80, 0, 0), ...shift(box(100,20,10), 40, 0, 50)];
}

const ARCHETYPES = [
  { name: 'hop-lon-phang',   tris: box(200,150,20) },
  { name: 'cot-cao-manh',    tris: box(20,20,150) },
  { name: 'cau-R40',         tris: sphere(40) },
  { name: 'vase-con-loe',    tris: frustum(40,55,150) },
  { name: 'tru-dung',        tris: frustum(40,40,150) },
  { name: 'bridge-2-chan',   tris: bridge() },
];

module.exports = { box, sphere, frustum, bridge, ARCHETYPES };
