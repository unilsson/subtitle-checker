"""Zero-dependency HTTP API + static dashboard; local network use only."""
from __future__ import annotations
import json
import logging
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit
from .config import Settings
from .database import Store
from .service import Checker
from . import __version__

STATIC = Path(__file__).resolve().parent / "static"
FILES = {"/": ("index.html", "text/html; charset=utf-8"),
         "/app.js": ("app.js", "application/javascript; charset=utf-8"),
         "/style.css": ("style.css", "text/css; charset=utf-8")}


def make_handler(config, store, checker):
    class Handler(BaseHTTPRequestHandler):
        server_version = f"SubtitleChecker/{__version__}"

        def log_message(self, fmt, *args):
            logging.info("%s %s", self.address_string(), fmt % args)

        def send(self, code, data, kind="application/json; charset=utf-8"):
            raw = (json.dumps(data, ensure_ascii=False).encode("utf-8")
                   if kind.startswith("application/json") else data)
            self.send_response(code)
            self.send_header("Content-Type", kind)
            self.send_header("Content-Length", str(len(raw)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("X-Frame-Options", "DENY")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self'; base-uri 'none'; frame-ancestors 'none'")
            self.end_headers()
            self.wfile.write(raw)

        def do_GET(self):
            path = urlsplit(self.path).path
            if path in FILES:
                filename, kind = FILES[path]
                self.send(200, (STATIC / filename).read_bytes(), kind)
                return
            if path == "/health":
                self.send(200, {"ok": True, "version": __version__})
                return
            if path == "/api/status":
                rows = store.all_movies()
                self.send(200, {"version": __version__, "job": checker.state(),
                                "settings": config.diagnostics(),
                                "summary": {
                                   "missing": len(rows),
                                   "checked": sum(r["checked_at"] is not None for r in rows),
                                   "swedish": sum((r["sv_count"] or 0) > 0 for r in rows),
                                   "english_only": sum(r["sv_count"] == 0 and (r["en_count"] or 0) > 0 for r in rows),
                                   "none": sum(r["sv_count"] == 0 and r["en_count"] == 0 for r in rows),
                                   "errors": sum(r["error"] is not None or r.get('release_error') is not None for r in rows),
                                   "release_checked": sum(r.get('release_checked_at') is not None for r in rows),
                                   "sv_release_match": sum(r.get('release_matches',{}).get('sv_candidates',0)>0 for r in rows),
                                }})
                return
            if path == "/api/movies":
                self.send(200, {"movies": store.all_movies()})
                return
            self.send(404, {"error": "Okänd adress"})

        def do_POST(self):
            # Browser cross-origin POST attempts are rejected, and JSON + custom header
            # prevents an ordinary HTML form from launching scans on the LAN.
            origin = self.headers.get("Origin")
            host = self.headers.get("Host")
            if (origin and urlsplit(origin).netloc != host) or self.headers.get("X-Requested-With") != "SubtitleChecker":
                self.send(403, {"error": "Otillåten begäran"})
                return
            if not self.headers.get("Content-Type", "").lower().startswith("application/json"):
                self.send(415, {"error": "JSON krävs"})
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
            except ValueError:
                length = -1
            if length < 0 or length > 4096:
                self.send(400, {"error": "Ogiltig begäran"})
                return
            try:
                payload = json.loads(self.rfile.read(length)) if length else {}
                if not isinstance(payload, dict):
                    raise ValueError()
            except (ValueError, UnicodeDecodeError):
                self.send(400, {"error": "Ogiltig JSON"})
                return
            path = urlsplit(self.path).path
            if path == "/api/sync":
                if not config.radarr_api_key:
                    self.send(400, {"error": "Konfigurera RADARR_API_KEY först"})
                    return
                started = checker.sync()
            elif path == "/api/scan":
                if not config.opensubtitles_api_key:
                    self.send(400, {"error": "Konfigurera OPENSUBTITLES_API_KEY först"})
                    return
                try:
                    mid = int(payload["movie_id"]) if payload.get("movie_id") is not None else None
                    if mid is not None and mid < 1:
                        raise ValueError()
                except (ValueError, TypeError, OverflowError):
                    self.send(400, {"error": "Ogiltigt film-ID"})
                    return
                started = checker.scan(movie_id=mid, force=bool(payload.get("force", False)))
            else:
                self.send(404, {"error": "Okänd adress"})
                return
            self.send(202 if started else 409,
                      {"started": started, "error": None if started else "En annan körning pågår"})

    return Handler


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    config = Settings()
    store = Store(config.db_path)
    checker = Checker(config, store)
    checker.maybe_auto_scan()
    httpd = ThreadingHTTPServer(("0.0.0.0", config.port), make_handler(config, store, checker))
    print(f"Subtitle Checker {__version__}: http://0.0.0.0:{config.port}", flush=True)
    httpd.serve_forever()


if __name__ == "__main__":
    main()
