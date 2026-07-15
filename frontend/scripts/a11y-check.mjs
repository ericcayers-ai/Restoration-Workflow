#!/usr/bin/env node
/**
 * axe-core smoke test on the built frontend (ROADMAP.md Phase 7).
 * Exercises empty shell, Settings dialog, Simple review, and InstructIR
 * Inspector (including ensemble confirm) with mocked /api responses.
 * Requires: npm run build first.
 */
import { createServer } from "node:http";
import { readFileSync, existsSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import puppeteer from "puppeteer";
import { AxePuppeteer } from "@axe-core/puppeteer";

const root = path.dirname(fileURLToPath(import.meta.url));
const dist = path.join(root, "..", "dist");
const indexHtml = path.join(dist, "index.html");

if (!existsSync(indexHtml)) {
  console.error("Run npm run build before npm run a11y");
  process.exit(1);
}

/** @type {Record<string, string>} */
const mime = {
  ".html": "text/html",
  ".js": "application/javascript",
  ".css": "text/css",
  ".json": "application/json",
  ".woff2": "font/woff2",
};

const server = createServer((req, res) => {
  const url = req.url === "/" ? "/index.html" : req.url ?? "/index.html";
  const file = path.join(dist, url.split("?")[0]);
  if (!file.startsWith(dist) || !existsSync(file)) {
    res.writeHead(404);
    res.end();
    return;
  }
  const ext = path.extname(file);
  res.writeHead(200, { "Content-Type": mime[ext] ?? "application/octet-stream" });
  res.end(readFileSync(file));
});

await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
const addr = server.address();
const port = typeof addr === "object" && addr ? addr.port : 0;
const origin = `http://127.0.0.1:${port}/`;

function weightsStatus(nodeId) {
  return {
    node_id: nodeId,
    installed: true,
    files: [],
    total_size_bytes: 0,
    missing_size_bytes: 0,
    acknowledged: true,
    requires_acknowledgement: false,
  };
}

function describedNode(id, displayName, category = "regression") {
  const instructParams =
    id === "instructir"
      ? {
          prompt_preset: {
            type: "string",
            enum: ["instruct_only_general", "custom"],
            default: "instruct_only_general",
            title: "Prompt preset",
          },
          instruction: {
            type: "string",
            default: "Restore this photograph.",
            title: "Custom instruction",
          },
          mode: {
            type: "string",
            enum: ["finish_only", "instruct_only", "guide_and_finish"],
            default: "finish_only",
            title: "Master mode",
          },
          mask_highlights: { type: "boolean", default: false, title: "Mask highlights" },
        }
      : { strength: { type: "number", minimum: 0, maximum: 1, default: 1, title: "Strength" } };

  return {
    id,
    display_name: displayName,
    description: `${displayName} (a11y mock)`,
    category,
    license: {
      spdx_id: "MIT",
      kind: "permissive",
      source_url: "https://example.invalid/LICENSE",
      requires_acknowledgement: false,
    },
    vram_tier: "low",
    param_schema: { type: "object", properties: instructParams },
    weight_manifest: [],
    supports_tiling: false,
    uses_gpu: false,
    availability: { state: "available", reason: null, badge: null },
    weights: weightsStatus(id),
  };
}

const MOCK_NODES = [
  describedNode("instructir", "InstructIR", "instruct"),
  describedNode("realesrgan", "Real-ESRGAN"),
  describedNode("scunet", "SCUNet"),
  describedNode("ddcolor", "DDColor"),
];

const MOCK_PROMPTS = {
  count: 2,
  presets: [
    {
      id: "instruct_only_general",
      title: "General restore",
      instruction: "Restore this photograph.",
      category: "general",
    },
    {
      id: "blown_highlight_rescue",
      title: "Blown Highlight Rescue",
      instruction: "Recover blown highlights.",
      category: "exposure",
    },
  ],
};

/**
 * @param {import('puppeteer').Page} page
 */
async function installApiMocks(page) {
  await page.setRequestInterception(true);
  page.on("request", (req) => {
    const u = req.url();
    if (!u.includes("/api/")) {
      req.continue();
      return;
    }
    const method = req.method();
    const pathOnly = new URL(u).pathname;

    const json = (body, status = 200) =>
      req.respond({
        status,
        contentType: "application/json",
        body: JSON.stringify(body),
      });

    if (pathOnly === "/api/nodes" && method === "GET") return json(MOCK_NODES);
    if (pathOnly.startsWith("/api/nodes/") && method === "GET") {
      const id = pathOnly.split("/").pop();
      const node = MOCK_NODES.find((n) => n.id === id);
      return node ? json(node) : json({ detail: "unknown" }, 400);
    }
    if (pathOnly === "/api/presets" && method === "GET") return json([]);
    if (pathOnly === "/api/weights" && method === "GET") {
      return json({
        cache_dir: "/tmp/weights",
        free_bytes: 50_000_000_000,
        nodes: MOCK_NODES.map((n) => ({
          node_id: n.id,
          display_name: n.display_name,
          ...n.weights,
          license: n.license,
        })),
      });
    }
    if (pathOnly === "/api/hardware" && method === "GET") {
      return json({ backend: "cpu", devices: [], recommended_quality_tier: "balanced" });
    }
    if (pathOnly === "/api/health" && method === "GET") {
      return json({ status: "ok", version: "0.6.0", api_version: "1.0.0", plugin_errors: [] });
    }
    if (pathOnly === "/api/instructir/prompts" && method === "GET") return json(MOCK_PROMPTS);
    if (pathOnly === "/api/analyze" && method === "POST") {
      return json({
        profile: {
          width: 64,
          height: 64,
          min_dimension: 64,
          blur_score: 100,
          noise_score: 0.01,
          jpeg_blockiness: 0,
          mean_luma: 0.5,
          dark_fraction: 0,
          bright_fraction: 0,
          face_count: 0,
          low_light: false,
          blown_highlights: false,
        },
        routing: {
          chain: ["realesrgan"],
          params: { realesrgan: { scale: 2 } },
          reasons: [{ node: "realesrgan", reason: "a11y mock route" }],
        },
        pipeline: {
          version: 1,
          nodes: [{ id: "u1", type: "realesrgan", params: { scale: 2 }, pinned: false }],
          edges: [],
        },
        missing_weights: [],
      });
    }
    if (pathOnly === "/api/pipelines/ensemble" && method === "POST") {
      return json({
        chain: ["scunet", "instructir"],
        instruction: "Restore this photograph.",
        mode: "guide_and_finish",
        reasons: [{ node: "instructir", reason: "a11y mock ensemble" }],
        pipeline: {
          version: 1,
          nodes: [
            { id: "s1", type: "scunet", params: {}, pinned: false },
            { id: "i1", type: "instructir", params: {}, pinned: false },
          ],
          edges: [{ from: "s1", to: "i1", to_input: "image" }],
        },
      });
    }
    return json({});
  });
}

/**
 * @param {import('puppeteer').Page} page
 * @param {string} label
 */
async function analyzeAxe(page, label) {
  const results = await new AxePuppeteer(page).withTags(["wcag2a", "wcag2aa"]).analyze();
  const blocking = results.violations.filter((v) =>
    ["critical", "serious"].includes(v.impact ?? ""),
  );
  if (blocking.length > 0) {
    console.error(`\n[${label}] ${blocking.length} critical/serious violation(s):`);
    for (const v of blocking) {
      console.error(`  [${v.impact}] ${v.id}: ${v.help}`);
      for (const node of v.nodes.slice(0, 3)) {
        console.error(`    - ${node.html}`);
      }
    }
    return false;
  }
  console.log(
    `[${label}] axe-core OK (${results.violations.length} non-blocking violation(s))`,
  );
  return true;
}

const browser = await puppeteer.launch({
  headless: true,
  args: ["--disable-gpu", "--no-sandbox", "--disable-dev-shm-usage"],
});

let ok = true;
try {
  const page = await browser.newPage();
  await page.setViewport({ width: 1440, height: 900 });
  await installApiMocks(page);
  await page.goto(origin, { waitUntil: "networkidle0", timeout: 60_000 });
  await page.waitForSelector("#root", { timeout: 15_000 });

  // 1) Empty shell
  ok = (await analyzeAxe(page, "empty-shell")) && ok;

  // 2) Settings dialog
  await page.click('button[aria-label="Settings"]');
  await page.waitForSelector('[role="dialog"][aria-label="Settings"]', { timeout: 10_000 });
  ok = (await analyzeAxe(page, "settings-dialog")) && ok;
  await page.click('button[aria-label="Close"]');
  await page.waitForFunction(
    () => !document.querySelector('[role="dialog"][aria-label="Settings"]'),
  );

  // 3) Simple review after analyze — inject a File (webkitdirectory inputs
  // resist Puppeteer's uploadFile for a single PNG path).
  await page.evaluate(async () => {
    const input = document.querySelector('input[type="file"]');
    if (!input) throw new Error("no file input");
    const bytes = Uint8Array.from(
      atob(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==",
      ),
      (c) => c.charCodeAt(0),
    );
    const file = new File([bytes], "sample.png", { type: "image/png" });
    const dt = new DataTransfer();
    dt.items.add(file);
    input.files = dt.files;
    input.dispatchEvent(new Event("change", { bubbles: true }));
  });
  await page.waitForFunction(
    () => document.body.innerText.includes("Review the workflow"),
    { timeout: 15_000 },
  );
  ok = (await analyzeAxe(page, "simple-review")) && ok;

  // 4) Studio InstructIR Inspector (+ ensemble confirm)
  // Scope to the visible mode pane — Simple stays mounted (display:none) and
  // would otherwise steal the InstructIR click.
  const visiblePane = async () => {
    await page.waitForFunction(() => {
      const panes = Array.from(document.querySelectorAll("main > div"));
      return panes.some((el) => window.getComputedStyle(el).display !== "none");
    });
  };

  await page.evaluate(() => {
    const tabs = Array.from(document.querySelectorAll('button[role="tab"]'));
    const studio = tabs.find((b) => (b.textContent || "").trim() === "Studio");
    studio?.click();
  });
  await visiblePane();
  await page.waitForFunction(
    () => {
      const panes = Array.from(document.querySelectorAll("main > div"));
      const visible = panes.find((el) => window.getComputedStyle(el).display !== "none");
      return Boolean(visible?.querySelector('aside[aria-label="Model Stack"]'));
    },
    { timeout: 15_000 },
  );

  await page.evaluate(() => {
    const panes = Array.from(document.querySelectorAll("main > div"));
    const visible = panes.find((el) => window.getComputedStyle(el).display !== "none");
    if (!visible) throw new Error("no visible mode pane");
    const instruct = Array.from(visible.querySelectorAll("button")).find((b) =>
      (b.getAttribute("aria-label") || b.textContent || "").includes("InstructIR"),
    );
    if (!instruct) throw new Error("InstructIR rail button not found in Studio");
    instruct.click();
  });
  await page.waitForFunction(
    () => {
      const panes = Array.from(document.querySelectorAll("main > div"));
      const visible = panes.find((el) => window.getComputedStyle(el).display !== "none");
      return Boolean(visible && visible.innerText.includes("Master Restorer"));
    },
    { timeout: 15_000 },
  );
  ok = (await analyzeAxe(page, "instructir-inspector")) && ok;

  await page.evaluate(() => {
    const panes = Array.from(document.querySelectorAll("main > div"));
    const visible = panes.find((el) => window.getComputedStyle(el).display !== "none");
    const ensemble = Array.from(visible?.querySelectorAll("button") ?? []).find((b) =>
      (b.textContent || "").includes("Build guided ensemble"),
    );
    if (!ensemble) throw new Error("Build guided ensemble button not found");
    ensemble.click();
  });
  await page.waitForSelector('[role="alertdialog"]', { timeout: 10_000 });
  ok = (await analyzeAxe(page, "instructir-ensemble-confirm")) && ok;
} catch (err) {
  console.error(err);
  try {
    const body = await page.evaluate(() => document.body.innerText.slice(0, 1200));
    console.error("page text snippet:\n", body);
  } catch {
    /* ignore */
  }
  ok = false;
} finally {
  await browser.close();
  server.close();
}

process.exit(ok ? 0 : 1);
