# Web demo — yappertech.com/legal-ai-demo

A browser-only build of Local Legal AI, published at
**https://www.yappertech.com/legal-ai-demo/**. Visitors get the real screens —
sign-in, dashboard, upload, Ask Documents, library, analytics, audit log, users,
integrations, account — searching a library of fictional sample agreements that is
indexed and queried entirely in their browser. Nothing is uploaded anywhere.

## Why a separate build

The product is Streamlit + FastAPI + ChromaDB + a local model. yappertech.com is a
static S3 bucket behind CloudFront: it can serve files but run nothing. So `web/`
is a dependency-free HTML/JS version of the UI with two interchangeable clients
(`web/js/api.js`):

| Mode | When | What answers questions |
|---|---|---|
| **demo** (default) | `API_BASE_URL` empty in `web/js/config.js` | The library in `web/demo/`, searched in the browser |
| **live** | build run with `--api-base-url URL` | A deployed Local Legal AI backend — same endpoints the Streamlit UI calls |

Demo mode behaves like the product does with **no local model connected**:
answers are extractive — the most relevant sentences of the top clauses, each
carrying its citation — with key terms, follow-up suggestions and sources, exactly
as on the Ask Documents page. A visitor can also upload a `.txt` file, which is
genuinely split clause by clause and indexed, and then ask about it. PDF, DOCX and
scans need the server's parsers and OCR, and the demo says so.

## Where the demo's data comes from

`web/demo/*.json` is **generated**, not hand-written:

```bash
.venv/bin/python tools/make_demo_data.py          # regenerate
.venv/bin/python tools/make_demo_data.py --check  # verify (scripts/ci.sh runs this)
```

It chunks the agreements in `samples/` with the product's own clause-aware chunker
(`rag.embedder.LegalDocumentEmbedder`) and extracts key terms with the product's own
extractor (`rag.legal_insights`), so the passages a visitor sees are the passages a
real install would index and cite. Analytics, audit trail (hash-chained), users and
integration status are derived from the same library and the questions
`scripts/seed_demo.py` asks.

If you change the samples, the chunker or the extractor, regenerate and commit.
Local CI (`scripts/ci.sh`, and so the pre-push hook) fails until you do, so the
demo cannot quietly drift from the product.

## Layout

```
web/
  index.html            shell; boots js/app.js
  css/styles.css        mirrors the Streamlit app's look
  js/app.js             hash router + every page
  js/api.js             demo client (in-browser) and live client (FastAPI)
  js/charts.js          inline-SVG charts with tooltips and data tables
  js/config.js          build-time API URL (empty = demo mode)
  js/engine/retrieval.js  TF-IDF index, ranking, extractive answers
  js/engine/insights.js   port of rag/legal_insights.py
  demo/*.json           generated library, analytics, audit, users, integrations
  og-image.png          1200×630 link-preview card (generated)
  apple-touch-icon.png  180×180 icon (generated)
  serve.py              local dev server (not shipped)
tools/
  make_demo_data.py     generates web/demo/ from samples/ with the real pipeline
  og-card.html          source of the link-preview card
  make_og_image.mjs     renders og-card.html and the favicon to the two PNGs
  build-site.sh         packages web/ into dist/legal-ai-demo/
  selftest.mjs          engine checks: 15 questions → right clause, JS key terms == Python
  e2e.mjs               Playwright walkthrough of every page, incl. phone width
```

## Link previews

Sharing the page in iMessage, Slack, LinkedIn or X shows `web/og-image.png`: the
headline and a real cited answer from the demo. To change it, edit
`tools/og-card.html` and run `node tools/make_og_image.mjs` (needs Playwright),
then commit the regenerated PNGs. The page source uses relative URLs; the build
makes the `og:` / `twitter:` URLs absolute against `--site-url` (default
`https://www.yappertech.com/legal-ai-demo/`), because preview scrapers ignore
relative ones. The e2e test fails if the image URL isn't absolute or the PNG isn't
1200×630.

iMessage caches a preview per link on each device, so a link that was already
shared before the image existed may keep its old, image-less preview there. New
shares, and other devices, fetch the current one.

## Working on it

```bash
python3 web/serve.py                 # http://127.0.0.1:8777/
node tools/selftest.mjs              # engine checks, no browser
bash tools/build-site.sh             # → dist/legal-ai-demo/
npm i --no-save playwright@1.55.0 && npx playwright install chromium
node tools/e2e.mjs --browser chromium
```

`tools/build-site.sh` options: `--head FILE` (insert an analytics tag into every
page; `LEGAL_AI_DEMO_HEAD` does the same), `--api-base-url URL` (live mode;
`LEGAL_AI_API_BASE_URL`), `--site-url URL` (where the build is served, for the
absolute link-preview URLs; `LEGAL_AI_SITE_URL`), `--zip`.

Routing is hash-based (`#/ask`, `#/analytics`, …) so every deep link is a request
for `index.html` and no server rewrite rule is needed. Every path is relative, so
the build works at any sub-path. The only browser storage used is a
`legal-ai-demo:session` sessionStorage key, prefixed because the origin is shared
with every other YapperTech product.

## How it reaches yappertech.com

The YapperTech monorepo (`yappertech-draft`) does not vendor this code. Its
`build.js` runs `bash tools/build-site.sh` in this repo (a sibling checkout at
`../local-legal-ai`, or wherever `LEGAL_AI_REPO` points), injects the site's Google
Analytics tag from `scripts/legal-ai-demo-head.html`, and copies
`dist/legal-ai-demo/` into its own `dist/`. `scripts/deploy.sh` /
`scripts/release.sh` then sync it to S3 and invalidate CloudFront. Because the
file names are not content-hashed, both scripts serve `legal-ai-demo/*` with
`Cache-Control: no-cache` rather than the site's default one-year immutable cache.

So publishing a change is:

1. Commit to `main` here and push. The pre-push hook runs `scripts/ci.sh --quick`
   (enable it once with `git config core.hooksPath .githooks`).
2. In the monorepo checkout, make sure the sibling `../local-legal-ai` is on `main`
   and up to date (or set `LEGAL_AI_REPO`), then run `bash scripts/deploy.sh`.
   Its test phase runs `scripts/ci.sh --web` in this repo first, so a broken demo
   stops the deploy before anything is uploaded.

There is no hosted CI anywhere in this pipeline: every check runs on the machine
doing the push or the deploy.

To point the public demo at a real backend, deploy the API with CORS allowing
`https://www.yappertech.com` and `https://yappertech.com`, then build with
`LEGAL_AI_API_URL=https://… node build.js`.
