"use strict";
/* Chạy tuần tự 01/02/03, in pass/fail thật, exit code = (fail?1:0) */
const suites = [
  require("./01-smoke.e2e"),
  require("./02-analyze.e2e"),
  require("./03-time.e2e"),
  require("./04-fixtures.e2e"),
  require("./05-optimizer.e2e"),
];

(async () => {
  let totalPass = 0;
  let totalFail = 0;
  const t0 = Date.now();

  for (const runSuite of suites) {
    let s;
    try {
      s = await runSuite();
    } catch (e) {
      console.log(`\n### SUITE CRASHED: ${(e && e.stack) || e}`);
      totalFail += 1;
      continue;
    }
    console.log(`\n=== ${s.name} ===`);
    for (const c of s.checks) {
      if (c.ok) {
        console.log(`  PASS  ${c.label}`);
      } else {
        console.log(`  FAIL  ${c.label}`);
        if (c.detail) console.log(`        ↳ ${c.detail}`);
      }
    }
    console.log(`  -- ${s.name}: ${s.pass} pass / ${s.fail} fail`);
    totalPass += s.pass;
    totalFail += s.fail;
  }

  const secs = ((Date.now() - t0) / 1000).toFixed(1);
  console.log(`\n==================================================`);
  console.log(`TOTAL: ${totalPass} pass / ${totalFail} fail   (${secs}s)`);
  console.log(`==================================================`);
  process.exit(totalFail ? 1 : 0);
})();
