// SPDX-License-Identifier: AGPL-3.0-or-later
// Render a GLB into a six-view lit contact sheet with three.js in headless Chromium.
//   node render.mjs <model.glb> <out.png> [title]
// Chromium comes from MODULARACK_CHROMIUM, else the newest build in the Playwright cache.

import { createReadStream, existsSync, readdirSync } from "node:fs";
import { createServer } from "node:http";
import { homedir, userInfo } from "node:os";
import { extname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright-core";

const HERE = fileURLToPath(new URL(".", import.meta.url));
const RENDER_TIMEOUT_MS = 300_000;
const VIEW_SIZE = 640;
const TYPES = { ".html": "text/html", ".js": "text/javascript", ".glb": "model/gltf-binary" };

function chromiumPath() {
  if (process.env.MODULARACK_CHROMIUM) return process.env.MODULARACK_CHROMIUM;
  // $HOME may be a per-session directory; the shared Playwright cache sits under the real home.
  const caches = [
    process.env.PLAYWRIGHT_BROWSERS_PATH,
    join(homedir(), ".cache", "ms-playwright"),
    join(userInfo().homedir, ".cache", "ms-playwright"),
  ].filter((cache) => cache && existsSync(cache));
  for (const cache of caches) {
    const builds = readdirSync(cache).filter((d) => /^chromium-\d+$/.test(d)).sort().reverse();
    for (const build of builds) {
      for (const folder of ["chrome-linux64", "chrome-linux"]) {
        const binary = join(cache, build, folder, "chrome");
        if (existsSync(binary)) return binary;
      }
    }
  }
  throw new Error(`No Chromium build in ${caches.join(", ")}; set MODULARACK_CHROMIUM`);
}

const [modelPath, outPath, title = ""] = process.argv.slice(2);
if (!modelPath || !outPath) throw new Error("usage: node render.mjs <model.glb> <out.png> [title]");
const model = resolve(modelPath);

const server = createServer((request, response) => {
  const path = decodeURIComponent(new URL(request.url, "http://x").pathname);
  const file = path === "/model.glb" ? model : join(HERE, path);
  if (!file.startsWith(HERE) && file !== model) return response.writeHead(403).end();
  if (!existsSync(file)) return response.writeHead(404).end();
  response.writeHead(200, { "Content-Type": TYPES[extname(file)] ?? "application/octet-stream" });
  createReadStream(file).pipe(response);
});
await new Promise((ok) => server.listen(0, "127.0.0.1", ok));
const port = server.address().port;

const browser = await chromium.launch({ executablePath: chromiumPath(), args: ["--use-angle=swiftshader", "--enable-unsafe-swiftshader"] });
try {
  const page = await browser.newPage({ viewport: { width: VIEW_SIZE * 3, height: VIEW_SIZE * 2 + 100 } });
  page.on("pageerror", (error) => console.error(error));
  const query = new URLSearchParams({ model: "/model.glb", title, size: String(VIEW_SIZE) });
  await page.goto(`http://127.0.0.1:${port}/viewer.html?${query}`);
  await page.waitForFunction(() => window.renderDone === true, null, { timeout: RENDER_TIMEOUT_MS });
  // The scene is drawn by now; a big model in software GL can still take Playwright past its 30 s default.
  await page.locator("canvas").screenshot({ path: resolve(outPath), timeout: RENDER_TIMEOUT_MS });
} finally {
  await browser.close();
  server.close();
}
