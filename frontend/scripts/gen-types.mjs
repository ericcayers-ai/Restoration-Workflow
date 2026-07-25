/**
 * Generate TypeScript types from the backend's OpenAPI schema.
 *
 * Usage:  node scripts/gen-types.mjs
 *
 * Runs the backend's dump_openapi.py to get the schema, then calls
 * openapi-typescript to generate src/lib/api-types.ts.
 */
import { execSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(__dirname, "..");
const backendRoot = path.resolve(root, "..", "backend");
const outFile = path.join(root, "src", "lib", "api-types.ts");
const tmpFile = path.join(root, "node_modules", ".tmp-openapi.json");

console.log("Dumping OpenAPI schema from backend...");
const schemaJson = execSync(
  "python scripts/dump_openapi.py",
  { cwd: backendRoot, encoding: "utf-8", maxBuffer: 10 * 1024 * 1024 },
);

fs.mkdirSync(path.dirname(tmpFile), { recursive: true });
fs.writeFileSync(tmpFile, schemaJson, "utf-8");

console.log(`Generating types to ${path.relative(root, outFile)}...`);
execSync(
  `npx openapi-typescript "${tmpFile}" --output "${outFile}"`,
  { cwd: root, stdio: "inherit" },
);

fs.unlinkSync(tmpFile);

// Add header
const content = fs.readFileSync(outFile, "utf-8");
const header = [
  "/* Auto-generated from OpenAPI schema — do not edit by hand.",
  " * Run `npm run gen-types` to regenerate.",
  " */",
  "",
].join("\n");
fs.writeFileSync(outFile, header + content, "utf-8");

console.log("Done.");
