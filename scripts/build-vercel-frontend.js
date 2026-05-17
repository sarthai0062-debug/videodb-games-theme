#!/usr/bin/env node
/**
 * Build static frontend for Vercel.
 * Set VIDEODB_API_BASE to your Render API URL (no trailing slash).
 */
const fs = require("fs");
const path = require("path");

const root = path.resolve(__dirname, "..");
const staticDir = path.join(root, "static");
const distDir = path.join(root, "dist");
const apiBase = (process.env.VIDEODB_API_BASE || "").replace(/\/$/, "");

if (!apiBase) {
  console.warn(
    "WARN: VIDEODB_API_BASE is empty — frontend will call same-origin /api (broken on Vercel). Set it in Vercel project env."
  );
}

fs.rmSync(distDir, { recursive: true, force: true });
fs.mkdirSync(distDir, { recursive: true });

for (const name of ["style.css", "app.js"]) {
  fs.copyFileSync(path.join(staticDir, name), path.join(distDir, name));
}

let indexOut = fs.readFileSync(path.join(staticDir, "index.html"), "utf8");
indexOut = indexOut.replace(/href="\/static\/style\.css[^"]*"/, 'href="./style.css"');
indexOut = indexOut.replace(/\s*<script src="\/static\/config\.js[^"]*"><\/script>\s*/g, "\n");
indexOut = indexOut.replace(
  /\s*<script src="\/static\/app\.js[^"]*"><\/script>\s*/,
  '\n  <script src="./config.js"></script>\n  <script src="./app.js"></script>\n'
);
fs.writeFileSync(path.join(distDir, "index.html"), indexOut);

const configJs = `window.__API_BASE__ = ${JSON.stringify(apiBase)};\n`;
fs.writeFileSync(path.join(distDir, "config.js"), configJs);

console.log(`Built frontend → dist/ (API base: ${apiBase || "(empty)"})`);
