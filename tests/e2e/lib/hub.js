"use strict";
/*
 * E2E helper cho BambuLab-A1-Hub.html
 * - launch()            : mở Chrome (puppeteer-core, headless)
 * - openHub(browser)    : mở 1 tab mới -> {page, errors}; errors bắt mọi pageerror
 * - analyze(page, path) : sang tab "phan-tich", upload .3mf, chờ #result render xong
 * - close(browser)      : đóng browser
 * - Suite               : bộ đếm assertion tối giản (không phụ thuộc node:test)
 */
const path = require("path");
const puppeteer = require("puppeteer-core");

const CHROME = "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe";
const HUB_URL = "file:///D:/56.BambuStudio/BambuLab-A1-Hub.html";
const DOWNLOADS = "C:\\Users\\philong.pham\\Downloads";
const ANALYZE_TIMEOUT = 90000; // file mesh lớn

function fixture(name) {
  return path.join(DOWNLOADS, name);
}

async function launch() {
  return puppeteer.launch({
    executablePath: CHROME,
    headless: true,
    args: ["--no-sandbox", "--disable-gpu", "--disable-dev-shm-usage"],
  });
}

async function openHub(browser) {
  const page = await browser.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push(String((e && e.message) || e)));
  await page.goto(HUB_URL, { waitUntil: "load", timeout: 60000 });
  await page.waitForSelector("button[data-tab]", { timeout: 30000 });
  return { page, errors };
}

async function analyze(page, filePath) {
  await page.click('button[data-tab="phan-tich"]');
  await page.waitForSelector("#file", { timeout: 10000 });
  const input = await page.$("#file");
  await input.uploadFile(filePath);
  await page.waitForFunction(
    () => {
      const r = document.querySelector("#result");
      if (!r) return false;
      const t = r.textContent || "";
      return /Kết quả|Lỗi đọc|Không đọc/.test(t);
    },
    { timeout: ANALYZE_TIMEOUT }
  );
}

async function close(browser) {
  if (browser) await browser.close();
}

/* ---- assertion collector tối giản ---- */
class Suite {
  constructor(name) {
    this.name = name;
    this.checks = [];
  }
  check(label, ok, detail) {
    this.checks.push({ label, ok: !!ok, detail: ok ? "" : String(detail == null ? "" : detail) });
    return !!ok;
  }
  eq(label, actual, expected, detail) {
    const ok = actual === expected;
    const d = detail != null ? detail : `kỳ vọng ${JSON.stringify(expected)}, thực tế ${JSON.stringify(actual)}`;
    return this.check(label, ok, d);
  }
  get pass() {
    return this.checks.filter((c) => c.ok).length;
  }
  get fail() {
    return this.checks.filter((c) => !c.ok).length;
  }
}

module.exports = { launch, openHub, analyze, close, Suite, fixture, HUB_URL, DOWNLOADS, ANALYZE_TIMEOUT };
