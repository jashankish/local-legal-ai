#!/usr/bin/env python3
"""Local demo and testing environment — the whole product on localhost, in one command.

    python scripts/demo.py up            # start everything and load the sample firm
    python scripts/demo.py up --with-model   # ...and answer with a local language model
    python scripts/demo.py status        # what is running
    python scripts/demo.py verify        # health, every UI page, and a real answer
    python scripts/demo.py reset         # wipe the demo library and reload it
    python scripts/demo.py down          # stop everything
    python scripts/demo.py tour          # print the walkthrough again

Everything lives under `.demo/` (git-ignored) and listens on ports that do not
clash with a normal `./start_system.sh` instance, so a demo can run alongside
your own data without touching it.
"""

import argparse
import json
import os
import secrets
import shutil
import signal
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
PYTHON = sys.executable
# Deliberately simple: the demo holds only fictional sample agreements, listens on
# localhost alone and runs the API with DEMO_MODE, which allows a password this short.
ADMIN_PASSWORD = "admin"
# What earlier versions of the demo set; adopted and replaced on the next `up`.
PREVIOUS_ADMIN_PASSWORDS = ("LegalDemo-2025",)

# Deliberately not 8000/8501: a demo should never collide with a real instance.
PORTS = {"api": 8010, "ui": 8511, "model": 8011, "events": 8012}
SERVICES = ("events", "model", "api", "ui")


# --- small helpers ---------------------------------------------------------------

def say(message="", symbol=""):
    print(f"{symbol}{message}" if symbol else message, flush=True)


def paths(root):
    return {
        "root": root,
        "data": os.path.join(root, "data"),
        "inbox": os.path.join(root, "data", "inbox"),
        "logs": os.path.join(root, "logs"),
        "run": os.path.join(root, "run"),
        "env": os.path.join(root, "demo.env"),
    }


def listening(port):
    with socket.socket() as probe:
        probe.settimeout(0.3)
        return probe.connect_ex(("127.0.0.1", port)) == 0


def http_ok(url, timeout=3):
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            return 200 <= response.status < 300
    except (urllib.error.URLError, OSError, ValueError):
        return False


def wait_for(url, seconds, label):
    deadline = time.time() + seconds
    while time.time() < deadline:
        if http_ok(url):
            return True
        time.sleep(0.5)
    say(f"   {label} did not become ready within {seconds}s", "⚠️  ")
    return False


def pid_file(p, name):
    return os.path.join(p["run"], f"{name}.pid")


def running_pid(p, name):
    path = pid_file(p, name)
    if not os.path.exists(path):
        return None
    try:
        pid = int(open(path).read().strip())
        os.kill(pid, 0)
        return pid
    except (ValueError, ProcessLookupError, PermissionError, OSError):
        return None


def spawn(p, name, command, env, cwd):
    """Start a detached background service and record its pid."""
    log_path = os.path.join(p["logs"], f"{name}.log")
    with open(log_path, "ab") as log:
        log.write(f"\n=== {name} started {time.strftime('%Y-%m-%d %H:%M:%S')} ===\n".encode())
        process = subprocess.Popen(command, cwd=cwd, env=env, stdout=log, stderr=subprocess.STDOUT,
                                   start_new_session=True)
    with open(pid_file(p, name), "w") as handle:
        handle.write(str(process.pid))
    return process.pid


def terminate(p, name):
    pid = running_pid(p, name)
    if pid is None:
        if os.path.exists(pid_file(p, name)):
            os.remove(pid_file(p, name))
        return False
    try:
        os.killpg(os.getpgid(pid), signal.SIGTERM)
    except (ProcessLookupError, PermissionError, OSError):
        try:
            os.kill(pid, signal.SIGTERM)
        except OSError:
            pass
    for _ in range(40):
        if running_pid(p, name) is None:
            break
        time.sleep(0.25)
    else:
        try:
            os.killpg(os.getpgid(pid), signal.SIGKILL)
        except OSError:
            pass
    if os.path.exists(pid_file(p, name)):
        os.remove(pid_file(p, name))
    return True


def load_env(p):
    """Secrets persist across restarts so sign-in tokens stay valid."""
    if os.path.exists(p["env"]):
        values = {}
        for line in open(p["env"]):
            if "=" in line and not line.strip().startswith("#"):
                key, _, value = line.partition("=")
                values[key.strip()] = value.strip()
        if {"SECRET_KEY", "WEBHOOK_SECRET"} <= set(values):
            return values
    values = {"SECRET_KEY": secrets.token_urlsafe(48), "WEBHOOK_SECRET": secrets.token_urlsafe(24)}
    with open(p["env"], "w") as handle:
        handle.write("# Generated for the local demo environment.\n")
        for key, value in values.items():
            handle.write(f"{key}={value}\n")
    os.chmod(p["env"], 0o600)
    return values


def model_assets():
    """Where the llama.cpp launcher keeps its virtualenv and weights, honouring overrides."""
    venv = os.environ.get("LLAMA_VENV", os.path.join(REPO, "model", ".venv"))
    models = os.environ.get("MODEL_DIR", os.path.join(REPO, "model", "models"))
    ready = os.path.exists(os.path.join(venv, "bin", "python")) and os.path.isdir(models) and any(
        name.endswith(".gguf") for name in os.listdir(models)) if os.path.isdir(models) else False
    return venv, models, ready


# --- commands --------------------------------------------------------------------

def cmd_up(args):
    p = paths(args.dir)
    for key in ("data", "inbox", "logs", "run"):
        os.makedirs(p[key], exist_ok=True)

    busy = [name for name in SERVICES
            if listening(PORTS[name]) and running_pid(p, name) is None
            and (name != "model" or args.with_model)]
    if busy:
        say(f"Ports already in use by something else: "
            f"{', '.join(f'{n} ({PORTS[n]})' for n in busy)}", "❌ ")
        say("   Stop it, or pass --api-port/--ui-port to move the demo.")
        return 1

    env_values = load_env(p)
    base_env = {**os.environ, **env_values}
    events_url = f"http://127.0.0.1:{PORTS['events']}"

    say("Starting the local demo environment", "🚀 ")

    # 1. Event sink — gives the Integrations page somewhere real to deliver to.
    if running_pid(p, "events") is None:
        spawn(p, "events", [PYTHON, os.path.join(REPO, "scripts", "demo_event_sink.py"),
                            "--dir", os.path.abspath(p["root"]), "--port", str(PORTS["events"]),
                            "--secret", env_values["WEBHOOK_SECRET"]],
              base_env, REPO)
        wait_for(events_url, 15, "Event sink")
    say(f"   Event sink   {events_url}", "✓ ")

    # 2. Optional local model. An already-running one is adopted, so `reset`
    #    and a plain `up` keep generated answers rather than silently losing them.
    model_endpoint = ""
    model_url = f"http://127.0.0.1:{PORTS['model']}"
    if http_ok(f"{model_url}/v1/models"):
        model_endpoint = model_url
        say(f"   Model        {model_endpoint} (already running)", "✓ ")
    elif args.with_model:
        venv, models, ready = model_assets()
        if running_pid(p, "model") is None:
            if not ready:
                say("   First run downloads a ~1 GB model and builds llama.cpp; this takes a few minutes.",
                    "⏳ ")
            spawn(p, "model", ["bash", os.path.join(REPO, "model", "llamacpp_launcher.sh")],
                  {**base_env, "LLM_PORT": str(PORTS["model"]), "LLAMA_VENV": venv, "MODEL_DIR": models},
                  REPO)
        if wait_for(f"http://127.0.0.1:{PORTS['model']}/v1/models", args.model_timeout, "Model"):
            model_endpoint = f"http://127.0.0.1:{PORTS['model']}"
            say(f"   Model        {model_endpoint} (answers will be generated)", "✓ ")
        else:
            say("   Continuing without it — answers will be cited excerpts. See .demo/logs/model.log", "⚠️  ")
    else:
        say("   Model        not started (answers will be cited excerpts; add --with-model)", "· ")

    # 3. API, run from the demo directory so all its data lands under .demo/data.
    api_url = f"http://127.0.0.1:{PORTS['api']}"
    if running_pid(p, "api") is None:
        api_env = {
            **base_env,
            "PYTHONPATH": REPO,
            "HOST": "127.0.0.1",
            "PORT": str(PORTS["api"]),
            "DEMO_MODE": "true",
            "LLM_ENABLED": "true" if model_endpoint else "false",
            "MODEL_ENDPOINT": model_endpoint or "http://127.0.0.1:1",
            "INBOX_DIR": "data/inbox",
            "INBOX_POLL_SECONDS": "5",
            "N8N_WEBHOOK_URL": f"{events_url}/n8n",
            "SLACK_WEBHOOK_URL": f"{events_url}/slack",
            "CORS_ORIGINS": f"http://localhost:{PORTS['ui']},http://127.0.0.1:{PORTS['ui']}",
        }
        spawn(p, "api", [PYTHON, "-m", "uvicorn", "backend.app:app",
                         "--host", "127.0.0.1", "--port", str(PORTS["api"])],
              api_env, os.path.abspath(p["root"]))
    if not wait_for(f"{api_url}/health", 90, "API"):
        say("   See .demo/logs/api.log", "   ")
        return 1
    say(f"   API          {api_url}  (docs at {api_url}/docs)", "✓ ")

    # 4. Web UI, run from the repo so it picks up .streamlit/config.toml.
    ui_url = f"http://localhost:{PORTS['ui']}"
    if running_pid(p, "ui") is None:
        spawn(p, "ui", [PYTHON, "-m", "streamlit", "run", os.path.join(REPO, "frontend", "streamlit_app.py"),
                        "--server.port", str(PORTS["ui"]), "--server.address", "127.0.0.1",
                        "--server.headless", "true"],
              {**base_env, "BACKEND_URL": api_url}, REPO)
    wait_for(f"http://127.0.0.1:{PORTS['ui']}/_stcore/health", 90, "Web UI")
    say(f"   Web UI       {ui_url}", "✓ ")

    adopt_admin_password(api_url)

    # 5. Sample firm.
    if not args.no_seed:
        if seeded(api_url):
            say("   Sample data already loaded (use `reset` for a clean library)", "· ")
        else:
            say("   Loading the sample firm...", "📚 ")
            seed = subprocess.run(
                [PYTHON, os.path.join(REPO, "scripts", "seed_demo.py"),
                 "--backend", api_url, "--admin-password", ADMIN_PASSWORD,
                 "--inbox-dir", os.path.abspath(p["inbox"])],
                cwd=REPO, capture_output=True, text=True)
            if seed.returncode != 0:
                say("   Seeding failed:", "⚠️  ")
                say(seed.stdout[-800:] + seed.stderr[-800:])
            else:
                say("   Sample documents, team and question history loaded", "✓ ")

    if not ocr_available(api_url):
        say("   OCR is not installed, so the scanned sample stayed in data/inbox/failed/ with an", "· ")
        say("     explanation. `brew install tesseract` (or apt-get install tesseract-ocr) then")
        say("     `reset` to see scanned documents read end to end.")

    say()
    print_tour(args, model_endpoint != "")
    return 0


def ocr_available(api_url):
    try:
        with urllib.request.urlopen(f"{api_url}/health", timeout=5) as response:
            return json.load(response).get("services", {}).get("ocr") == "available"
    except Exception:
        return True  # don't nag if we can't tell


def _post_json(url, body, token=None):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(url, method="POST", data=json.dumps(body).encode(), headers=headers)
    with urllib.request.urlopen(request, timeout=10) as response:
        return json.load(response)


def adopt_admin_password(api_url):
    """Move a demo created by an earlier version onto the current admin password.

    Its library and history stay as they are; only the password changes, so a
    `.demo/` from before keeps working with admin / admin.
    """
    try:
        _post_json(f"{api_url}/auth/login", {"username": "admin", "password": ADMIN_PASSWORD})
        return  # already current (or a fresh install, which seeding handles)
    except Exception:
        pass
    for old in PREVIOUS_ADMIN_PASSWORDS:
        try:
            token = _post_json(f"{api_url}/auth/login",
                               {"username": "admin", "password": old})["access_token"]
            _post_json(f"{api_url}/auth/change-password",
                       {"current_password": old, "new_password": ADMIN_PASSWORD}, token)
            say(f"   Admin password updated to {ADMIN_PASSWORD!r}", "· ")
            return
        except Exception:
            continue


def seeded(api_url):
    """True if the sample library is already present."""
    try:
        request = urllib.request.Request(
            f"{api_url}/auth/login", method="POST",
            data=json.dumps({"username": "admin", "password": ADMIN_PASSWORD}).encode(),
            headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(request, timeout=10) as response:
            token = json.load(response)["access_token"]
        documents = urllib.request.Request(f"{api_url}/documents",
                                           headers={"Authorization": f"Bearer {token}"})
        with urllib.request.urlopen(documents, timeout=10) as response:
            return json.load(response).get("total", 0) > 0
    except Exception:
        return False


def cmd_down(args):
    p = paths(args.dir)
    stopped = [name for name in reversed(SERVICES) if terminate(p, name)]
    say(f"Stopped: {', '.join(stopped)}" if stopped else "Nothing was running", "🛑 " if stopped else "· ")
    return 0


def cmd_status(args):
    p = paths(args.dir)
    checks = {
        "events": f"http://127.0.0.1:{PORTS['events']}",
        "model": f"http://127.0.0.1:{PORTS['model']}/v1/models",
        "api": f"http://127.0.0.1:{PORTS['api']}/health",
        "ui": f"http://127.0.0.1:{PORTS['ui']}/_stcore/health",
    }
    say(f"Demo environment at {os.path.abspath(p['root'])}")
    any_up = False
    for name in SERVICES:
        pid = running_pid(p, name)
        healthy = http_ok(checks[name])
        any_up = any_up or healthy
        state = "running" if healthy else ("starting / unhealthy" if pid else "stopped")
        mark = "✓" if healthy else ("~" if pid else "·")
        say(f"  {mark} {name:<7} port {PORTS[name]:<5} {state}" + (f"  pid {pid}" if pid else ""))
    if any_up:
        say(f"\n  Web UI  http://localhost:{PORTS['ui']}")
        say(f"  Events  http://127.0.0.1:{PORTS['events']}")
    return 0


def cmd_reset(args):
    p = paths(args.dir)
    was_running = running_pid(p, "api") is not None
    for name in ("ui", "api"):
        terminate(p, name)
    for target in (p["data"], os.path.join(p["root"], "events.jsonl")):
        if os.path.isdir(target):
            shutil.rmtree(target, ignore_errors=True)
        elif os.path.exists(target):
            os.remove(target)
    say("Demo library, users and history cleared", "🧹 ")
    if was_running or args.restart:
        return cmd_up(args)
    say("   Run `python scripts/demo.py up` to start again with fresh sample data")
    return 0


def cmd_verify(args):
    """Prove the running demo actually works, end to end."""
    p = paths(args.dir)
    api_url = f"http://127.0.0.1:{PORTS['api']}"
    if not http_ok(f"{api_url}/health"):
        say("The demo is not running. Start it with `python scripts/demo.py up`.", "❌ ")
        return 1

    failures = 0
    say("Verifying the running demo", "🔍 ")

    with urllib.request.urlopen(f"{api_url}/health", timeout=10) as response:
        services = json.load(response).get("services", {})
    say(f"   API {services.get('api')}, vector store {services.get('chromadb')}, "
        f"model {services.get('model')}, OCR {services.get('ocr')}", "✓ ")

    say("   Rendering every page of the web interface...")
    smoke = subprocess.run([PYTHON, os.path.join(REPO, "scripts", "ui_smoke.py"),
                            os.path.join(REPO, "frontend", "streamlit_app.py")],
                           cwd=REPO, capture_output=True, text=True,
                           env={**os.environ, "BACKEND_URL": api_url, "ADMIN_PASSWORD": ADMIN_PASSWORD})
    pages = [line for line in smoke.stdout.splitlines() if line.startswith(("OK", "EXCEPTION"))]
    for line in pages:
        say(f"   {line}")
    if smoke.returncode != 0:
        failures += 1
        say("   A page raised an error", "❌ ")
    elif pages:
        say(f"   All {len(pages)} pages render", "✓ ")

    # A running model gives generated answers; without one they are cited excerpts.
    expected_mode = "generative" if services.get("model") == "healthy" else "extractive"
    say(f"   Asking a question (expecting a {expected_mode} answer)...")
    answer = subprocess.run([PYTHON, os.path.join(REPO, "scripts", "ci_check_answer.py"),
                             "--backend", api_url, "--password", ADMIN_PASSWORD,
                             "--expect-mode", expected_mode, "--wait", "60"],
                            cwd=REPO, capture_output=True, text=True)
    output = (answer.stdout.strip() + "\n" + answer.stderr.strip()).strip()
    for line in output.splitlines()[:3]:
        say(f"   {line}")
    if answer.returncode != 0:
        failures += 1
        say("   The question was not answered", "❌ ")

    events = os.path.join(p["root"], "events.jsonl")
    count = sum(1 for _ in open(events)) if os.path.exists(events) else 0
    say(f"   {count} notification(s) delivered to the event sink", "✓ " if count else "· ")

    say()
    say("Everything checks out" if not failures else f"{failures} check(s) failed",
        "✅ " if not failures else "❌ ")
    return 1 if failures else 0


def cmd_logs(args):
    p = paths(args.dir)
    name = args.service
    path = os.path.join(p["logs"], f"{name}.log")
    if not os.path.exists(path):
        say(f"No log for '{name}' yet at {path}", "· ")
        return 1
    subprocess.run(["tail", "-n", str(args.lines)] + (["-f"] if args.follow else []) + [path])
    return 0


def print_tour(args, model_running):
    ui = f"http://localhost:{PORTS['ui']}"
    api = f"http://127.0.0.1:{PORTS['api']}"
    events = f"http://127.0.0.1:{PORTS['events']}"
    say("=" * 72)
    say(f"  Local Legal AI is running at  {ui}")
    say("=" * 72)
    say()
    say("  Sign in as any of these:")
    say(f"    admin / {ADMIN_PASSWORD}                    administrator — sees everything")
    say("    associate / associate-demo-1     lawyer")
    say("    paralegal / paralegal-demo-1     standard user")
    say("    new.hire / Welcome-temp-1        must choose a password at first sign-in")
    say("    former.counsel                   disabled — sign-in is refused")
    say()
    say("  Things worth trying:")
    say("    1. Ask \"Can the tenant terminate the lease early, and what does it cost?\"")
    say("       — the answer cites the passages it came from."
        + ("" if model_running else " Without a model these are"))
    if not model_running:
        say("       the most relevant excerpts; restart with --with-model for generated answers.")
    say("    2. Ask \"What is the capital of France?\" — it refuses, because your documents")
    say("       do not cover it. Answers never come from the model's general knowledge.")
    say("    3. Document Library — search, filter, open a document, export the register.")
    say("    4. Upload a PDF, Word file, or a photo of a page (it is read with OCR).")
    inbox = os.path.relpath(os.path.join(args.dir, "data", "inbox", "contracts"), os.getcwd())
    say(f"    5. Drop a file into {inbox}/ and watch it get indexed automatically.")
    say("    6. Sign in as admin → Users: add someone, reset a password, disable an account.")
    say("    7. Sign in wrongly five times — the account locks, and the lockout is audited.")
    say("    8. Audit Log → Verify chain: every action is hash-chained and tamper-evident.")
    say("    9. Analytics: usage, response times, document similarity, who did what.")
    say(f"   10. Watch notifications arrive at {events} as you work.")
    say()
    say(f"  API docs   {api}/docs")
    say(f"  Logs       {os.path.join(args.dir, 'logs')}/   (python scripts/demo.py logs api -f)")
    say()
    say("  python scripts/demo.py verify    check it all works")
    say("  python scripts/demo.py reset     clean library, fresh sample data")
    say("  python scripts/demo.py down      stop everything")
    say()


def cmd_tour(args):
    print_tour(args, http_ok(f"http://127.0.0.1:{PORTS['model']}/v1/models"))
    return 0


def main():
    parser = argparse.ArgumentParser(
        description="Run the complete Local Legal AI product locally, for demos and testing.",
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dir", default=os.path.join(REPO, ".demo"),
                        help="where the demo keeps its data and logs (default: .demo)")
    parser.add_argument("--api-port", type=int, help="override the API port")
    parser.add_argument("--ui-port", type=int, help="override the web UI port")
    sub = parser.add_subparsers(dest="command")

    up = sub.add_parser("up", help="start everything and load the sample firm")
    up.add_argument("--with-model", action="store_true",
                    help="also run a local language model so answers are generated")
    up.add_argument("--no-seed", action="store_true", help="start empty, without sample data")
    up.add_argument("--model-timeout", type=int, default=900,
                    help="seconds to wait for the model (first run downloads it)")
    up.set_defaults(func=cmd_up)

    sub.add_parser("down", help="stop everything").set_defaults(func=cmd_down)
    sub.add_parser("status", help="show what is running").set_defaults(func=cmd_status)
    sub.add_parser("verify", help="health, every UI page, and a real answer").set_defaults(func=cmd_verify)
    sub.add_parser("tour", help="print the walkthrough again").set_defaults(func=cmd_tour)

    reset = sub.add_parser("reset", help="wipe the demo library and reload sample data")
    reset.add_argument("--restart", action="store_true", help="start again even if it was stopped")
    reset.set_defaults(func=cmd_reset, with_model=False, no_seed=False, model_timeout=900)

    logs = sub.add_parser("logs", help="show a service log")
    logs.add_argument("service", choices=SERVICES, nargs="?", default="api")
    logs.add_argument("-n", "--lines", type=int, default=50)
    logs.add_argument("-f", "--follow", action="store_true")
    logs.set_defaults(func=cmd_logs)

    args = parser.parse_args()
    if not getattr(args, "command", None):
        parser.print_help()
        return 0
    if args.api_port:
        PORTS["api"] = args.api_port
    if args.ui_port:
        PORTS["ui"] = args.ui_port
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
