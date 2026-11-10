"""Local HTTP server for the return-desk UI and JSON APIs."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from urllib.parse import parse_qs, urlsplit

from .config import DEMO_DATE, ROOT, STORE


def create_server(desk, port):
    class Handler(BaseHTTPRequestHandler):
        def send_body(self, status, payload, mime="application/json"):
            body = json.dumps(payload, ensure_ascii=False).encode() if mime == "application/json" else payload
            self.send_response(status)
            self.send_header("Content-Type", mime + "; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header(
                "Content-Security-Policy",
                "default-src 'self'; frame-ancestors 'none'; base-uri 'none'",
            )
            self.end_headers()
            self.wfile.write(body)

        def valid_host(self):
            return self.headers.get("Host") in {
                f"127.0.0.1:{self.server.server_port}",
                f"localhost:{self.server.server_port}",
            }

        def do_GET(self):
            if not self.valid_host():
                return self.send_body(403, {"error": "Use the local demo address."})
            url = urlsplit(self.path)
            assets = {
                "/": ("index.html", "text/html"),
                "/style.css": ("style.css", "text/css"),
                "/app.js": ("app.js", "text/javascript"),
            }
            if url.path in assets:
                name, mime = assets[url.path]
                return self.send_body(200, (ROOT / "static" / name).read_bytes(), mime)
            if url.path == "/api/search":
                query = parse_qs(url.query).get("q", [""])[0][:180]
                return self.send_body(200, {"results": desk.search(query)})
            if url.path == "/api/policies":
                return self.send_body(
                    200,
                    {
                        "policies": list(desk.policies.values()),
                        "store": STORE,
                        "date": DEMO_DATE.isoformat(),
                        "openai": bool(desk.api_key),
                    },
                )
            return self.send_body(404, {"error": "Page not found."})

        def do_POST(self):
            if not self.valid_host():
                return self.send_body(403, {"error": "Use the local demo address."})
            if self.path != "/api/chat":
                return self.send_body(404, {"error": "Page not found."})
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= 8192 or self.headers.get_content_type() != "application/json":
                    raise ValueError
                data = json.loads(self.rfile.read(length))
                if not isinstance(data, dict) or not isinstance(data.get("message"), str):
                    raise ValueError
                message = data["message"].strip()
                context = data.get("context", {})
                if not 0 < len(message) <= 600 or not isinstance(context, dict):
                    raise ValueError
            except ValueError:
                return self.send_body(400, {"error": "Enter a question of 1–600 characters."})
            return self.send_body(200, desk.chat(message, context))

        def log_message(self, _format, *args):
            pass  # Keep free text and order details out of request logs.

    return ThreadingHTTPServer(("127.0.0.1", port), Handler)
