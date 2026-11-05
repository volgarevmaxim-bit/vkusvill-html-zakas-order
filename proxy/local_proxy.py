"""Локальный сервер селектора ВкусВилл: страница + прокси к MCP.

Зачем прокси: Qrator-WAF на mcp.vkusvill.ru отвечает 401 на preflight OPTIONS,
поэтому страница, открытая с GitHub Pages (https), не может вызвать MCP
напрямую — браузер блокирует запрос. Здесь страница и /mcp отдаются с одного
origin, CORS не нужен вообще.

Запуск:  python proxy/local_proxy.py [порт] [--lan]
         --lan — слушать 0.0.0.0 (для телефона в домашней сети)
Открыть: http://127.0.0.1:8770/
"""
import json
import pathlib
import sys
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROOT = pathlib.Path(__file__).resolve().parent.parent
UPSTREAM = "https://mcp.vkusvill.ru/mcp"
STATIC = {
    "/": ("vkusvill-selector.html", "text/html; charset=utf-8"),
    "/index.html": ("vkusvill-selector.html", "text/html; charset=utf-8"),
    "/sw.js": ("sw.js", "application/javascript; charset=utf-8"),
    "/manifest.json": ("manifest.json", "application/json; charset=utf-8"),
}
ARGS = [a for a in sys.argv[1:] if not a.startswith("--")]
PORT = int(ARGS[0]) if ARGS else 8770
BIND = "0.0.0.0" if "--lan" in sys.argv else "127.0.0.1"


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, GET, OPTIONS")
        self.send_header(
            "Access-Control-Allow-Headers",
            "Content-Type, Accept, Mcp-Session-Id, Authorization",
        )
        # Chrome Private Network Access: без этого заголовка запрос
        # с публичного https-сайта на 127.0.0.1 может быть заблокирован
        self.send_header("Access-Control-Allow-Private-Network", "true")
        self.send_header("Access-Control-Max-Age", "86400")

    def _send(self, code, body, ctype="application/json", extra=None):
        self.send_response(code)
        self._cors()
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        if body:
            self.wfile.write(body)

    def do_OPTIONS(self):  # preflight
        self._send(204, b"")

    def do_GET(self):
        path = self.path.split("?")[0]
        if path == "/health":
            self._send(200, json.dumps({"ok": True, "upstream": UPSTREAM}).encode())
            return
        if path == "/mcp":
            self._send(405, b'{"error":"use POST"}')
            return
        if path in STATIC:
            name, ctype = STATIC[path]
            f = ROOT / name
            if not f.exists():
                self._send(404, ("нет файла %s" % name).encode(), "text/plain; charset=utf-8")
                return
            extra = {"Cache-Control": "no-store"} if ctype.startswith("text/html") else {}
            self._send(200, f.read_bytes(), ctype, extra)
            return
        self._send(404, b'{"error":"not found"}')

    def do_POST(self):
        if self.path.split("?")[0] != "/mcp":
            self._send(404, b'{"error":"not found"}')
            return
        length = int(self.headers.get("Content-Length") or 0)
        data = self.rfile.read(length)
        req = urllib.request.Request(
            UPSTREAM,
            data=data,
            method="POST",
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json, text/event-stream",
                "User-Agent": "vkusvill-selector-proxy/1.1",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                code, body = resp.status, resp.read()
                ctype = resp.headers.get("Content-Type", "application/json")
        except urllib.error.HTTPError as exc:
            code, body = exc.code, exc.read()
            ctype = exc.headers.get("Content-Type", "application/json")
        except Exception as exc:  # сеть, таймаут, TLS
            code, ctype = 502, "application/json"
            body = json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False).encode()
        self._send(code, body, ctype)

    def log_message(self, fmt, *args):
        sys.stderr.write("%s %s\n" % (self.address_string(), fmt % args))


if __name__ == "__main__":
    srv = ThreadingHTTPServer((BIND, PORT), Handler)
    print("Страница:   http://127.0.0.1:%d/" % PORT)
    print("MCP прокси: http://127.0.0.1:%d/mcp  ->  %s" % (PORT, UPSTREAM))
    print("Слушаю: %s:%d" % (BIND, PORT))
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
