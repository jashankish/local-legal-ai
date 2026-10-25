"""Local stand-in for Slack and n8n, so the demo can show real event delivery.

The application posts notifications to whatever webhook URLs it is configured
with. Pointing those at this process means uploads, deletions, sign-in failures
and lockouts show up somewhere visible without setting up Slack or n8n.

Received events are appended to <dir>/events.jsonl and rendered at the root URL,
newest first. When a signing secret is given, each event's
`X-LegalAI-Signature` header is checked and the result recorded, which
demonstrates that the payloads really are signed.

Usage: python scripts/demo_event_sink.py --dir .demo --port 8012 [--secret ...]
"""

import argparse
import html
import json
import os
import sys
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

PAGE = """<!doctype html>
<html><head><meta charset="utf-8"><title>Local Legal AI - event sink</title>
<meta http-equiv="refresh" content="5">
<style>
 body{{font-family:-apple-system,Segoe UI,Roboto,sans-serif;margin:2rem auto;max-width:60rem;color:#1f2937}}
 h1{{font-size:1.4rem}} .sub{{color:#6b7280;margin-bottom:1.5rem}}
 .e{{border:1px solid #e5e7eb;border-left:4px solid #1e3a8a;border-radius:6px;padding:.75rem 1rem;margin:.6rem 0}}
 .e.security{{border-left-color:#dc2626}} .t{{color:#6b7280;font-size:.85rem}}
 .n{{font-weight:600}} .ok{{color:#15803d}} .bad{{color:#dc2626}}
 pre{{background:#f3f5f9;padding:.5rem;border-radius:4px;overflow-x:auto;font-size:.8rem;margin:.4rem 0 0}}
 .empty{{color:#6b7280;border:1px dashed #d1d5db;border-radius:6px;padding:2rem;text-align:center}}
</style></head><body>
<h1>Event sink</h1>
<div class="sub">Notifications the application has sent. Stands in for Slack and n8n. Refreshes every 5s.</div>
{body}
</body></html>"""


def render(events):
    if not events:
        return ('<div class="empty">No events yet. Upload or delete a document, or sign in with '
                'the wrong password, and it will appear here.</div>')
    blocks = []
    for item in reversed(events[-50:]):
        event = item.get("event", {})
        # n8n-shaped posts carry the event name; Slack-shaped ones carry only prose.
        name = event.get("event") or ("Slack message" if item.get("text") else "event")
        kind = "security" if str(name).startswith("security.") else ""
        signature = item.get("signature")
        if signature is True:
            sig = '<span class="ok">signature valid</span>'
        elif signature is False:
            sig = '<span class="bad">SIGNATURE INVALID</span>'
        else:
            sig = '<span class="t">unsigned</span>'
        detail = html.escape(json.dumps(event.get("details", {}), indent=2)) if event.get("details") else ""
        blocks.append(
            f'<div class="e {kind}"><div class="n">{html.escape(str(name))}</div>'
            f'<div class="t">{html.escape(item["received_at"])} &middot; {html.escape(item["path"])} &middot; {sig}</div>'
            + (f'<pre>{detail}</pre>' if detail else "")
            + (f'<div>{html.escape(str(item["text"]))}</div>' if item.get("text") else "")
            + "</div>")
    return "\n".join(blocks)


def build_handler(log_path, secret):
    events = []
    if os.path.exists(log_path):
        with open(log_path) as handle:
            for line in handle:
                try:
                    events.append(json.loads(line))
                except ValueError:
                    pass

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path.startswith("/events"):
                payload = json.dumps(events[-200:]).encode()
                content_type = "application/json"
            else:
                payload = PAGE.format(body=render(events)).encode()
                content_type = "text/html; charset=utf-8"
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def do_POST(self):
            body = self.rfile.read(int(self.headers.get("Content-Length", 0) or 0))
            record = {"received_at": datetime.now().isoformat(timespec="seconds"), "path": self.path}
            try:
                payload = json.loads(body or b"{}")
            except ValueError:
                payload = {"raw": body.decode("utf-8", "replace")}
            # Slack-shaped posts carry {"text": ...}; n8n-shaped posts carry the event itself.
            if isinstance(payload, dict) and set(payload) == {"text"}:
                record["text"] = payload["text"]
            else:
                record["event"] = payload
            header = self.headers.get("X-LegalAI-Signature")
            if secret and header:
                from backend.integrations import verify_signature
                record["signature"] = verify_signature(body, secret, header)
            events.append(record)
            with open(log_path, "a") as handle:
                handle.write(json.dumps(record) + "\n")
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"ok")

        def log_message(self, *args):
            pass

    return Handler


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dir", default=".demo")
    parser.add_argument("--port", type=int, default=8012)
    parser.add_argument("--secret", default=os.getenv("WEBHOOK_SECRET"))
    args = parser.parse_args()

    os.makedirs(args.dir, exist_ok=True)
    log_path = os.path.join(args.dir, "events.jsonl")
    server = ThreadingHTTPServer(("127.0.0.1", args.port), build_handler(log_path, args.secret))
    print(f"Event sink on http://127.0.0.1:{args.port} (log: {log_path})", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
