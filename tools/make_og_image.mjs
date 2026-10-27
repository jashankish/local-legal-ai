// Render the web demo's link-preview images.
//
//   web/og-image.png          1200×630  Open Graph / Twitter card (iMessage, Slack, …)
//   web/apple-touch-icon.png  180×180   home-screen and fallback link icon
//
// Both come from sources in the repo (tools/og-card.html, web/favicon.svg), so
// change those and rerun; never edit the PNGs by hand.
//
//   npm i --no-save playwright@1.55.0 && npx playwright install chromium
//   node tools/make_og_image.mjs

import { readFile, stat } from "node:fs/promises";
import { fileURLToPath, pathToFileURL } from "node:url";
import { dirname, join } from "node:path";
import { chromium } from "playwright";

const ROOT = join(dirname(fileURLToPath(import.meta.url)), "..");
const WEB = join(ROOT, "web");

const browser = await chromium.launch();

async function render(target, { url, html, width, height }) {
  const page = await browser.newPage({ viewport: { width, height }, deviceScaleFactor: 1 });
  if (url) await page.goto(url, { waitUntil: "load" });
  else await page.setContent(html, { waitUntil: "load" });
  await page.screenshot({ path: target, type: "png", omitBackground: false });
  await page.close();
  const { size } = await stat(target);
  console.log(`  ${target.replace(`${ROOT}/`, "")}  ${width}×${height}  ${(size / 1024).toFixed(0)} KB`);
}

await render(join(WEB, "og-image.png"), {
  url: pathToFileURL(join(ROOT, "tools", "og-card.html")).href,
  width: 1200,
  height: 630,
});

// iOS shows touch icons on an opaque square and rounds the corners itself, so
// the favicon's navy tile fills the whole canvas edge to edge.
const favicon = (await readFile(join(WEB, "favicon.svg"), "utf8"))
  .replace('<rect width="64" height="64" rx="12" fill="#1e3a8a"/>', '<rect width="64" height="64" fill="#1e3a8a"/>');
await render(join(WEB, "apple-touch-icon.png"), {
  html: `<!doctype html><style>html,body{margin:0;width:180px;height:180px;background:#1e3a8a}
    svg{display:block;width:180px;height:180px}</style>${favicon}`,
  width: 180,
  height: 180,
});

await browser.close();
