#!/usr/bin/env node
/**
 * axe-core smoke test on the built frontend (ROADMAP.md Phase 7).
 * Requires: npm run build first.
 */
import { spawnSync } from "node:child_process";
import { createServer } from "node:http";
import { readFileSync, existsSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const root = path.dirname(fileURLToPath(import.meta.url));
const dist = path.join(root, "dist");
const indexHtml = path.join(dist, "index.html");

if (!existsSync(indexHtml)) {
  console.error("Run npm run build before npm run a11y");
  process.exit(1);
}

const mime: Record<string, string> = {
  ".html": "text/html",
  ".js": "application/javascript",
  ".css": "text/css",
  ".json": "application/json",
  ".woff2": "font/woff2",
};

const server = createServer((req, res) => {
  const url = req.url === "/" ? "/index.html" : req.url ?? "/index.html";
  const file = path.join(dist, url.split("?")[0]!);
  if (!file.startsWith(dist) || !existsSync(file)) {
    res.writeHead(404);
    res.end();
    return;
  }
  const ext = path.extname(file);
  res.writeHead(200, { "Content-Type": mime[ext] ?? "application/octet-stream" });
  res.end(readFileSync(file));
});

await new Promise<void>((resolve) => server.listen(0, "127.0.0.1", resolve));
const port = (server.address() as { port: number }).port;
const url = `http://127.0.0.1:${port}/`;

const result = spawnSync(
  "npx",
  ["@axe-core/cli", url, "--exit", "--tags", "wcag2a,wcag2aa"],
  { stdio: "inherit", shell: true },
);
server.close();
process.exit(result.status ?? 1);
