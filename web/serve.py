#!/usr/bin/env python3
"""Tiny static server for the Local Legal AI web demo.

Serves this folder with the cache headers the demo expects, so editing a JS
module and reloading always picks up the new file.

    python3 web/serve.py [--port 8777]   → http://127.0.0.1:8777/

This is a development convenience only; the built site in dist/legal-ai-demo/
is plain static files and needs no server of its own.
"""
import argparse
import os
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

WEB_DIR = os.path.dirname(os.path.abspath(__file__))


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=WEB_DIR, **kwargs)

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        super().end_headers()

    def log_message(self, fmt, *args):
        if not self.path.startswith("/favicon"):
            super().log_message(fmt, *args)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8777)
    parser.add_argument("--host", default="127.0.0.1")
    args = parser.parse_args()

    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"Local Legal AI demo → http://{args.host}:{args.port}/   (Ctrl-C to stop)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    main()
