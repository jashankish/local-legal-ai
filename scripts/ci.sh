#!/usr/bin/env bash
# =============================================================================
# ci.sh — the project's CI, run on your own machine. There is no hosted CI:
# this script is the only pipeline, so run it before pushing (the pre-push
# hook in .githooks/ does that for you) and before deploying the web demo.
#
#   bash scripts/ci.sh            full run: everything below
#   bash scripts/ci.sh --quick    python tests + demo data + web demo in Chromium
#                                 (what the pre-push hook runs, ~1–2 min)
#   bash scripts/ci.sh --web      web demo only, Chromium (the YapperTech deploy gate)
#
#   --require-ocr      fail, rather than skip, when Tesseract is not installed
#   --require-docker   fail, rather than skip, when no Docker daemon is running
#   --keep-going       run every stage even after one fails (default: stop)
#   CI_PYTHON=path     python to use instead of .venv/bin/python (e.g. in a worktree)
#
# Stages
#   python     pytest; web/demo data regenerated with the real chunker matches git
#   demo-env   scripts/demo.py up → status → verify → down, fresh, on shifted ports
#              in a throwaway directory, so it never touches your own testing
#              environment or its .demo/ data
#   web        JS syntax, engine self-test, site build, browser end-to-end in
#              Chromium (+ Firefox and WebKit on a full run)
#   docker     the Compose stack built and exercised end to end, in a temporary
#              git worktree so your .env and inbox are never touched (needs a
#              running Docker daemon, e.g. OrbStack or Docker Desktop)
#
# Logs for every stage land in .ci/logs/ (git-ignored).
# =============================================================================
set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO"

MODE=full; REQUIRE_OCR=false; REQUIRE_DOCKER=false; KEEP_GOING=false
for arg in "$@"; do
  case "$arg" in
    --quick) MODE=quick ;;
    --web) MODE=web ;;
    --require-ocr) REQUIRE_OCR=true ;;
    --require-docker) REQUIRE_DOCKER=true ;;
    --keep-going) KEEP_GOING=true ;;
    -h|--help) sed -n '2,30p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "unknown option: $arg (see --help)" >&2; exit 2 ;;
  esac
done

PLAYWRIGHT_VERSION=1.55.0   # the version tools/e2e.mjs documents
# CI_PYTHON points a worktree without its own .venv at another checkout's.
PY="${CI_PYTHON:-$REPO/.venv/bin/python}"
LOGS="$REPO/.ci/logs"
mkdir -p "$LOGS"

BOLD=$'\033[1m'; DIM=$'\033[2m'; NC=$'\033[0m'
GREEN=$'\033[32m'; RED=$'\033[31m'; YELLOW=$'\033[33m'
[ -t 1 ] || { BOLD=; DIM=; NC=; GREEN=; RED=; YELLOW=; }

FAILED=0
START=$(date +%s)

record() {  # record <pass|skip|fail> <name> <detail>
  case "$1" in
    pass) printf "  ${GREEN}✓${NC} %-48s ${DIM}%s${NC}\n" "$2" "$3" ;;
    skip) printf "  ${YELLOW}–${NC} %-48s ${YELLOW}%s${NC}\n" "$2" "$3" ;;
    fail) printf "  ${RED}✗${NC} %-48s ${RED}%s${NC}\n" "$2" "$3"; FAILED=$((FAILED + 1)) ;;
  esac
}

finish() {
  local took=$(( $(date +%s) - START ))
  echo
  if [ "$FAILED" -eq 0 ]; then
    printf "${GREEN}${BOLD}CI passed${NC} ${DIM}(%s mode, %dm %ds)${NC}\n" "$MODE" $((took / 60)) $((took % 60))
  else
    printf "${RED}${BOLD}CI failed: %d step(s)${NC} ${DIM}(%s mode, %dm %ds) — logs in .ci/logs/${NC}\n" \
      "$FAILED" "$MODE" $((took / 60)) $((took % 60))
  fi
  exit $(( FAILED > 0 ? 1 : 0 ))
}

stop_unless_keep_going() { $KEEP_GOING || finish; }

# step <name> <log-file> <command...>: run quietly, show the log tail on failure.
step() {
  local name="$1" log="$LOGS/$2"; shift 2
  local t0; t0=$(date +%s)
  if "$@" >"$log" 2>&1; then
    record pass "$name" "$(( $(date +%s) - t0 ))s"
    return 0
  fi
  record fail "$name" "see .ci/logs/$(basename "$log")"
  tail -n 25 "$log" | sed 's/^/      /'
  stop_unless_keep_going
  return 1
}

section() { printf "\n${BOLD}%s${NC}\n" "$1"; }

port_free() { ! (exec 3<>"/dev/tcp/127.0.0.1/$1") 2>/dev/null; }

# ── python ───────────────────────────────────────────────────────────────────
stage_python() {
  section "Python"
  if [ ! -x "$PY" ]; then
    record fail "Python environment" "no .venv: python3.12 -m venv .venv && .venv/bin/pip install -r requirements.txt"
    stop_unless_keep_going
    return
  fi

  step "pytest" pytest.log "$PY" -m pytest -rs -q

  local skipped
  skipped=$(grep -cE "^SKIPPED .*Tesseract" "$LOGS/pytest.log" 2>/dev/null || true)
  if [ "${skipped:-0}" -gt 0 ]; then
    if $REQUIRE_OCR; then
      record fail "OCR tests" "Tesseract not installed (--require-ocr): brew install tesseract"
      stop_unless_keep_going
    else
      record skip "OCR tests" "$skipped skipped: Tesseract not installed (brew install tesseract)"
    fi
  else
    record pass "OCR tests" "ran"
  fi

  step "Web demo data matches samples + real chunker" demo-data.log \
    "$PY" tools/make_demo_data.py --check
}

# ── testing environment ──────────────────────────────────────────────────────
stage_demo_env() {
  section "Testing environment (fresh, isolated)"
  if [ ! -x "$PY" ]; then
    record fail "Testing environment" "no .venv"
    stop_unless_keep_going
    return
  fi

  # A port block clear of a testing environment you may already have running.
  local offset="" candidate
  for candidate in 100 200 300 400; do
    if port_free $((8010 + candidate)) && port_free $((8511 + candidate)) \
       && port_free $((8011 + candidate)) && port_free $((8012 + candidate)); then
      offset=$candidate
      break
    fi
  done
  if [ -z "$offset" ]; then
    record fail "Testing environment" "no free port block between 8110 and 8911"
    stop_unless_keep_going
    return
  fi

  local dir; dir="$(mktemp -d "${TMPDIR:-/tmp}/legal-ai-ci-demo.XXXXXX")"
  export DEMO_PORT_OFFSET="$offset"
  local demo=("$PY" scripts/demo.py --dir "$dir")
  local ok=true
  step "demo.py up (fresh install, ports +$offset)" demo-up.log "${demo[@]}" up || ok=false
  if $ok; then
    step "demo.py status" demo-status.log "${demo[@]}" status || ok=false
  fi
  if $ok; then
    step "demo.py verify (health, 9 pages, an answer)" demo-verify.log "${demo[@]}" verify || ok=false
  fi
  $ok || cp "$dir"/logs/*.log "$LOGS/" 2>/dev/null || true
  "${demo[@]}" down >"$LOGS/demo-down.log" 2>&1 || true
  unset DEMO_PORT_OFFSET
  rm -rf "$dir"
}

# ── web demo ─────────────────────────────────────────────────────────────────
ensure_playwright() {
  if ! grep -qs "\"version\": \"$PLAYWRIGHT_VERSION\"" node_modules/playwright/package.json; then
    npm i --no-save --silent "playwright@$PLAYWRIGHT_VERSION"
  fi
  npx --no-install playwright install "$@"
}

js_syntax() {
  local f
  for f in web/js/*.js web/js/engine/*.js tools/*.mjs; do
    node --input-type=module --check < "$f" || { echo "syntax error in $f"; return 1; }
  done
}

stage_web() {
  section "Web demo (yappertech.com/legal-ai-demo)"
  if ! command -v node >/dev/null; then
    record fail "Web demo" "node is not installed"
    stop_unless_keep_going
    return
  fi
  step "JavaScript parses" web-syntax.log js_syntax
  step "Engine self-test (15 questions, key-term parity)" web-selftest.log node tools/selftest.mjs
  step "Site build → dist/legal-ai-demo" web-build.log bash tools/build-site.sh

  local browsers=(chromium)
  [ "$MODE" = full ] && browsers=(chromium firefox webkit)
  step "Playwright $PLAYWRIGHT_VERSION + ${browsers[*]}" web-playwright.log \
    ensure_playwright "${browsers[@]}" || return
  local browser
  for browser in "${browsers[@]}"; do
    step "End-to-end in $browser" "web-e2e-$browser.log" node tools/e2e.mjs --browser "$browser"
  done
}

# ── docker ───────────────────────────────────────────────────────────────────
docker_stack() (  # a subshell: its set -e and cd must not leak into this script
  set -e
  cd "$1"
  cp .env.example .env
  local secret; secret="$("$PY" -c 'import secrets; print(secrets.token_urlsafe(48))')"
  sed -i.bak "s|^SECRET_KEY=.*|SECRET_KEY=$secret|" .env && rm -f .env.bak
  mkdir -p inbox && chmod 777 inbox
  docker compose --profile llm --profile automation config --quiet
  docker compose build
  docker compose up -d --wait --wait-timeout 300
  curl -fsS http://127.0.0.1:8000/health | grep -q '"chromadb":"healthy"'
  curl -fsS http://127.0.0.1:8501/_stcore/health
  "$PY" scripts/seed_demo.py --backend http://127.0.0.1:8000
  "$PY" scripts/ci_check_answer.py --backend http://127.0.0.1:8000 --expect-mode extractive
  mkdir -p inbox/contracts
  cp samples/inbox/software_license_agreement.txt inbox/contracts/
  "$PY" scripts/ci_check_answer.py --backend http://127.0.0.1:8000 \
    --expect-document software_license_agreement.txt --wait 90
  mkdir -p inbox/real_estate
  cp samples/inbox/scanned_lease_amendment.pdf inbox/real_estate/
  "$PY" scripts/ci_check_answer.py --backend http://127.0.0.1:8000 \
    --expect-document scanned_lease_amendment.pdf --wait 120
  docker compose --profile llm up -d llm
  "$PY" scripts/ci_check_answer.py --backend http://127.0.0.1:8000 --expect-mode generative --wait 900
)

stage_docker() {
  section "Docker Compose stack"
  if ! docker info >/dev/null 2>&1; then
    if $REQUIRE_DOCKER; then
      record fail "Docker stack" "no Docker daemon running (start OrbStack or Docker Desktop)"
      stop_unless_keep_going
    else
      record skip "Docker stack" "no Docker daemon running: start OrbStack/Docker Desktop to include it"
    fi
    return
  fi
  if ! port_free 8000 || ! port_free 8501; then
    record fail "Docker stack" "ports 8000/8501 are in use (stop ./start_system.sh first)"
    stop_unless_keep_going
    return
  fi

  # A clean checkout of HEAD, so the stack never sees your .env, data/ or inbox/.
  local tree; tree="$(mktemp -d "${TMPDIR:-/tmp}/legal-ai-ci-docker.XXXXXX")"
  rmdir "$tree"
  git worktree add --detach --quiet "$tree" HEAD
  step "Compose: build, seed, inbox, OCR, local model" docker.log docker_stack "$tree"
  (cd "$tree" && docker compose --profile llm logs --tail 200 >"$LOGS/docker-compose.log" 2>&1
                 docker compose --profile llm down -v >/dev/null 2>&1) || true
  git worktree remove --force "$tree" >/dev/null 2>&1 || rm -rf "$tree"
}

# ── run ──────────────────────────────────────────────────────────────────────
printf "${BOLD}Local Legal AI CI${NC} ${DIM}(%s mode, %s)${NC}\n" "$MODE" "$(git rev-parse --short HEAD)"

case "$MODE" in
  web)   stage_web ;;
  quick) stage_python; stage_web ;;
  full)  stage_python; stage_demo_env; stage_web; stage_docker ;;
esac

finish
