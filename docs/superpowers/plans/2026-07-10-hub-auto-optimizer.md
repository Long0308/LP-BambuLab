# A1 Hub Auto-Optimizer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Thả một `.3mf` vào hub → hub tự sinh cấu hình tối ưu (first layer → warping → bề mặt/độ bền → bo cong → thời gian), xuất 2 preset import được + bảng Height range, mọi quyết định kèm con số và nguồn.

**Architecture:** Ba đơn vị thuần hàm trong `BambuLab-A1-Hub.html` — `geoFeatures()` (chỉ hình học), `printerLimits()` (chỉ đọc config), `optimize()` (Extract → Transform → Derive → Validate → lặp tới điểm bất động → Load). Chúng nằm giữa hai marker `/* PURE:START */` … `/* PURE:END */` để test harness `node` trích ra chạy được mà hub vẫn là một file HTML offline duy nhất.

**Tech Stack:** Vanilla JS trong một file HTML · `node --test` (built-in, không cần dependency) cho unit + golden test · `puppeteer-core` (đã có ở scratchpad) cho e2e hiện hữu.

**Spec:** `docs/superpowers/specs/2026-07-10-hub-auto-optimizer-design.md`

---

## File Structure

| File | Trách nhiệm |
|---|---|
| `BambuLab-A1-Hub.html` | Sửa: thêm marker PURE, `geoFeatures` mở rộng, `printerLimits`, `derive`, `checkInvariants`, `optimize`, `renderPlan`, `renderVlhTable`; sửa 2 luật `auditFile` |
| `tests/lib/loadPure.js` | Tạo: trích khối PURE khỏi HTML, trả về object các hàm |
| `tests/fixtures/meshes.js` | Tạo: 6 mesh tổng hợp (hộp, cột, cầu, vase, trụ, bridge) |
| `tests/geoFeatures.test.js` | Tạo: unit test hình học, đáp án biết trước |
| `tests/derive.test.js` | Tạo: unit test 7 bất biến |
| `tests/optimize.test.js` | Tạo: test từng tầng |
| `tests/golden-archetypes.test.js` | Tạo: snapshot config cho 6 dạng vật |

---

## Task 1: Sửa 2 luật `auditFile` cũ (làm TRƯỚC, kẻo optimizer bị hub báo oan)

**Files:**
- Modify: `BambuLab-A1-Hub.html` (luật `bed >= 65`, và luật infill pattern)

- [ ] **Step 1: Tìm dòng luật bed hiện tại**

Run: `grep -n 'Bed hơi nóng cho PLA' BambuLab-A1-Hub.html`
Expected: đúng 1 dòng.

- [ ] **Step 2: Thay bằng luật theo diện tích đế**

Tìm:
```js
 if(ft.includes("PLA")&&bed>=65)add("warn","Bed hơi nóng cho PLA","bed "+bed+"°C → dễ phồng chân (elephant foot) + heat-creep. Hè VN 55–60°C là đủ.");
```
Thay bằng:
```js
 /* wiki Bambu: PLA trên Textured PEI đích 55–65°C. Đế LỚN cần 65; đế nhỏ mới nên hạ.
    Luật cũ ("bed>=65 là nóng") trái wiki và sẽ báo oan chính cấu hình optimizer sinh ra. */
 if(ft.includes("PLA")&&bed){
   const bigBase=geo&&(geo.dx*geo.dy>15000);
   if(bigBase&&bed<65)add("warn","Đế LỚN mà bed thấp","Đế "+(geo.dx*geo.dy/100).toFixed(0)+" cm² + bed "+bed+"°C. Wiki Bambu: PLA cong góc → tăng bed lên 55–65°C (A1 khung hở, phòng <20°C thì +10°C nữa).");
   else if(!bigBase&&bed>=65)add("info","Bed 65°C với vật đế nhỏ","Đế nhỏ ít rủi ro vênh → có thể hạ 55–60°C để bớt phồng chân (elephant foot).");
 }
```

- [ ] **Step 3: Thêm luật infill pattern theo đế**

Ngay sau khối trên, thêm:
```js
 if(geo&&geo.dx*geo.dy>15000){
   const pat=(g("sparse_infill_pattern")||"").toLowerCase();
   if(/grid|triangle/.test(pat))add("warn","Đế LỚN + infill Grid/Triangle → ứng suất tuyến","Wiki Bambu: Grid và Triangle tạo ứng suất kéo theo phương tuyến trong lòng vật → cong vênh. Đổi sang Gyroid ≤25%.");
 }
```

- [ ] **Step 4: Chạy regression, xác nhận không vỡ**

Run:
```bash
SP=/c/Users/PHILON~1.PHA/AppData/Local/Temp/claude/d--56-BambuStudio/b1acb35c-9276-4bf4-aff4-1a3cb0210fd5/scratchpad
cd "$SP" && node e2e.js | tail -2 && node newrules.js | tail -2
```
Expected: `E2E: 63 passed, 0 failed` và `10 file · lệch 0 · pageerror 0`.

- [ ] **Step 5: Commit**

```bash
git add BambuLab-A1-Hub.html
git commit -F - <<'EOF'
fix: luật bed theo diện tích đế + cảnh báo Grid/Triangle trên đế lớn

Luật cũ "PLA && bed>=65 → hơi nóng" trái wiki Bambu (đích 55–65°C trên Textured
PEI; A1 khung hở phòng lạnh còn +10°C). Nó sẽ báo oan chính cấu hình mà
auto-optimizer sinh ra. Đổi thành luật theo diện tích đế.
EOF
```

---

## Task 2: Marker PURE + test harness `node`

**Files:**
- Modify: `BambuLab-A1-Hub.html`
- Create: `tests/lib/loadPure.js`

- [ ] **Step 1: Viết test harness trước (sẽ fail vì chưa có marker)**

Tạo `tests/lib/loadPure.js`:
```js
'use strict';
const fs = require('fs');
const path = require('path');

const HUB = path.join(__dirname, '..', '..', 'BambuLab-A1-Hub.html');
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
  const names = ['geoFeatures', 'printerLimits', 'derive', 'checkInvariants', 'optimize'];
  const fn = new Function(`${body}\n; return {${names.join(',')}};`);
  return fn();
}

module.exports = { loadPure };
```

- [ ] **Step 2: Chạy để xác nhận fail**

Run: `node -e "require('./tests/lib/loadPure').loadPure()"`
Expected: FAIL — `Không tìm thấy marker PURE:START / PURE:END trong hub`

- [ ] **Step 3: Thêm marker + 5 hàm rỗng vào hub**

Trong `BambuLab-A1-Hub.html`, ngay **trước** dòng `/* audit */`, chèn:
```js
/* PURE:START */
/* Khối hàm THUẦN — không đụng DOM, không đụng biến toàn cục của trang.
   tests/lib/loadPure.js trích nguyên khối này ra chạy bằng node. */
function geoFeatures(world){ return null; }
function printerLimits(ps){ return null; }
function derive(cfg,L){ return null; }
function checkInvariants(cfg,L,d){ return []; }
function optimize(F,L,mat,goal){ return null; }
/* PURE:END */
```

- [ ] **Step 4: Chạy lại, xác nhận pass**

Run: `node -e "const {loadPure}=require('./tests/lib/loadPure'); console.log(Object.keys(loadPure()).join(','))"`
Expected: `geoFeatures,printerLimits,derive,checkInvariants,optimize`

- [ ] **Step 5: Commit**

```bash
git add BambuLab-A1-Hub.html tests/lib/loadPure.js
git commit -m "test: harness trích khối PURE khỏi hub để chạy bằng node"
```

---

## Task 3: Mesh fixtures

**Files:**
- Create: `tests/fixtures/meshes.js`

- [ ] **Step 1: Viết fixtures**

```js
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
```

- [ ] **Step 2: Kiểm nhanh fixtures dựng đúng**

Run: `node -e "const {ARCHETYPES}=require('./tests/fixtures/meshes'); ARCHETYPES.forEach(a=>console.log(a.name, a.tris.length))"`
Expected: 6 dòng, `hop-lon-phang 12`, `cot-cao-manh 12`, `cau-R40 6400`, `vase-con-loe 256`, `tru-dung 256`, `bridge-2-chan 36`

- [ ] **Step 3: Commit**

```bash
git add tests/fixtures/meshes.js
git commit -m "test: 6 mesh fixture tổng hợp cho golden test"
```

---

## Task 4: `geoFeatures()`

**Files:**
- Modify: `BambuLab-A1-Hub.html` (trong khối PURE)
- Create: `tests/geoFeatures.test.js`

- [ ] **Step 1: Viết test fail trước**

```js
'use strict';
const { test } = require('node:test');
const assert = require('node:assert');
const { loadPure } = require('./lib/loadPure');
const { box, sphere } = require('./fixtures/meshes');

const { geoFeatures } = loadPure();

test('hộp 100x100x50: đáy không bị tính là overhang', () => {
  const F = geoFeatures(box(100, 100, 50));
  assert.equal(F.down_cm2.toFixed(1), '0.0', 'hộp không có overhang thật');
  assert.equal(F.firstArea_cm2.toFixed(0), '100', 'đáy 100 cm²');
  assert.equal(F.topArea_cm2.toFixed(0), '100', 'mặt trên 100 cm²');
  assert.equal(F.islands, 1);
});

test('hộp: baseDiag = đường chéo đáy', () => {
  const F = geoFeatures(box(200, 150, 20));
  assert.ok(Math.abs(F.baseDiag_mm - 250) < 0.5, `baseDiag=${F.baseDiag_mm}`);
});

test('cột 20x20x150: aspect = 7.5', () => {
  const F = geoFeatures(box(20, 20, 150));
  assert.ok(Math.abs(F.aspect - 7.5) < 0.01);
});

test('cầu R40: overhang thật ~14%, tiếp xúc đáy ~0', () => {
  const F = geoFeatures(sphere(40));
  assert.ok(F.down > 10 && F.down < 18, `down=${F.down}`);
  assert.ok(F.firstArea_cm2 < 1, `firstArea=${F.firstArea_cm2}`);
});

test('cầu R40: ba dải góc đều có diện tích', () => {
  const F = geoFeatures(sphere(40));
  assert.ok(F.bands.lo > 0 && F.bands.mid > 0 && F.bands.hi > 0);
  assert.ok(F.bands.hi > F.bands.mid, 'mặt gần đứng nhiều hơn mặt cong 25–50°');
});

test('zSlope: bin theo Z, có thetaP10', () => {
  const F = geoFeatures(sphere(40));
  assert.ok(F.zSlope.length >= 4);
  for (const b of F.zSlope) {
    assert.ok(b.z1 > b.z0);
    if (b.area > 0) assert.ok(b.thetaP10 >= 0 && b.thetaP10 <= 90);
  }
});

test('bridge: có mặt 75–90° (mặt dưới dầm)', () => {
  const { bridge } = require('./fixtures/meshes');
  const F = geoFeatures(bridge());
  assert.ok(F.ohBins['75-90'] > 10, `ohBins 75-90 = ${F.ohBins['75-90']} cm²`);
});
```

- [ ] **Step 2: Chạy để xác nhận fail**

Run: `node --test tests/geoFeatures.test.js`
Expected: FAIL — `Cannot read properties of null (reading 'down_cm2')`

- [ ] **Step 3: Cài đặt `geoFeatures` trong khối PURE**

Thay hàm rỗng bằng:
```js
function geoFeatures(world){
  if(!world||!world.length)return null;
  const C45=Math.cos(Math.PI/4), BIN=10;
  const mx=a=>{let m=-Infinity;for(const v of a)if(v>m)m=v;return m;};
  const mn=a=>{let m=Infinity;for(const v of a)if(v<m)m=v;return m;};
  let zmin=Infinity;
  for(const t of world)for(const p of t)if(p[2]<zmin)zmin=p[2];
  const zBase=zmin+0.6, zFirst=zmin+0.05;
  const xs=[],ys=[],zs=[];
  let area=0,vol=0,base=0,down=0,top=0,vert=0,slope=0,firstA=0;
  const fx=[],fy=[];
  const bands={lo:0,mid:0,hi:0};
  const ohBins={'45-60':0,'60-75':0,'75-90':0};
  const zsl=[];      // bin Z -> [[theta,area],...]
  const plateaus={}; // z làm tròn 1mm -> area
  for(const [p1,p2,p3] of world){
    for(const p of [p1,p2,p3]){xs.push(p[0]);ys.push(p[1]);zs.push(p[2]);}
    vol+=(p1[0]*(p2[1]*p3[2]-p3[1]*p2[2])-p1[1]*(p2[0]*p3[2]-p3[0]*p2[2])+p1[2]*(p2[0]*p3[1]-p3[0]*p2[1]))/6;
    const ux=p2[0]-p1[0],uy=p2[1]-p1[1],uz=p2[2]-p1[2];
    const vx=p3[0]-p1[0],vy=p3[1]-p1[1],vz=p3[2]-p1[2];
    const nx=uy*vz-uz*vy,ny=uz*vx-ux*vz,nz=ux*vy-uy*vx;
    const a=Math.hypot(nx,ny,nz)/2; if(a<1e-9)continue;
    area+=a;
    const cz=nz/(2*a), zc=(p1[2]+p2[2]+p3[2])/3;
    if(cz>0.985){ top+=a; const k=Math.round(zc); plateaus[k]=(plateaus[k]||0)+a; }
    else if(cz<-C45){
      if(zc<=zBase){ base+=a; if(zc<=zFirst){ firstA+=a; for(const p of [p1,p2,p3]){fx.push(p[0]);fy.push(p[1]);} } }
      else{
        down+=a;
        const dip=Math.acos(Math.min(1,-cz))*180/Math.PI; // 0 = phẳng úp xuống, 90 = thẳng đứng
        const ov=90-dip;                                   // góc so với mặt phẳng ngang
        if(ov>=75)ohBins['75-90']+=a; else if(ov>=60)ohBins['60-75']+=a; else if(ov>=45)ohBins['45-60']+=a;
      }
    }
    else if(Math.abs(cz)<0.15)vert+=a; else slope+=a;
    const th=Math.acos(Math.min(1,Math.abs(cz)))*180/Math.PI;
    if(th>5&&th<85){
      if(th<25)bands.lo+=a; else if(th<50)bands.mid+=a; else bands.hi+=a;
      if(zc>zBase){ const i=Math.floor((zc-zmin)/BIN); (zsl[i]=zsl[i]||[]).push([th,a]); }
    }
  }
  const dx=mx(xs)-mn(xs), dy=mx(ys)-mn(ys), dz=mx(zs)-mn(zs);
  const pc=v=>area?v/area*100:0;
  const zSlope=[];
  const nb=Math.max(1,Math.ceil(dz/BIN));
  for(let i=0;i<nb;i++){
    const bl=(zsl[i]||[]).slice().sort((a,b)=>a[0]-b[0]);
    const tot=bl.reduce((s,x)=>s+x[1],0);
    let p10=0,acc=0;
    for(const [th,a] of bl){acc+=a; if(acc>=0.10*tot){p10=th;break;}}
    zSlope.push({z0:i*BIN,z1:Math.min((i+1)*BIN,dz),area:tot/100,thetaP10:p10});
  }
  const topPlateaus=Object.keys(plateaus).map(k=>({z:+k,area_cm2:plateaus[k]/100}))
    .filter(x=>x.area_cm2>0.5).sort((a,b)=>b.area_cm2-a.area_cm2);
  const baseDiag=fx.length?Math.hypot(mx(fx)-mn(fx),mx(fy)-mn(fy)):0;
  return {
    tris:world.length, dx,dy,dz,
    vol_cm3:Math.abs(vol)/1000, area_cm2:area/100,
    down:pc(down), down_cm2:down/100, base:pc(base),
    top:pc(top), topArea_cm2:top/100, vert:pc(vert), slope:pc(slope),
    firstArea_cm2:firstA/100, baseDiag_mm:baseDiag,
    islands:countIslands(world,zmin),
    aspect:Math.min(dx,dy)>0?dz/Math.min(dx,dy):0,
    maxObj:Math.max(dx,dy,dz),
    bands:{lo:bands.lo/100,mid:bands.mid/100,hi:bands.hi/100},
    ohBins:{'45-60':ohBins['45-60']/100,'60-75':ohBins['60-75']/100,'75-90':ohBins['75-90']/100},
    zSlope, topPlateaus,
  };
}

/* Rasterize lát cắt z=zmin trên lưới 0.5mm rồi đếm thành phần liên thông (4-neighbour). */
function countIslands(world,zmin){
  const G=0.5, zf=zmin+0.05, cells=new Set();
  let minx=Infinity,miny=Infinity;
  const pts=[];
  for(const t of world){
    if(Math.max(t[0][2],t[1][2],t[2][2])>zf)continue;
    for(const p of t){pts.push(p); if(p[0]<minx)minx=p[0]; if(p[1]<miny)miny=p[1];}
  }
  if(!pts.length)return 0;
  for(const t of world){
    if(Math.max(t[0][2],t[1][2],t[2][2])>zf)continue;
    const xs=t.map(p=>p[0]), ys=t.map(p=>p[1]);
    const i0=Math.floor((Math.min.apply(null,xs)-minx)/G), i1=Math.ceil((Math.max.apply(null,xs)-minx)/G);
    const j0=Math.floor((Math.min.apply(null,ys)-miny)/G), j1=Math.ceil((Math.max.apply(null,ys)-miny)/G);
    for(let i=i0;i<=i1;i++)for(let j=j0;j<=j1;j++)cells.add(i+','+j);
  }
  let n=0; const seen=new Set();
  for(const c of cells){
    if(seen.has(c))continue;
    n++; const st=[c];
    while(st.length){
      const k=st.pop(); if(seen.has(k))continue; seen.add(k);
      const [i,j]=k.split(',').map(Number);
      for(const [di,dj] of [[1,0],[-1,0],[0,1],[0,-1]]){
        const m=(i+di)+','+(j+dj);
        if(cells.has(m)&&!seen.has(m))st.push(m);
      }
    }
  }
  return n;
}
```

- [ ] **Step 4: Chạy test, xác nhận pass**

Run: `node --test tests/geoFeatures.test.js`
Expected: `# pass 7`, `# fail 0`

- [ ] **Step 5: Nối `meshStats` cũ vào `geoFeatures`**

Trong `readFile()`, chỗ `const geo=meshStats(files);` giữ nguyên; thêm ngay sau:
```js
   const feat=geo&&geo._world?geoFeatures(geo._world):null;
```
Và trong `meshStats`, ngay trước `return {objects:...}`, thêm `_world:world,` vào object trả về.

- [ ] **Step 6: Chạy e2e, xác nhận không vỡ**

Run: `cd "$SP" && node e2e.js | tail -2`
Expected: `E2E: 63 passed, 0 failed`

- [ ] **Step 7: Commit**

```bash
git add BambuLab-A1-Hub.html tests/geoFeatures.test.js
git commit -m "feat: geoFeatures() - đặc trưng hình học có vị trí (zSlope, ohBins, topPlateaus, islands)"
```

---

## Task 5: `printerLimits()`

**Files:**
- Modify: `BambuLab-A1-Hub.html`
- Create: `tests/printerLimits.test.js`

- [ ] **Step 1: Viết test fail trước**

```js
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
```

- [ ] **Step 2: Chạy để xác nhận fail**

Run: `node --test tests/printerLimits.test.js`
Expected: FAIL — `Cannot read properties of null (reading 'nozzle')`

- [ ] **Step 3: Cài đặt**

```js
function printerLimits(ps){
  const f=v=>Array.isArray(v)?v[0]:v;
  const num=k=>parseFloat(f(ps[k]));
  const nozzle=num('nozzle_diameter')||0.4;
  const maxvol=num('filament_max_volumetric_speed')||0;
  const lh=num('layer_height')||0.2;
  const W={};
  for(const k of ['inner_wall','sparse_infill','internal_solid_infill','outer_wall','top_surface'])
    W[k]=num(k+'_line_width')||nozzle*1.125;
  const vmax={};
  for(const k in W)vmax[k]=maxvol?maxvol/(lh*W[k]):Infinity;
  /* Máy: min/max_layer_height. Quy tắc thực dụng: 25–75% đường kính nozzle (BigRep).
     Lấy GIAO của hai khoảng. A1 0.4: máy [0.08,0.28] ∩ quy tắc [0.10,0.30] = [0.10,0.28]. */
  const machMin=num('min_layer_height')||0.08, machMax=num('max_layer_height')||0.28;
  return {
    nozzle, maxvol, layerHeight:lh, width:W, vmax,
    layerMin:Math.max(machMin, nozzle*0.25),
    layerMax:Math.min(machMax, nozzle*0.75),
    smallNozzle:nozzle<0.3,
    printerId:String(f(ps.printer_settings_id)||''),
  };
}
```

- [ ] **Step 4: Chạy test**

Run: `node --test tests/printerLimits.test.js`
Expected: `# pass 3`, `# fail 0`

- [ ] **Step 5: Commit**

```bash
git add BambuLab-A1-Hub.html tests/printerLimits.test.js
git commit -m "feat: printerLimits() - trần lưu lượng + sàn/trần layer"
```

---

## Task 6: `derive()` + `checkInvariants()` — 7 bất biến

**Files:**
- Modify: `BambuLab-A1-Hub.html`
- Create: `tests/derive.test.js`

- [ ] **Step 1: Viết test fail trước**

```js
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

test('BASE sạch: không vi phạm gì (trừ khi bật VLH)', () => {
  const L = printerLimits(BASE);
  const v = checkInvariants(BASE, L, derive(BASE, L));
  assert.deepEqual(v.map(x => x.id), []);
});
```

- [ ] **Step 2: Chạy để xác nhận fail**

Run: `node --test tests/derive.test.js`
Expected: FAIL — `checkInvariants` trả `[]` nên các assert `v.some(...)` fail

- [ ] **Step 3: Cài đặt**

```js
function derive(cfg,L){
  const f=v=>Array.isArray(v)?v[0]:v;
  const num=k=>parseFloat(f(cfg[k]));
  const lh=num('layer_height')||L.layerHeight;
  const flow={};
  for(const k in L.width){
    const s=num(k+'_speed');
    if(!isNaN(s))flow[k]=lh*L.width[k]*s;
  }
  const tt=num('top_shell_thickness'), tl=parseInt(f(cfg.top_shell_layers),10)||0;
  const bt=num('bottom_shell_thickness'), bl=parseInt(f(cfg.bottom_shell_layers),10)||0;
  return {
    layerHeight:lh, flow,
    effTopLayers:tt>0?Math.max(tl,Math.ceil(tt/lh)):tl,
    effBottomLayers:bt>0?Math.max(bl,Math.ceil(bt/lh)):bl,
    firstFlow:(num('initial_layer_print_height')||lh)*(num('initial_layer_line_width')||0.5)*(num('initial_layer_speed')||25),
  };
}

/* Trả mảng vi phạm. `vlhWanted` = optimizer định xuất vlhRanges. */
function checkInvariants(cfg,L,d,vlhWanted){
  const f=v=>Array.isArray(v)?v[0]:v;
  const S=k=>String(f(cfg[k])??'').toLowerCase();
  const N=k=>parseFloat(f(cfg[k]));
  const V=[];
  for(const k in d.flow){
    if(L.maxvol&&d.flow[k]>L.maxvol+1e-6)
      V.push({id:'I1',key:k+'_speed',msg:`flow ${d.flow[k].toFixed(2)} > maxvol ${L.maxvol} → engine tự hạ tốc về ${L.vmax[k].toFixed(0)} mm/s, số bạn đặt vô nghĩa`});
  }
  const tl=parseInt(f(cfg.top_shell_layers),10)||0;
  if(d.effTopLayers>tl)
    V.push({id:'I2',key:'top_shell_layers',msg:`top_shell_thickness=${f(cfg.top_shell_thickness)} ⇒ engine tự tăng ${tl} → ${d.effTopLayers} lớp đặc. Khoản tiết kiệm không xảy ra.`});
  if(d.layerHeight<L.layerMin-1e-9||d.layerHeight>L.layerMax+1e-9)
    V.push({id:'I3',key:'layer_height',msg:`layer ${d.layerHeight} ngoài [${L.layerMin}, ${L.layerMax}]`});
  const ss=S('seam_slope_type'), fs=S('filament_scarf_seam_type');
  if(ss&&fs&&ss!==fs)
    V.push({id:'I4',key:'filament_scarf_seam_type',msg:`Filament '${fs}' đè Process '${ss}' (ô này không có checkbox override) → scarf chạy theo filament`});
  if(vlhWanted){
    const style=S('support_style'), type=S('support_type');
    const organic=style.includes('organic')||((style===''||style==='default')&&type.includes('tree'));
    if(organic)V.push({id:'I5',key:'support_style',msg:`Organic support chặn Variable layer height`});
    if(['1','true'].includes(S('enable_prime_tower')))
      V.push({id:'I5',key:'enable_prime_tower',msg:`Prime tower chặn Variable layer height`});
  }
  if(N('elefant_foot_compensation')>0&&N('brim_object_gap')>0)
    V.push({id:'I6',key:'brim_object_gap',msg:`elephant foot compensation > 0 ⇒ brim_object_gap phải = 0, nếu không brim tách khỏi vật`});
  return V;
}
```

- [ ] **Step 4: Chạy test**

Run: `node --test tests/derive.test.js`
Expected: `# pass 7`, `# fail 0`

- [ ] **Step 5: Commit**

```bash
git add BambuLab-A1-Hub.html tests/derive.test.js
git commit -m "feat: derive() + 7 bất biến - bắt được engine âm thầm sửa config"
```

---

## Task 7: `optimize()` — tầng 0→2 + vòng lặp điểm bất động

**Files:**
- Modify: `BambuLab-A1-Hub.html`
- Create: `tests/optimize.test.js`

- [ ] **Step 1: Viết test fail trước**

```js
'use strict';
const { test } = require('node:test');
const assert = require('node:assert');
const { loadPure } = require('./lib/loadPure');
const { geoFeatures, printerLimits, optimize } = loadPure();
const { box, sphere } = require('./fixtures/meshes');

const PS = {
  nozzle_diameter: ['0.4'], layer_height: '0.2', filament_max_volumetric_speed: ['22'],
  inner_wall_line_width: '0.45', sparse_infill_line_width: '0.45',
  internal_solid_infill_line_width: '0.42', outer_wall_line_width: '0.42', top_surface_line_width: '0.45',
  filament_type: ['PLA'], curr_bed_type: 'Textured PEI Plate',
  top_shell_layers: '5', top_shell_thickness: '1.0',
  enable_pressure_advance: ['0'], filament_flow_ratio: ['0.98'],
};

test('Tầng 0: chưa hiệu chuẩn thì cảnh báo, KHÔNG bịa K', () => {
  const F = geoFeatures(box(100,100,50));
  const P = optimize(F, printerLimits(PS), 'PLA Matte', 'Chi tiết trang trí', PS);
  assert.ok(P.calibration.some(c => /Flow Dynamics/.test(c.msg)));
  assert.equal(P.deltaFilament.pressure_advance, undefined, 'không được đề xuất giá trị K');
});

test('Tầng 1: luôn đặt close_fan 3 và initial_layer_speed 25', () => {
  const F = geoFeatures(box(100,100,50));
  const P = optimize(F, printerLimits(PS), 'PLA Matte', 'Chi tiết trang trí', PS);
  assert.equal(P.deltaFilament.close_fan_the_first_x_layers, 3);
  assert.equal(P.deltaProcess.initial_layer_speed, 25);
});

test('Tầng 2: đế lớn → brim 8mm + gyroid + bed 65', () => {
  const F = geoFeatures(box(200,150,20));
  const P = optimize(F, printerLimits(PS), 'PLA Matte', 'Chi tiết trang trí', PS);
  assert.equal(P.deltaProcess.brim_type, 'outer_only');
  assert.equal(P.deltaProcess.brim_width, 8);
  assert.equal(P.deltaProcess.sparse_infill_pattern, 'gyroid');
  assert.equal(P.deltaFilament.textured_plate_temp, 65);
});

test('Tầng 2 ghi đè tầng 5: gyroid thắng adaptivecubic, có ghi conflict', () => {
  const F = geoFeatures(box(200,150,20));
  const P = optimize(F, printerLimits(PS), 'PLA Matte', 'Chi tiết trang trí', PS);
  assert.equal(P.deltaProcess.sparse_infill_pattern, 'gyroid');
  assert.ok(P.conflicts.some(c => c.key === 'sparse_infill_pattern'));
});

test('Hình cầu: KHÔNG hạ acceleration (aspect 1.0), nhưng CÓ brim vì tiếp xúc bé', () => {
  const F = geoFeatures(sphere(40));
  const P = optimize(F, printerLimits(PS), 'PLA Matte', 'Chi tiết trang trí', PS);
  assert.equal(P.deltaProcess.default_acceleration, undefined, 'cầu không cao mảnh');
  assert.equal(P.deltaProcess.brim_type, 'outer_only');
});

test('Cột cao mảnh: CÓ hạ acceleration', () => {
  const F = geoFeatures(box(20,20,150));
  const P = optimize(F, printerLimits(PS), 'PLA Matte', 'Chi tiết trang trí', PS);
  assert.ok(P.deltaProcess.default_acceleration < 6000);
});
```

- [ ] **Step 2: Chạy để xác nhận fail**

Run: `node --test tests/optimize.test.js`
Expected: FAIL — `Cannot read properties of null (reading 'calibration')`

- [ ] **Step 3: Cài đặt khung + tầng 0/1/2**

```js
function optimize(F,L,mat,goal,ps){
  ps=ps||{};
  const f=v=>Array.isArray(v)?v[0]:v;
  const S=k=>String(f(ps[k])??'').toLowerCase();
  const dP={}, dF={}, reasons=[], conflicts=[], calibration=[], locked=new Set();
  const put=(bag,k,v,tier,why,src)=>{
    if(locked.has(k)){ conflicts.push({key:k,tier,wanted:v,kept:bag[k]}); return; }
    bag[k]=v; reasons.push({key:k,value:v,tier,why,src});
    if(tier<=2)locked.add(k);
  };
  const isPLA=/pla/i.test(mat)||/pla/i.test(String(f(ps.filament_type)||''));
  const functional=/cơ khí|chức năng|functional/i.test(goal||'');

  /* Tầng 0 — hiệu chuẩn: chỉ phát hiện, KHÔNG bịa giá trị */
  if(['0','false'].includes(S('enable_pressure_advance')))
    calibration.push({key:'enable_pressure_advance',msg:'Chưa bật Pressure Advance → chạy Flow Dynamics Calibration trên máy. Hub không đề xuất giá trị K.'});
  calibration.push({key:'filament_flow_ratio',msg:'Nếu flow ratio vẫn bằng giá trị stock của profile → chưa chạy Flow Rate Calibration. Đo trên máy, đừng đoán.'});

  /* Tầng 1 — first layer */
  put(dF,'close_fan_the_first_x_layers',3,1,'wiki: first layer not sticking','wiki/warping');
  put(dP,'initial_layer_speed',25,1,'lớp đầu chạy chậm để bám','—');
  put(dP,'initial_layer_print_height',Math.min(0.28,Math.max(0.20,L.layerHeight+0.04)),1,'lớp đầu dày hơn để dung sai mặt bàn','—');

  /* Tầng 2 — warping. Hai điều kiện TÁCH BẠCH. */
  const bigBase=F.firstArea_cm2>150||F.baseDiag_mm>150;
  const tinyContact=F.firstArea_cm2<5;
  const tallThin=F.aspect>3;
  if(bigBase||tinyContact||tallThin){
    put(dP,'brim_type','outer_only',2,bigBase?`đế ${F.firstArea_cm2.toFixed(0)} cm² / chéo ${F.baseDiag_mm.toFixed(0)} mm`:`tiếp xúc bé ${F.firstArea_cm2.toFixed(1)} cm²`,'wiki/warping');
    put(dP,'brim_width',8,2,'wiki PLA: brim 8–10mm','wiki/warping');
  }else{
    put(dP,'brim_type','auto_brim',2,'đế vừa, không rủi ro đặc biệt','wiki/brim');
  }
  if(tallThin){
    put(dP,'default_acceleration',4500,2,`aspect ${F.aspect.toFixed(1)} → wiki giảm 20–30%`,'wiki/warping');
    put(dP,'outer_wall_acceleration',3750,2,`aspect ${F.aspect.toFixed(1)} → wiki giảm 20–30%`,'wiki/warping');
  }
  if(bigBase){
    put(dP,'sparse_infill_pattern','gyroid',2,'wiki: large flat model → gyroid','wiki/warping');
    put(dP,'sparse_infill_density','15%',2,'wiki: ≤25%','wiki/warping');
    if(isPLA)put(dF,'textured_plate_temp',65,2,'wiki: PLA trên Textured PEI đích 55–65°C','wiki/warping');
  }
  if(parseFloat(f(ps.elefant_foot_compensation))>0)
    put(dP,'brim_object_gap',0,2,'I6: EFC>0 ⇒ gap phải 0, nếu không brim tách khỏi vật','wiki/brim');

  return {deltaProcess:dP,deltaFilament:dF,vlhRanges:[],reasons,conflicts,calibration,
          _put:put,_locked:locked,_ctx:{isPLA,functional,bigBase,tinyContact,tallThin}};
}
```

- [ ] **Step 4: Chạy test**

Run: `node --test tests/optimize.test.js`
Expected: `# pass 5`, `# fail 1` — test "Tầng 2 ghi đè tầng 5" vẫn fail vì tầng 5 chưa có.

- [ ] **Step 5: Tạm bỏ qua test tầng 5**

Đổi test đó thành `test.skip(...)` với ghi chú `// bật lại ở Task 10`.

Run: `node --test tests/optimize.test.js`
Expected: `# pass 5`, `# skip 1`, `# fail 0`

- [ ] **Step 6: Commit**

```bash
git add BambuLab-A1-Hub.html tests/optimize.test.js
git commit -m "feat: optimize() tầng 0-2 (hiệu chuẩn, first layer, warping) + khoá key + conflicts"
```

---

## Task 8: Tầng 3 (bề mặt) + 3b (độ bền) + 4b (võng mặt trên)

**Files:**
- Modify: `BambuLab-A1-Hub.html`
- Modify: `tests/optimize.test.js`

- [ ] **Step 1: Thêm test fail**

```js
test('Tầng 3: vùng θ<25° lớn → ironing/top shell, KHÔNG hạ layer', () => {
  const F = geoFeatures(sphere(40));
  const P = optimize(F, printerLimits(PS), 'PLA Matte', 'Chi tiết trang trí', PS);
  assert.equal(P.deltaProcess.top_shell_layers, 5);
  assert.equal(P.deltaProcess.top_surface_pattern, 'monotonicline');
  assert.equal(P.deltaProcess.layer_height, undefined, 'tầng 3 không được đụng layer_height');
});

test('Tầng 3b: goal chức năng → wall_loops tăng TRƯỚC, layer <= 0.25', () => {
  const F = geoFeatures(box(100,100,50));
  const P = optimize(F, printerLimits(PS), 'PLA Basic', 'Công năng cơ khí', PS);
  assert.ok(P.deltaProcess.wall_loops >= 3);
  assert.equal(P.deltaProcess.infill_wall_overlap, '15%');
  assert.ok(P.limits.layerMaxEff <= 0.25);
});

test('Tầng 3b KHÔNG bật cho đồ trang trí', () => {
  const F = geoFeatures(box(100,100,50));
  const P = optimize(F, printerLimits(PS), 'PLA Matte', 'Chi tiết trang trí', PS);
  assert.equal(P.deltaProcess.wall_loops, undefined);
});

test('Tầng 4b: mặt trên lớn + infill thưa → cảnh báo võng', () => {
  const F = geoFeatures(box(200,150,20));   // top 41% diện tích
  const P = optimize(F, printerLimits(PS), 'PLA Matte', 'Chi tiết trang trí', PS);
  assert.ok(P.warnings.some(w => /võng/.test(w.msg)));
});
```

- [ ] **Step 2: Chạy để xác nhận fail**

Run: `node --test tests/optimize.test.js`
Expected: FAIL — `P.limits` undefined, `P.warnings` undefined

- [ ] **Step 3: Cài đặt — chèn trước `return` của `optimize`**

```js
  const warnings=[];
  const layerMaxEff=functional?Math.min(L.layerMax,0.25):L.layerMax;

  /* Tầng 3 — bề mặt nhìn thấy */
  const isMatte=/matte/i.test(mat);
  if(F.top>12&&!isMatte)
    put(dP,'ironing_type','top surfaces',3,`mặt phẳng trên ${F.top.toFixed(0)}%`,'wiki/ironing');
  if(F.bands.lo>5){
    put(dP,'top_shell_layers',5,3,`${F.bands.lo.toFixed(1)} cm² mặt dốc <25°: ở sàn layer 0.08 bậc vẫn 0.23–0.45mm ⇒ hạ layer vô ích`,'đo thật');
    put(dP,'top_surface_pattern','monotonicline',3,'mặt trên đều','—');
    put(dP,'top_surface_speed',150,3,'chậm để mặt trên mịn','—');
  }
  put(dP,'wall_generator','arachne',3,'thành mỏng / chữ nhỏ','—');

  /* Tầng 3b — độ bền (chỉ khi goal chức năng). Thành TRƯỚC infill. */
  if(functional){
    put(dP,'wall_loops',3,3,'UltiMaker: 2 perimeter thêm > nâng infill 20→30%','ultimaker/infill');
    put(dP,'sparse_infill_density','25%',3,'PLA cứng: 20–30%','ultimaker/infill');
    put(dP,'sparse_infill_pattern','gyroid',3,'pattern chịu lực đẳng hướng','ultimaker/infill');
    put(dP,'infill_wall_overlap','15%',3,'khuyến nghị 10–25%; thấp hơn gây bong thành↔infill','ultimaker/infill');
  }

  /* Tầng 4b — võng mặt trên do infill quá thưa */
  const infPct=parseFloat(String(dP.sparse_infill_density||f(ps.sparse_infill_density)||'15'));
  if(F.top>15&&infPct<12)
    warnings.push({key:'sparse_infill_density',msg:`Mặt phẳng trên ${F.top.toFixed(0)}% + infill ${infPct}% → nguy cơ VÕNG mặt trên (UltiMaker). Nâng infill lên 15% hoặc top_shell_layers lên 6. Cả hai đều tốn thêm thời gian.`});
```

Và sửa `return`:
```js
  return {deltaProcess:dP,deltaFilament:dF,vlhRanges:[],reasons,conflicts,calibration,warnings,
          limits:{...L,layerMaxEff},
          _put:put,_locked:locked,_ctx:{isPLA,functional,bigBase,tinyContact,tallThin}};
```

- [ ] **Step 4: Chạy test**

Run: `node --test tests/optimize.test.js`
Expected: `# fail 0` (test tầng 5 vẫn skip)

- [ ] **Step 5: Commit**

```bash
git add BambuLab-A1-Hub.html tests/optimize.test.js
git commit -m "feat: optimize() tầng 3 (bề mặt) + 3b (độ bền: thành trước infill) + 4b (võng mặt trên)"
```

---

## Task 9: Tầng 4 — overhang/bridge + bảng Height range

**Files:**
- Modify: `BambuLab-A1-Hub.html`
- Modify: `tests/optimize.test.js`

- [ ] **Step 1: Thêm test fail**

```js
const { bridge, frustum } = require('./fixtures/meshes');

test('Support: 3 khoảng rạch ròi, không có vùng xám', () => {
  const dec = 'Chi tiết trang trí';
  const P1 = optimize(geoFeatures(box(100,100,50)), printerLimits(PS), 'PLA Matte', dec, PS);
  assert.equal(P1.deltaProcess.enable_support, 0, 'overhang 0% → tắt');

  const P2 = optimize(geoFeatures(sphere(40)), printerLimits(PS), 'PLA Matte', dec, PS);
  assert.equal(P2.deltaProcess.enable_support, 1);
  assert.equal(P2.deltaProcess.support_type, 'tree(auto)', 'overhang 14% > 8% → auto');
});

test('Bridge: bật enable_overhang_speed + overhang_fan_speed', () => {
  const P = optimize(geoFeatures(bridge()), printerLimits(PS), 'PLA Matte', 'Chi tiết trang trí', PS);
  assert.equal(P.deltaProcess.enable_overhang_speed, 1);
  assert.equal(P.deltaFilament.overhang_fan_speed, 100);
});

test('VLH: vase có nhiều mặt θ>=50° → sinh ranges + gỡ blocker', () => {
  const P = optimize(geoFeatures(frustum(40,55,150)), printerLimits(PS), 'PLA Matte', 'Chi tiết trang trí', PS);
  assert.ok(P.vlhRanges.length > 0);
  assert.equal(P.deltaProcess.support_style, 'tree_hybrid');
  assert.equal(P.deltaProcess.enable_prime_tower, 0);
});

test('VLH: mọi layer nằm trong [layerMin, layerMaxEff]', () => {
  const P = optimize(geoFeatures(sphere(40)), printerLimits(PS), 'PLA Matte', 'Chi tiết trang trí', PS);
  for (const r of P.vlhRanges) {
    assert.ok(r.layer >= P.limits.layerMin - 1e-9, `layer ${r.layer} < min`);
    assert.ok(r.layer <= P.limits.layerMaxEff + 1e-9, `layer ${r.layer} > max`);
    assert.ok(r.z1 > r.z0);
  }
});

test('VLH: vùng θ<25° KHÔNG bị hạ layer', () => {
  const P = optimize(geoFeatures(sphere(40)), printerLimits(PS), 'PLA Matte', 'Chi tiết trang trí', PS);
  const F = geoFeatures(sphere(40));
  for (const b of F.zSlope) {
    if (b.area > 0 && b.thetaP10 > 0 && b.thetaP10 < 25) {
      const r = P.vlhRanges.find(x => x.z0 === b.z0);
      if (r) assert.ok(r.layer >= 0.2, `bin ${b.z0}: θ=${b.thetaP10}° không được hạ layer, đang ${r.layer}`);
    }
  }
});
```

- [ ] **Step 2: Chạy để xác nhận fail**

Run: `node --test tests/optimize.test.js`
Expected: FAIL — `enable_support` undefined, `vlhRanges` rỗng

- [ ] **Step 3: Cài đặt — chèn sau tầng 4b**

```js
  /* Tầng 4 — overhang & bridge */
  if(F.ohBins['75-90']>2){
    put(dP,'enable_overhang_speed',1,4,`${F.ohBins['75-90'].toFixed(1)} cm² mặt 75–90° (bắc cầu)`,'—');
    put(dF,'overhang_fan_speed',100,4,'thổi mát vùng đua/bắc cầu','wiki/warping');
  }
  if(F.down<=2){
    put(dP,'enable_support',0,5,`overhang thật ${F.down.toFixed(2)}% (${F.down_cm2.toFixed(1)} cm²) → tự đỡ được`,'đo thật');
  }else if(F.down<=8){
    put(dP,'enable_support',1,4,`overhang thật ${F.down.toFixed(1)}%`,'đo thật');
    put(dP,'support_type','tree(manual)',4,'ít overhang + đồ trang trí → chỉ đỡ chỗ sơn, không để sẹo','PrintConfig.cpp:5184');
    warnings.push({key:'support_type',msg:"support_type '(manual)' KHÔNG sinh gì nếu chưa sơn enforcer. Prepare ▸ Support painting."});
  }else{
    put(dP,'enable_support',1,4,`overhang thật ${F.down.toFixed(1)}% → quá nhiều để sơn tay`,'đo thật');
    put(dP,'support_type','tree(auto)',4,'overhang lớn, không có support là hỏng','PrintConfig.cpp:5184');
  }

  /* Tầng 4 — Variable layer height */
  const STEP_TARGET=0.20;
  const wantVLH=F.bands.mid>3||F.bands.hi>20;
  if(wantVLH){
    const raw=F.zSlope.map(b=>{
      let lh;
      if(b.area<=0||b.thetaP10<=0)lh=layerMaxEff;
      else if(b.thetaP10>=50)lh=layerMaxEff;
      else if(b.thetaP10>=25)lh=Math.max(L.layerMin,Math.min(layerMaxEff,Math.round(STEP_TARGET*Math.tan(b.thetaP10*Math.PI/180)/0.02)*0.02));
      else lh=L.layerHeight;
      return {z0:b.z0,z1:b.z1,layer:+lh.toFixed(2),theta:b.thetaP10};
    });
    const merged=[];
    for(const r of raw){
      const last=merged[merged.length-1];
      if(last&&Math.abs(last.layer-r.layer)<1e-9)last.z1=r.z1;
      else merged.push({...r});
    }
    for(const r of merged)dPvlhPush(r);
    put(dP,'support_style','tree_hybrid',4,'gỡ blocker: organic support chặn VLH','BambuStudio.mo');
    put(dP,'enable_prime_tower',0,4,'gỡ blocker: prime tower chặn VLH','BambuStudio.mo');
  }
  function dPvlhPush(r){ vlh.push(r); }
```

Khai báo `const vlh=[];` ngay dưới `const warnings=[];`, rồi đổi `vlhRanges:[]` thành `vlhRanges:vlh` trong `return`.

- [ ] **Step 4: Chạy test**

Run: `node --test tests/optimize.test.js`
Expected: `# fail 0`

- [ ] **Step 5: Commit**

```bash
git add BambuLab-A1-Hub.html tests/optimize.test.js
git commit -m "feat: optimize() tầng 4 - support 3 khoảng rạch ròi, bridge, bảng Height range"
```

---

## Task 10: Tầng 5 (thời gian) + vòng lặp điểm bất động

**Files:**
- Modify: `BambuLab-A1-Hub.html`
- Modify: `tests/optimize.test.js`

- [ ] **Step 1: Bật lại test đã skip + thêm test fixpoint**

Đổi `test.skip('Tầng 2 ghi đè tầng 5'...)` về `test(...)`. Thêm:

```js
test('Tầng 5: đẩy tốc độ vùng khuất tới sát trần, KHÔNG đụng outer wall', () => {
  const F = geoFeatures(box(100,100,50));
  const P = optimize(F, printerLimits(PS), 'PLA Matte', 'Chi tiết trang trí', PS);
  assert.ok(P.deltaProcess.inner_wall_speed >= 235 && P.deltaProcess.inner_wall_speed <= 244);
  assert.ok(P.deltaProcess.internal_solid_infill_speed <= 262);
  assert.equal(P.deltaProcess.outer_wall_speed, undefined, 'cấm chạm outer wall');
  assert.equal(P.deltaProcess.top_surface_speed, 150, 'top surface do tầng 3 đặt, tầng 5 không được nâng');
});

test('Fixpoint: I2 được sửa, top_shell_layers không bị engine tăng ngầm', () => {
  const ps = { ...PS, top_shell_layers: '4' };
  const F = geoFeatures(box(100,100,50));
  const P = optimize(F, printerLimits(ps), 'PLA Matte', 'Chi tiết trang trí', ps);
  const eff = Math.max(P.deltaProcess.top_shell_layers ?? 4, Math.ceil(1.0 / 0.2));
  assert.equal(eff, P.deltaProcess.top_shell_layers, 'sau fixpoint, số lớp đã đủ dày');
});

test('Không còn bất biến nào vỡ sau fixpoint', () => {
  const F = geoFeatures(box(200,150,20));
  const P = optimize(F, printerLimits(PS), 'PLA Matte', 'Chi tiết trang trí', PS);
  assert.deepEqual(P.violations, [], JSON.stringify(P.violations));
});
```

- [ ] **Step 2: Chạy để xác nhận fail**

Run: `node --test tests/optimize.test.js`
Expected: FAIL — `inner_wall_speed` undefined, `P.violations` undefined

- [ ] **Step 3: Cài đặt tầng 5 + vòng lặp**

Chèn sau tầng 4:
```js
  /* Tầng 5 — thời gian. CHỈ vùng khuất. Đây là đòn duy nhất thật sự miễn phí. */
  for(const k of ['inner_wall','sparse_infill','internal_solid_infill']){
    const cap=L.vmax[k];
    if(!isFinite(cap))continue;
    const v=Math.floor(cap*0.98/5)*5;   // chừa ~2% biên, làm tròn bội 5
    put(dP,k+'_speed',v,5,`trần lưu lượng ${cap.toFixed(0)} mm/s (vùng khuất, không đụng bề mặt)`,'wiki/volumetric');
  }
  if(!wantVLH)put(dP,'enable_prime_tower',0,5,'in 1 màu không cần prime tower','—');
  put(dP,'sparse_infill_pattern','adaptivecubic',5,'tiết kiệm nhựa','—'); // bị tầng 2 chặn nếu đế lớn
```

Chèn ngay trước `return` — vòng lặp tới điểm bất động:
```js
  /* Derive → Validate → sửa → lặp. Tối đa 3 vòng. */
  let violations=[];
  for(let pass=0;pass<3;pass++){
    const merged=Object.assign({},ps,dP,dF);
    violations=checkInvariants(merged,L,derive(merged,L),wantVLH);
    if(!violations.length)break;
    let fixed=false;
    for(const v of violations){
      if(v.id==='I1'){
        const k=v.key.replace(/_speed$/,'');
        if(L.vmax[k]&&!locked.has(v.key)){
          dP[v.key]=Math.floor(L.vmax[k]*0.98/5)*5;
          reasons.push({key:v.key,value:dP[v.key],tier:5,why:'fixpoint I1: hạ về dưới trần lưu lượng',src:'wiki/volumetric'});
          fixed=true;
        }
      }else if(v.id==='I2'){
        const tt=parseFloat(f(ps.top_shell_thickness))||0;
        if(tt>0){
          dP.top_shell_layers=Math.ceil(tt/derive(merged,L).layerHeight);
          reasons.push({key:'top_shell_layers',value:dP.top_shell_layers,tier:5,why:`fixpoint I2: cần ≥ ${tt}mm bề dày, engine sẽ tự tăng nếu ta không tự đặt`,src:'PrintConfig.cpp top_shell_thickness'});
          fixed=true;
        }
      }else if(v.id==='I4'){
        dF.filament_scarf_seam_type=String(f(dP.seam_slope_type)||f(ps.seam_slope_type)||'all');
        reasons.push({key:'filament_scarf_seam_type',value:dF.filament_scarf_seam_type,tier:5,why:'fixpoint I4: filament luôn đè process, phải khớp',src:'Tab.cpp:4426'});
        fixed=true;
      }else if(v.id==='I6'){
        dP.brim_object_gap=0; fixed=true;
      }
    }
    if(!fixed)break;
  }
```

Thêm `violations` vào object `return`.

- [ ] **Step 4: Chạy test**

Run: `node --test tests/optimize.test.js`
Expected: `# fail 0`, không còn skip

- [ ] **Step 5: Commit**

```bash
git add BambuLab-A1-Hub.html tests/optimize.test.js
git commit -m "feat: optimize() tầng 5 + vòng lặp điểm bất động (derive → validate → sửa)"
```

---

## Task 11: Golden test — 6 dạng vật

**Files:**
- Create: `tests/golden-archetypes.test.js`

- [ ] **Step 1: Viết golden test**

```js
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
  enable_pressure_advance: ['1'], filament_flow_ratio: ['0.98'],
};

/* Kỳ vọng chốt từ spec §9. Đổi luật mà bảng này đổi ⇒ phải giải trình trong PR. */
const EXPECT = {
  'hop-lon-phang':  { brim_type:'outer_only', sparse_infill_pattern:'gyroid', enable_support:0, accel:false },
  'cot-cao-manh':   { brim_type:'outer_only', enable_support:0, accel:true },
  'cau-R40':        { brim_type:'outer_only', enable_support:1, support_type:'tree(auto)', accel:false },
  'vase-con-loe':   { enable_support:0, vlh:true },
  'tru-dung':       { enable_support:0 },
  'bridge-2-chan':  { enable_support:1, enable_overhang_speed:1 },
};

for (const { name, tris } of ARCHETYPES) {
  test(`golden: ${name}`, () => {
    const F = geoFeatures(tris);
    const P = optimize(F, printerLimits(PS), 'PLA Matte', 'Chi tiết trang trí', PS);
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
  const P = optimize(F, printerLimits(PS), 'PLA Matte', 'Chi tiết trang trí', PS);
  assert.equal(P.deltaProcess.default_acceleration, undefined);
});
```

- [ ] **Step 2: Chạy**

Run: `node --test tests/golden-archetypes.test.js`
Expected: `# pass 7`, `# fail 0`

- [ ] **Step 3: Chạy toàn bộ test**

Run: `node --test tests/`
Expected: `# fail 0`

- [ ] **Step 4: Commit**

```bash
git add tests/golden-archetypes.test.js
git commit -m "test: golden 6 dạng vật - chốt kỳ vọng, đổi luật phải giải trình"
```

---

## Task 12: UI — bảng quyết định, bảng Height range, nút xuất preset

**Files:**
- Modify: `BambuLab-A1-Hub.html`

- [ ] **Step 1: Render bảng quyết định + Height range**

Thêm ngoài khối PURE (được đụng DOM):
```js
function renderPlan(P){
  if(!P)return "";
  let h="<h2 class='sec' style='margin-top:18px'>Cấu hình tối ưu — tự sinh từ hình học</h2>";
  if(P.calibration.length){
    h+="<div class='callout c-amber'><svg class='icn'><use href='#i-alert'/></svg><div><b>Hiệu chuẩn trước đã.</b> Ba giá trị dưới đây ĐO TRÊN MÁY, hub không đoán:<ul>";
    P.calibration.forEach(c=>{h+="<li><code>"+esc(c.key)+"</code> — "+esc(c.msg)+"</li>";});
    h+="</ul></div></div>";
  }
  h+="<table><tr><th>Key</th><th>Giá trị</th><th>Tầng</th><th>Vì sao</th><th>Nguồn</th></tr>";
  P.reasons.forEach(r=>{
    h+="<tr><td><code>"+esc(r.key)+"</code></td><td class='val'>"+esc(String(r.value))+"</td><td>T"+r.tier+"</td><td class='gd'>"+esc(r.why)+"</td><td class='gd'>"+esc(r.src)+"</td></tr>";
  });
  h+="</table>";
  if(P.conflicts.length){
    h+="<div class='callout c-info'><svg class='icn'><use href='#i-info'/></svg><div><b>Xung đột đã giải:</b><ul>";
    P.conflicts.forEach(c=>{h+="<li><code>"+esc(c.key)+"</code>: tầng "+c.tier+" muốn <b>"+esc(String(c.wanted))+"</b>, giữ <b>"+esc(String(c.kept))+"</b> (tầng ưu tiên cao hơn đã khoá)</li>";});
    h+="</ul></div></div>";
  }
  P.warnings.forEach(w=>{h+="<div class='callout c-amber'><svg class='icn'><use href='#i-alert'/></svg><div>"+esc(w.msg)+"</div></div>";});
  if(P.vlhRanges.length){
    h+="<div class='sectitle'>Bảng Height range — nhập tay vào Prepare ▸ chuột phải vật ▸ Height range Modifier</div>";
    h+="<div class='gd'><code>adaptive_layer_height</code> nằm trong danh sách <code>ignore</code> của PrintConfig.cpp ⇒ KHÔNG set được bằng preset. Đây là cách duy nhất truyền đạt nó.</div>";
    h+="<table><tr><th>Z từ (mm)</th><th>Z đến (mm)</th><th>Layer height</th><th>Góc dốc p10</th></tr>";
    P.vlhRanges.forEach(r=>{h+="<tr><td>"+r.z0.toFixed(0)+"</td><td>"+r.z1.toFixed(0)+"</td><td class='val'>"+r.layer.toFixed(2)+"</td><td class='gd'>"+(r.theta?r.theta.toFixed(0)+"°":"—")+"</td></tr>";});
    h+="</table>";
  }
  h+="<div style='display:flex;gap:8px;margin-top:12px'><button class='btn' id='expOpt'>⬇ Xuất 2 preset tối ưu (.json)</button></div>";
  return h;
}
```

- [ ] **Step 2: Nối vào luồng phân tích**

Trong `readFile()`, sau `render(ps,geo,slice,findings,file.name);` thêm:
```js
   if(feat){
     const L=printerLimits(ps);
     const plan=optimize(feat,L,$("#mat").value,$("#uc").value,ps);
     $("#result").insertAdjacentHTML("beforeend",renderPlan(plan));
     const b=$("#expOpt"); if(b)b.addEventListener("click",()=>downloadOptimized(plan));
   }
```

- [ ] **Step 3: Hàm xuất preset**

```js
function downloadOptimized(P){
  const stamp=n=>({from:"User",version:"2.7.0.8",name:n});
  const proc=Object.assign({},stamp("BambuLab - AUTO - Optimized"),{
    inherits:"0.20mm Standard @BBL A1",
    print_settings_id:"BambuLab - AUTO - Optimized",
    print_extruder_id:["1"], print_extruder_variant:["Direct Drive Standard"],
  },shapeFix(P.deltaProcess));
  const fil=Object.assign({},stamp("BambuLab - AUTO - Optimized"),{
    inherits:"Bambu PLA Matte @BBL A1",
    filament_settings_id:["BambuLab - AUTO - Optimized"],
    filament_extruder_variant:["Direct Drive Standard"],
  },shapeFix(P.deltaFilament,true));
  dl(proc,"AUTO-optimized-process.json"); dl(fil,"AUTO-optimized-filament.json");
}
/* Các key kiểu coFloats/coInts phải là MẢNG, khớp shape của project_settings.config */
const ARRAY_KEYS=new Set(["initial_layer_speed","inner_wall_speed","sparse_infill_speed",
  "internal_solid_infill_speed","top_surface_speed","overhang_fan_speed",
  "close_fan_the_first_x_layers","textured_plate_temp","filament_scarf_seam_type"]);
function shapeFix(o){
  const r={};
  for(const k in o)r[k]=ARRAY_KEYS.has(k)?[String(o[k])]:String(o[k]);
  return r;
}
function dl(obj,name){
  const b=new Blob([JSON.stringify(obj,null,4)],{type:"application/json"});
  const a=document.createElement("a"); a.href=URL.createObjectURL(b); a.download=name; a.click();
  setTimeout(()=>URL.revokeObjectURL(a.href),1000);
}
```

- [ ] **Step 4: Chạy e2e + validate**

Run:
```bash
SP=/c/Users/PHILON~1.PHA/AppData/Local/Temp/claude/d--56-BambuStudio/b1acb35c-9276-4bf4-aff4-1a3cb0210fd5/scratchpad
cd "$SP" && node e2e.js | tail -2 && node newrules.js | tail -2 && node validate.js | tail -3
```
Expected: `E2E: 63 passed, 0 failed` · `10 file · lệch 0 · pageerror 0` · `preset files: 0 key sai`

- [ ] **Step 5: Commit**

```bash
git add BambuLab-A1-Hub.html
git commit -m "feat: UI bảng quyết định có nguồn + bảng Height range + xuất 2 preset tối ưu"
```

---

## Task 13: E2E trên file thật + chốt

**Files:**
- Create: `tests/e2e-optimizer.js` (puppeteer, chạy tay)

- [ ] **Step 1: Viết e2e**

```js
'use strict';
const puppeteer = require('puppeteer-core');
const CHROME = 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe';
const URL = 'file:///D:/56.BambuStudio/BambuLab-A1-Hub.html';
const FILE = process.argv[2] || 'C:\\Users\\philong.pham\\Downloads\\Body 14 - LP.3mf';

(async () => {
  const b = await puppeteer.launch({ executablePath: CHROME, headless: 'new', args: ['--no-sandbox'] });
  const p = await b.newPage();
  const errs = [];
  p.on('pageerror', e => errs.push(e.message));
  await p.goto(URL, { waitUntil: 'load' });
  await p.select('#mat', 'PLA Matte');
  await p.select('#uc', 'Chi tiết trang trí');
  await p.click('[data-tab="phan-tich"]');
  (await p.$('#file')).uploadFile(FILE);
  await p.waitForFunction(() => /Cấu hình tối ưu/.test(document.querySelector('#result').innerText), { timeout: 90000 });
  const out = await p.evaluate(() => {
    const rows = [...document.querySelectorAll('#result table tr')].slice(1)
      .map(tr => [...tr.querySelectorAll('td')].map(td => td.innerText.trim()));
    return { rows: rows.length, hasVlh: /Height range Modifier/.test(document.querySelector('#result').innerText) };
  });
  console.log(`rows=${out.rows}  vlhTable=${out.hasVlh}  pageerror=${errs.length}`);
  if (errs.length) console.log(errs[0]);
  await b.close();
  process.exit(errs.length ? 1 : 0);
})();
```

- [ ] **Step 2: Chạy trên file thật**

Run: `cd "$SP" && node /d/56.BambuStudio/tests/e2e-optimizer.js`
Expected: `rows > 10`, `vlhTable=true`, `pageerror=0`

- [ ] **Step 3: Chạy toàn bộ**

Run: `node --test tests/ && cd "$SP" && node e2e.js | tail -2 && node newrules.js | tail -2`
Expected: tất cả pass.

- [ ] **Step 4: Commit + push**

```bash
git add tests/e2e-optimizer.js
git commit -m "test: e2e optimizer trên file .3mf thật"
git push origin main
```

---

## Self-Review

**Spec coverage:**

| Spec | Task |
|---|---|
| §4 kiến trúc 3 đơn vị | T2, T4, T5 |
| §4b dataflow + 7 bất biến + fixpoint | T6, T10 |
| §5 geoFeatures (ohBins, zSlope, topPlateaus, firstArea, islands) | T4 |
| §6 tầng 0 hiệu chuẩn | T7 |
| §6 tầng 1 first layer | T7 |
| §6 tầng 2 warping (tách tinyContact / tallThin) | T7 |
| §6 tầng 3 bề mặt · 3b độ bền | T8 |
| §6 tầng 4 overhang 3 khoảng · bridge | T9 |
| §6 tầng 4b võng mặt trên | T8 |
| §6 tầng 5 thời gian | T10 |
| §7 bảng Height range + clamp theo goal | T9 |
| §8 đầu ra: bảng quyết định + 2 preset + Z-range | T12 |
| §9 golden 6 dạng vật + regression | T11, T13 |
| §11 sửa 2 luật auditFile trước | T1 |

**Chưa có task, cố ý bỏ (YAGNI):** `thinWall_cm2` (§5, spec đã đánh dấu bỏ trước nếu cắt scope — `arachne` luôn bật ở T8 nên không mất gì).

**Type consistency:** `geoFeatures` trả `bands.{lo,mid,hi}` và `ohBins['45-60'|'60-75'|'75-90']` — dùng đúng tên đó ở T7–T11. `optimize` trả `{deltaProcess, deltaFilament, vlhRanges, reasons, conflicts, calibration, warnings, violations, limits}` — T12 chỉ đọc đúng các trường này. `printerLimits` trả `vmax` khoá theo tên feature (`inner_wall`, …) khớp `L.width`.
