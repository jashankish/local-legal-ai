// End-to-end walkthrough of the built demo in a real browser.
//
// Serves dist/legal-ai-demo/ and drives it the way a visitor would: sign in,
// visit every page, ask a question and read the cited answer, upload a document
// and ask about it, verify the audit chain, create a user. Any page that throws,
// renders empty, or logs a console error fails the run.
//
//   npm i --no-save playwright@1.55.0 && npx playwright install --with-deps chromium
//   node tools/e2e.mjs [--browser chromium|firefox|webkit] [--headed]

import { createServer } from "node:http";
import { readFile } from "node:fs/promises";
import { existsSync } from "node:fs";
import { extname, join, normalize } from "node:path";
import { fileURLToPath } from "node:url";
import { dirname } from "node:path";

const ROOT = join(dirname(fileURLToPath(import.meta.url)), "..");
const SITE = join(ROOT, "dist", "legal-ai-demo");

const args = process.argv.slice(2);
const browserName = args.includes("--browser") ? args[args.indexOf("--browser") + 1] : "chromium";
const headed = args.includes("--headed");

if (!existsSync(join(SITE, "index.html"))) {
  console.error("dist/legal-ai-demo/ is missing — run: bash tools/build-site.sh");
  process.exit(1);
}

const TYPES = {
  ".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8",
  ".css": "text/css; charset=utf-8", ".json": "application/json; charset=utf-8",
  ".svg": "image/svg+xml",
};

const server = createServer(async (request, response) => {
  const path = decodeURIComponent(new URL(request.url, "http://x").pathname);
  const file = join(SITE, normalize(path).replace(/^(\.\.[/\\])+/, ""));
  const target = path.endsWith("/") ? join(file, "index.html") : file;
  try {
    const body = await readFile(target);
    response.writeHead(200, {
      "Content-Type": TYPES[extname(target)] || "application/octet-stream",
      "Cache-Control": "no-store",
    });
    response.end(body);
  } catch {
    response.writeHead(404).end("not found");
  }
});

await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
const base = `http://127.0.0.1:${server.address().port}/`;

const { chromium, firefox, webkit } = await import("playwright");
const engine = { chromium, firefox, webkit }[browserName];
if (!engine) {
  console.error(`unknown browser: ${browserName}`);
  process.exit(2);
}

const browser = await engine.launch({ headless: !headed });
const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });

const consoleErrors = [];
page.on("console", (message) => {
  if (message.type() === "error") consoleErrors.push(message.text());
});
page.on("pageerror", (error) => consoleErrors.push(`uncaught: ${error.message}`));

let failures = 0;
async function check(name, run) {
  try {
    const problem = await run();
    if (problem) {
      failures += 1;
      console.log(`  FAIL  ${name}\n          ${problem}`);
    } else {
      console.log(`  ok    ${name}`);
    }
  } catch (error) {
    failures += 1;
    console.log(`  FAIL  ${name}\n          ${error.message.split("\n")[0]}`);
  }
}

const text = (selector) => page.locator(selector).first().innerText();

console.log(`\nEnd-to-end in ${browserName}\n`);

await page.goto(base, { waitUntil: "load" });

await check("the sign-in page renders", async () => {
  await page.waitForSelector("#login-form", { timeout: 15000 });
  const heading = await text(".main-header h1");
  return heading.includes("Local Legal AI") ? null : `header reads "${heading}"`;
});

await check("no login is pre-filled or printed on the sign-in page", async () => {
  const username = await page.locator('input[name="username"]').inputValue();
  const password = await page.locator('input[name="password"]').inputValue();
  if (username || password) return `fields load with "${username}" / "${password ? "•••" : ""}"`;
  const card = await text(".login-card");
  return /admin\s*\/\s*admin|\btran\b/.test(card) ? "credentials are printed on the page" : null;
});

await check("wrong credentials are rejected", async () => {
  await page.fill('input[name="username"]', "admin");
  await page.fill('input[name="password"]', "nope");
  await page.click('button[type="submit"]');
  await page.waitForSelector("#login-error .note-err", { timeout: 10000 });
  return null;
});

await check("admin can sign in", async () => {
  await page.fill('input[name="username"]', "admin");
  await page.fill('input[name="password"]', "admin");
  await page.click('button[type="submit"]');
  await page.waitForSelector(".sidebar", { timeout: 15000 });
  return (await text("h1")).includes("Dashboard") ? null : "no dashboard after sign-in";
});

await check("the dashboard shows the indexed library", async () => {
  const values = await page.locator(".metric-value").allInnerTexts();
  const documents = Number(values[0]);
  const passages = Number(values[1]);
  if (!(documents >= 4)) return `only ${documents} documents`;
  if (!(passages >= 30)) return `only ${passages} passages`;
  const rows = await page.locator("tbody tr").count();
  return rows >= 4 ? null : `only ${rows} rows in "Recently added"`;
});

const PAGES = [
  ["upload", "Document Upload"],
  ["ask", "Ask Your Documents"],
  ["library", "Document Library"],
  ["analytics", "Analytics Dashboard"],
  ["audit", "Audit Log"],
  ["users", "Users"],
  ["integrations", "Integrations"],
  ["account", "My Account"],
];

for (const [route, heading] of PAGES) {
  await check(`the ${route} page renders`, async () => {
    await page.click(`button[data-nav="${route}"]`);
    await page.waitForFunction(
      (expected) => document.querySelector("h1")?.textContent?.includes(expected),
      heading, { timeout: 15000 });
    const body = await text("#main");
    if (body.includes("Could not load this page")) return "page threw while rendering";
    return body.length > 200 ? null : `page rendered only ${body.length} characters`;
  });
}

await check("every analytics tab renders with its charts", async () => {
  await page.click('button[data-nav="analytics"]');
  await page.waitForSelector('[data-tab="usage"]', { timeout: 15000 });
  for (const tab of ["usage", "performance", "similarity", "activity", "reports"]) {
    await page.click(`[data-tab="${tab}"]`);
    await page.waitForFunction(
      (name) => document.querySelector(`[data-tab="${name}"]`)?.getAttribute("aria-selected") === "true",
      tab, { timeout: 15000 });
    const body = await text("#analytics-body");
    if (body.includes("Could not load")) return `${tab} tab threw`;
    if (tab !== "reports") {
      const charts = await page.locator("#analytics-body .chart svg").count();
      if (!charts) return `${tab} tab drew no charts`;
    }
  }
  return null;
});

await check("a report can be generated", async () => {
  await page.click('[data-tab="reports"]');
  await page.click('[data-action="generate-report"]');
  await page.waitForSelector("#report-output .note-ok", { timeout: 15000 });
  return null;
});

await check("asking a question returns a cited answer", async () => {
  await page.click('button[data-nav="ask"]');
  await page.waitForSelector("#ask-input", { timeout: 15000 });
  await page.fill("#ask-input", "Can the tenant terminate the lease early, and what does it cost?");
  await page.click('[data-action="ask"]');
  await page.waitForSelector("#ask-history .acc-body .source", { timeout: 20000 });

  const answer = await text("#ask-history .answer");
  if (!answer.includes("four (4) months")) return `answer was: ${answer.slice(0, 160)}`;
  if (!(await page.locator("#ask-history .cite").count())) return "answer carries no citation marker";
  const cited = await page.locator("#ask-history .tag-cited").count();
  if (!cited) return "no source is marked as cited";
  const source = await text("#ask-history .source-head");
  return source.includes("Commercial Lease") ? null : `top source was: ${source}`;
});

await check("a follow-up suggestion fills the question box", async () => {
  const suggestion = page.locator("#ask-history [data-suggest]").first();
  const expected = await suggestion.getAttribute("data-suggest");
  await suggestion.click();
  const value = await page.locator("#ask-input").inputValue();
  return value === expected ? null : `box reads "${value}"`;
});

await check("an uploaded document is indexed and becomes answerable", async () => {
  await page.click('button[data-nav="upload"]');
  await page.waitForSelector("#upload-file", { timeout: 15000 });
  await page.setInputFiles("#upload-file", {
    name: "side_letter.txt",
    mimeType: "text/plain",
    buffer: Buffer.from(
      "SIDE LETTER\n\n" +
      "This Side Letter is made on 1 March 2026 between Pinewood Holdings LLC and Vance Partners LLP.\n\n" +
      "Section 1. Fees. The quarterly advisory fee is $27,500, payable within fifteen (15) days of invoice.\n\n" +
      "Section 2. Termination. Either party may terminate this Side Letter on forty-five (45) days notice.\n"),
  });
  await page.waitForSelector('[data-action="do-upload"]', { timeout: 10000 });
  await page.click('[data-action="do-upload"]');
  await page.waitForSelector("#upload-result .note-ok", { timeout: 20000 });

  await page.click('button[data-nav="ask"]');
  await page.waitForSelector("#ask-input", { timeout: 15000 });
  const question = "What is the quarterly advisory fee in the side letter?";
  await page.fill("#ask-input", question);
  await page.click('[data-action="ask"]');
  // The history already holds the earlier question, so wait for THIS answer.
  await page.waitForFunction(
    (asked) => document.querySelector("#ask-history summary")?.textContent?.includes(asked),
    question, { timeout: 20000 });
  await page.waitForSelector("#ask-history .acc-body .source", { timeout: 20000 });
  const answer = await text("#ask-history .answer");
  return answer.includes("$27,500") ? null : `answer was: ${answer.slice(0, 160)}`;
});

await check("the library search filters documents", async () => {
  await page.click('button[data-nav="library"]');
  await page.waitForSelector("#library-search", { timeout: 15000 });
  const before = await page.locator(".file-card").count();
  await page.fill("#library-search", "lease");
  await page.waitForFunction(
    (count) => document.querySelectorAll(".file-card").length < count,
    before, { timeout: 10000 });
  const after = await page.locator(".file-card").count();
  return after > 0 && after < before ? null : `${before} cards before, ${after} after`;
});

await check("the audit chain verifies", async () => {
  await page.click('button[data-nav="audit"]');
  await page.waitForSelector('[data-action="verify-chain"]', { timeout: 15000 });
  await page.click('[data-action="verify-chain"]');
  await page.waitForSelector("#verify-result .note-ok", { timeout: 15000 });
  const rows = await page.locator("tbody tr").count();
  return rows > 5 ? null : `only ${rows} audit rows`;
});

await check("an admin can create a user", async () => {
  await page.click('button[data-nav="users"]');
  await page.waitForSelector("#create-user-form", { timeout: 15000 });
  const before = await page.locator("tbody tr").count();
  await page.fill('#create-user-form input[name="username"]', "a.newjoiner");
  await page.fill('#create-user-form input[name="password"]', "temporary-pass-1");
  await page.click('#create-user-form button[type="submit"]');
  await page.waitForFunction(
    (count) => document.querySelectorAll("tbody tr").length > count, before, { timeout: 15000 });
  return null;
});

await check("a deep link opens its page directly", async () => {
  await page.goto(`${base}#/integrations`, { waitUntil: "load" });
  await page.waitForSelector(".sidebar", { timeout: 15000 });
  const heading = await text("h1");
  return heading.includes("Integrations") ? null : `landed on "${heading}"`;
});

await check("the layout works at phone width", async () => {
  const phone = await browser.newPage({ viewport: { width: 390, height: 844 } });
  const overflowing = [];
  try {
    await phone.goto(base, { waitUntil: "load" });
    await phone.waitForSelector("#login-form", { timeout: 15000 });
    await phone.fill('input[name="username"]', "admin");
    await phone.fill('input[name="password"]', "admin");
    await phone.click('button[type="submit"]');
    await phone.waitForSelector(".sidebar", { timeout: 15000 });

    for (const [route] of PAGES) {
      await phone.goto(`${base}#/${route}`, { waitUntil: "load" });
      await phone.waitForSelector("#main h1", { timeout: 15000 });
      // A page wider than the screen means something is not wrapping.
      const overflows = await phone.evaluate(() =>
        document.documentElement.scrollWidth > window.innerWidth + 1);
      if (overflows) overflowing.push(route);
    }
  } finally {
    await phone.close();
  }
  return overflowing.length ? `pages scroll sideways: ${overflowing.join(", ")}` : null;
});

await check("signing out returns to the sign-in page", async () => {
  await page.click('[data-action="logout"]');
  await page.waitForSelector("#login-form", { timeout: 15000 });
  return null;
});

await check("liz / tran signs in as an administrator", async () => {
  await page.fill('input[name="username"]', "liz");
  await page.fill('input[name="password"]', "tran");
  await page.click('button[type="submit"]');
  await page.waitForSelector(".sidebar", { timeout: 15000 });
  const user = await text(".sidebar");
  if (!user.includes("liz")) return "sidebar does not show liz";
  // Admin-only pages must be in the navigation.
  const admin = await page.locator('button[data-nav="users"]').count();
  return admin ? null : "no admin pages for liz";
});

await check("nothing logged a console error", () => (
  consoleErrors.length ? consoleErrors.slice(0, 3).join(" | ") : null));

await browser.close();
server.close();

console.log(failures ? `\n${failures} check(s) failed\n` : "\nAll checks passed\n");
process.exit(failures ? 1 : 0);
