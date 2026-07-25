/**
 * Manual UI walkthrough against a running Vite + API stack.
 * Captures screenshots for each mode/state.
 */
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import puppeteer from "puppeteer";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(__dirname, "../..");
const outDir = path.join(root, "docs", "screenshots", "qa", "walkthrough");
const base = process.env.RW_UI_URL || "http://127.0.0.1:5173";
const qaImage = path.join(root, "frontend", "public", "qa", "Scan_12.png");

fs.mkdirSync(outDir, { recursive: true });

async function shot(page, name) {
  const file = path.join(outDir, `${name}.png`);
  await page.screenshot({ path: file, fullPage: false });
  return file;
}

async function measure(page, mode) {
  return page.evaluate((modeName) => {
    const main = document.querySelector("main");
    const panes = Array.from(document.querySelectorAll("[data-mode-pane]"));
    const visible = panes.find((p) => p.style.display !== "none") ?? null;
    const fileInputs = Array.from(document.querySelectorAll('input[type="file"]')).map((el) => {
      const input = /** @type {HTMLInputElement} */ (el);
      return {
        accept: input.accept,
        multiple: input.multiple,
        webkitdirectory: input.hasAttribute("webkitdirectory"),
        aria: input.getAttribute("aria-label"),
        inVisiblePane: Boolean(visible?.contains(input)),
      };
    });
    const rect = (el) => {
      if (!el) return null;
      const r = el.getBoundingClientRect();
      return {
        w: Math.round(r.width),
        h: Math.round(r.height),
        top: Math.round(r.top),
        left: Math.round(r.left),
      };
    };
    return {
      mode: modeName,
      viewport: { w: window.innerWidth, h: window.innerHeight },
      main: rect(main),
      visiblePane: rect(visible),
      visiblePaneOverflow: visible
        ? {
            scrollW: visible.scrollWidth,
            clientW: visible.clientWidth,
            scrollH: visible.scrollHeight,
            clientH: visible.clientHeight,
          }
        : null,
      fileInputs,
      bodyOverflowX: document.body.scrollWidth > window.innerWidth + 2,
      selectedTab: document.querySelector('[role="tab"][aria-selected="true"]')?.textContent?.trim(),
      dialog: rect(document.querySelector('[role="dialog"]')),
    };
  }, mode);
}

async function setFileOnInput(page, selector, filePath) {
  const input = await page.$(selector);
  if (!input) throw new Error(`Missing input: ${selector}`);
  await input.uploadFile(filePath);
}

async function clickTab(page, name) {
  await page.evaluate((label) => {
    const tabs = Array.from(document.querySelectorAll('[role="tab"]'));
    const tab = tabs.find((t) => t.textContent?.trim() === label);
    if (!tab) throw new Error(`tab ${label} missing`);
    tab.click();
  }, name);
  await page.waitForFunction(
    (label) =>
      document.querySelector('[role="tab"][aria-selected="true"]')?.textContent?.trim() === label,
    {},
    name,
  );
}

const browser = await puppeteer.launch({
  headless: true,
  defaultViewport: { width: 1440, height: 900 },
  args: ["--no-sandbox"],
});

const page = await browser.newPage();
page.setDefaultTimeout(45000);

try {
  await page.goto(base, { waitUntil: "networkidle0" });
  console.log("simple idle desktop");
  await shot(page, "01-simple-idle");

  // H-E: inspect simple dropzone file input attrs before upload
  const simpleInputs = await page.evaluate(() => {
    const pane = document.querySelector('[data-mode-pane="simple"]');
    return Array.from(pane?.querySelectorAll('input[type="file"]') ?? []).map((i) => ({
      accept: i.accept,
      multiple: i.multiple,
      webkitdirectory: i.hasAttribute("webkitdirectory"),
    }));
  });
  console.log("simple file inputs:", JSON.stringify(simpleInputs));

  // Primary photo picker must NOT be webkitdirectory (H-E); folder is a separate control.
  const simpleFileSel =
    '[data-mode-pane="simple"] input[type="file"]:not([webkitdirectory])';
  await setFileOnInput(page, simpleFileSel, qaImage);
  await page.waitForFunction(() => document.body.innerText.includes("Review workflow"), {
    timeout: 60000,
  });
  console.log("simple review after Scan_12");
  await shot(page, "02-simple-review");

  // Open stage inspector
  await page.evaluate(() => {
    const stage = Array.from(document.querySelectorAll("button")).find((b) =>
      /RealESRGAN stage/i.test(b.getAttribute("aria-label") || b.textContent || ""),
    );
    stage?.click();
  });
  await page.waitForFunction(() => /Upscale factor|Tile size/i.test(document.body.innerText));
  await shot(page, "03-simple-review-inspector");

  // Studio
  await clickTab(page, "Studio");
  console.log("studio empty");
  await shot(page, "04-studio-empty");

  await setFileOnInput(
    page,
    '[data-mode-pane="studio"] input[type="file"][accept*="png"]:not([webkitdirectory])',
    qaImage,
  );
  await page.waitForFunction(() => /Scan_12\.png/.test(document.body.innerText), {
    timeout: 15000,
  });
  // Add RealESRGAN
  await page.evaluate(() => {
    const btn = Array.from(document.querySelectorAll('[data-mode-pane="studio"] button')).find(
      (b) => (b.getAttribute("aria-label") || b.textContent || "").trim() === "RealESRGAN",
    );
    btn?.click();
  });
  await page.waitForFunction(() => /1\s*RealESRGAN|RealESRGAN stage/i.test(document.body.innerText));
  console.log("studio with photo + stage");
  await shot(page, "05-studio-loaded");

  // Graph editor
  await page.evaluate(() => {
    const tab = Array.from(document.querySelectorAll('[role="tab"]')).find(
      (t) => t.textContent?.trim() === "Graph",
    );
    tab?.click();
  });
  await page.waitForFunction(
    () =>
      document.querySelector('[role="tab"][aria-selected="true"]')?.textContent?.trim() === "Graph" ||
      /Graph|canvas|node/i.test(document.body.innerText),
  );
  await shot(page, "06-studio-graph");
  console.log("studio graph mode");

  // Mask
  await clickTab(page, "Mask");
  console.log("mask idle");
  await shot(page, "07-mask-idle");

  await setFileOnInput(page, '[data-mode-pane="mask"] input[type="file"]', qaImage);
  await page.waitForFunction(() => /Brush|Erase|Inpaint|Export/i.test(document.body.innerText), {
    timeout: 20000,
  });
  // allow canvases to init
  await new Promise((r) => setTimeout(r, 500));
  const maskMetrics = await page.evaluate(() => {
    const overlay = document.querySelector('[data-mode-pane="mask"] canvas[role="img"]');
    const stage = document.querySelector('[data-mode-pane="mask"]');
    const r = overlay?.getBoundingClientRect();
    return {
      natural: overlay ? { w: /** @type {HTMLCanvasElement} */ (overlay).width, h: /** @type {HTMLCanvasElement} */ (overlay).height } : null,
      bounds: r
        ? { w: Math.round(r.width), h: Math.round(r.height), top: Math.round(r.top), left: Math.round(r.left) }
        : null,
      stageScroll: stage
        ? { scrollW: stage.scrollWidth, clientW: stage.clientWidth, scrollH: stage.scrollHeight, clientH: stage.clientHeight }
        : null,
    };
  });
  console.log("mask with Scan_12");
  await shot(page, "08-mask-loaded");

  // Settings tabs
  await page.click('button[aria-label="Settings"]');
  await page.waitForSelector('[role="dialog"]');
  console.log("settings downloads");
  await shot(page, "09-settings-downloads");

  await page.evaluate(() => {
    document.getElementById("settings-tab-vision")?.click();
  });
  await new Promise((r) => setTimeout(r, 300));
  await shot(page, "10-settings-vision");
  console.log("settings vision");

  await page.evaluate(() => {
    document.getElementById("settings-tab-legacy")?.click();
  });
  await new Promise((r) => setTimeout(r, 300));
  await shot(page, "11-settings-legacy");
  console.log("settings legacy");

  // Close settings
  await page.keyboard.press("Escape");
  await page.waitForFunction(() => !document.querySelector('[role="dialog"]'));

  // Narrow viewport
  await page.setViewport({ width: 720, height: 900 });
  await clickTab(page, "Simple");
  await new Promise((r) => setTimeout(r, 300));
  console.log("simple review narrow");
  await shot(page, "12-simple-review-narrow");

  await clickTab(page, "Studio");
  await new Promise((r) => setTimeout(r, 300));
  console.log("studio narrow");
  await shot(page, "13-studio-narrow");

  await clickTab(page, "Mask");
  await new Promise((r) => setTimeout(r, 300));
  console.log("mask narrow");
  await shot(page, "14-mask-narrow");

  // Light theme spot check
  await page.setViewport({ width: 1440, height: 900 });
  await clickTab(page, "Simple");
  await page.evaluate(() => {
    const light = Array.from(document.querySelectorAll('[role="radio"]')).find(
      (r) => r.textContent?.trim() === "Light",
    );
    light?.click();
  });
  await new Promise((r) => setTimeout(r, 300));
  await shot(page, "15-simple-light");
  console.log("simple light theme");

  console.log(JSON.stringify({ ok: true, outDir }, null, 2));
} catch (err) {
  console.error("walkthrough error:", String(err).slice(0, 200));
  await shot(page, "99-error").catch(() => {});
  console.error(err);
  process.exitCode = 1;
} finally {
  await browser.close();
}
