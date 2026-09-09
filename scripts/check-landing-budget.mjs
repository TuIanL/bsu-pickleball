/* global console */

import { gzipSync } from "node:zlib";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

const dist = resolve("dist");
const manifestPath = resolve(dist, ".vite/manifest.json");
const manifest = JSON.parse(readFileSync(manifestPath, "utf8"));
const entry = manifest["index.html"];
if (!entry) throw new Error("Vite manifest does not contain index.html");

const visited = new Set();
const files = [];
function visit(key) {
  if (!key || visited.has(key)) return;
  visited.add(key);
  const chunk = manifest[key];
  if (!chunk) return;
  if (chunk.file?.endsWith(".js")) files.push(chunk.file);
  for (const imported of chunk.imports ?? []) visit(imported);
}
visit("index.html");
// The landing route is lazy, but its static dependency closure is still a cold-load cost.
for (const key of Object.keys(manifest)) {
  if (/\/LandingPage\.[jt]sx?$/.test(key)) visit(key);
}

const jsBytes = files.reduce((sum, file) => sum + gzipSync(readFileSync(resolve(dist, file))).length, 0);
const cssFiles = [...new Set(Object.values(manifest).flatMap((chunk) => chunk.css ?? []))];
const cssBytes = cssFiles.reduce((sum, file) => sum + gzipSync(readFileSync(resolve(dist, file))).length, 0);
const dynamicFiles = Object.values(manifest)
  .filter((chunk) => chunk.isDynamicEntry && chunk.file?.endsWith(".js"))
  .map((chunk) => ({ file: chunk.file, gzipBytes: gzipSync(readFileSync(resolve(dist, chunk.file))).length }));

console.log(JSON.stringify({ landingStaticJsGzipBytes: jsBytes, cssGzipBytes: cssBytes, dynamicFiles }, null, 2));
if (jsBytes > 350 * 1024) {
  throw new Error(`landing static JS gzip budget exceeded: ${jsBytes} > ${350 * 1024}`);
}
