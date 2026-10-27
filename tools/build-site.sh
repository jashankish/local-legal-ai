#!/usr/bin/env bash
# Package the web demo for hosting: copies web/ to dist/legal-ai-demo/ without
# the local-only bits (serve.py). Upload dist/legal-ai-demo/ to any static host,
# at the root or in a sub-folder — every path in the app is relative.
#
#   bash tools/build-site.sh                      → dist/legal-ai-demo/
#   bash tools/build-site.sh --zip                → also dist/legal-ai-demo.zip
#   bash tools/build-site.sh --head FILE          → insert FILE's HTML before </head>
#                                                   on every page (e.g. an analytics tag);
#                                                   LEGAL_AI_DEMO_HEAD=FILE does the same
#   bash tools/build-site.sh --api-base-url URL   → point the build at a real backend
#                                                   instead of the in-browser demo;
#                                                   LEGAL_AI_API_BASE_URL=URL does the same
#   bash tools/build-site.sh --site-url URL       → where the build will be served, for the
#                                                   absolute link-preview URLs (og:image…);
#                                                   LEGAL_AI_SITE_URL=URL does the same.
#                                                   Default: https://www.yappertech.com/legal-ai-demo/
set -euo pipefail

HEAD_FILE="${LEGAL_AI_DEMO_HEAD:-}"
API_BASE_URL="${LEGAL_AI_API_BASE_URL:-}"
SITE_URL="${LEGAL_AI_SITE_URL:-https://www.yappertech.com/legal-ai-demo/}"
ZIP=false

while [ $# -gt 0 ]; do
  case "$1" in
    --zip) ZIP=true ;;
    --head) HEAD_FILE="$2"; shift ;;
    --api-base-url) API_BASE_URL="$2"; shift ;;
    --site-url) SITE_URL="$2"; shift ;;
    *) echo "unknown option: $1" >&2; exit 2 ;;
  esac
  shift
done

[ -z "$HEAD_FILE" ] || HEAD_FILE="$(cd "$(dirname "$HEAD_FILE")" && pwd)/$(basename "$HEAD_FILE")"
[ -z "$HEAD_FILE" ] || [ -f "$HEAD_FILE" ] || { echo "--head: no such file $HEAD_FILE" >&2; exit 2; }

cd "$(dirname "$0")/.."
OUT=dist/legal-ai-demo
rm -rf "$OUT"
mkdir -p "$OUT"

# Copy everything except the dev-only server.
tar -C web --exclude='./serve.py' --exclude='.DS_Store' --exclude='__pycache__' -cf - . \
  | tar -C "$OUT" -xf -

# The demo cannot work without these, and a silent half-build would deploy green.
for f in index.html css/styles.css js/app.js js/api.js js/config.js js/charts.js \
         js/engine/retrieval.js js/engine/insights.js \
         demo/library.json demo/analytics.json demo/audit.json demo/users.json \
         demo/integrations.json demo/questions.json favicon.svg \
         og-image.png apple-touch-icon.png; do
  [ -f "$OUT/$f" ] || { echo "missing $f in the build" >&2; exit 1; }
done

# Link previews: iMessage, Slack and friends ignore relative og:/twitter: URLs,
# so resolve them against where this build will be served.
python3 - "$OUT/index.html" "$SITE_URL" <<'PY'
import re, sys
from urllib.parse import urljoin
path, site = sys.argv[1], sys.argv[2]
if not re.match(r"^https?://", site):
    sys.exit(f"--site-url must be an absolute http(s) URL, got {site!r}")
site = site if site.endswith("/") else site + "/"
html = open(path).read()
absolute = lambda m: f'{m.group(1)}"{urljoin(site, m.group(2))}"'
html, count = re.subn(
    r'(<meta (?:property|name)="(?:og:url|og:image|og:image:secure_url|twitter:image)" content=)"([^"]*)"',
    absolute, html)
html, canonical = re.subn(r'(<link rel="canonical" href=)"([^"]*)"', absolute, html)
assert count == 4 and canonical == 1, f"expected 4 preview URLs and a canonical link, found {count} and {canonical}"
open(path, "w").write(html)
PY
echo "Link previews point at ${SITE_URL%/}/og-image.png"

# A build with no documents would render an empty product. Catch that here.
python3 - "$OUT/demo/library.json" <<'PY'
import json, sys
library = json.load(open(sys.argv[1]))
assert len(library["documents"]) >= 4, "demo library has too few documents"
assert len(library["passages"]) >= 30, "demo library has too few passages"
PY

if [ -n "$API_BASE_URL" ]; then
  python3 - "$OUT/js/config.js" "$API_BASE_URL" <<'PY'
import re, sys
path, url = sys.argv[1], sys.argv[2]
source = open(path).read()
patched, count = re.subn(r'^const API_BASE_URL = "";$',
                         'const API_BASE_URL = "%s";' % url.replace('"', '\\"'),
                         source, count=1, flags=re.M)
assert count == 1, "could not find the API_BASE_URL line in config.js"
open(path, "w").write(patched)
PY
  echo "Pointed the build at $API_BASE_URL (live backend, not demo mode)"
fi

if [ -n "$HEAD_FILE" ]; then
  for page in "$OUT"/*.html; do
    python3 - "$page" "$HEAD_FILE" <<'PY'
import sys
page, snippet = sys.argv[1], open(sys.argv[2]).read().rstrip("\n") + "\n"
html = open(page).read()
assert "</head>" in html, page
open(page, "w").write(html.replace("</head>", snippet + "</head>", 1))
PY
  done
  echo "Added $(basename "$HEAD_FILE") to the <head> of every page"
fi

echo "Built $OUT ($(du -sh "$OUT" | cut -f1), $(find "$OUT" -type f | wc -l | tr -d ' ') files)"

if $ZIP; then
  (cd dist && rm -f legal-ai-demo.zip && zip -qr legal-ai-demo.zip legal-ai-demo)
  echo "Zipped dist/legal-ai-demo.zip ($(du -sh dist/legal-ai-demo.zip | cut -f1))"
fi
