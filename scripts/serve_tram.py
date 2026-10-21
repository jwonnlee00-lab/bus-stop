"""Serve only the tram UI and its two public data files on loopback."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
FILES = {
    "/web/tram/": ("web/tram/index.html", "text/html; charset=utf-8"),
    "/web/tram/index.html": ("web/tram/index.html", "text/html; charset=utf-8"),
    "/web/tram/style.css": ("web/tram/style.css", "text/css; charset=utf-8"),
    "/web/tram/app.mjs": ("web/tram/app.mjs", "text/javascript; charset=utf-8"),
    "/web/tram/router.mjs": ("web/tram/router.mjs", "text/javascript; charset=utf-8"),
    "/data/tram_stations_estimated.csv": ("data/tram_stations_estimated.csv", "text/csv; charset=utf-8"),
    "/data/tram_edges.json": ("data/tram_edges.json", "application/json; charset=utf-8"),
}


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        path = urlsplit(self.path).path
        if path == "/":
            self.send_response(302)
            self.send_header("Location", "/web/tram/")
            self.end_headers()
            return
        if path not in FILES:
            self.send_error(404)
            return
        relative, content_type = FILES[path]
        try:
            body = (ROOT / relative).read_bytes()
        except OSError:
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)


if __name__ == "__main__":
    print("http://127.0.0.1:8766/web/tram/", flush=True)
    try:
        ThreadingHTTPServer(("127.0.0.1", 8766), Handler).serve_forever()
    except KeyboardInterrupt:
        pass
