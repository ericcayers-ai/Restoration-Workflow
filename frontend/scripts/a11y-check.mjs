#!/usr/bin/env node
/**
 * axe-core smoke test on the built frontend (ROADMAP.md Phase 7).
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
const url = `http://127.0.0.1:${port}/`;

const browser = await puppeteer.launch({
  headless: true,
  args: ["--disable-gpu", "--no-sandbox", "--disable-dev-shm-usage"],
});
try {
  const page = await browser.newPage();
  await page.goto(url, { waitUntil: "networkidle0", timeout: 60_000 });
  await page.waitForSelector("#root", { timeout: 15_000 });
  const results = await new AxePuppeteer(page)
    .withTags(["wcag2a", "wcag2aa"])
    .analyze();

  const blocking = results.violations.filter((v) =>
    ["critical", "serious"].includes(v.impact ?? ""),
  );
  if (blocking.length > 0) {
    for (const v of blocking) {
      console.error(`[${v.impact}] ${v.id}: ${v.help}`);
      for (const node of v.nodes.slice(0, 3)) {
        console.error(`  - ${node.html}`);
      }
    }
    process.exitCode = 1;
  } else {
    console.log(
      `axe-core: ${results.violations.length} violations (${blocking.length} critical/serious)`,
    );
  }
} finally {
  await browser.close();
  server.close();
}

process.exit(process.exitCode ?? 0);
