"""Serialized background scans, so the browser remains responsive."""
from __future__ import annotations
from datetime import datetime, timezone, timedelta
from threading import Lock, Thread
from time import sleep
from .config import Settings
from .database import Store
from .providers import ProviderError, radarr_movies, opensubtitles_search


class Checker:
    def __init__(self, config: Settings, store: Store, radarr=radarr_movies, search=opensubtitles_search):
        self.config, self.store = config, store
        self.radarr, self.search = radarr, search
        self._lock = Lock()
        self._state = {"running": False, "action": None, "total": 0, "done": 0,
                       "current": None, "errors": 0, "message": None, "finished_at": None}

    def state(self):
        with self._lock:
            return dict(self._state)

    def _start(self, action, func):
        with self._lock:
            if self._state["running"]:
                return False
            self._state = {"running": True, "action": action, "total": 0,
                           "done": 0, "current": None, "errors": 0,
                           "message": None, "finished_at": None}
        Thread(target=self._run, args=(func,), daemon=True).start()
        return True

    def _run(self, func):
        try:
            func()
        except Exception as ex:
            with self._lock:
                self._state["message"] = f"Misslyckades: {str(ex)[:300]}"
        finally:
            with self._lock:
                self._state["running"] = False
                self._state["current"] = None
                self._state["finished_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
                if not self._state["message"]:
                    self._state["message"] = "Klart"

    def sync(self):
        return self._start("sync", self._sync)

    def _sync(self):
        rows = self.radarr(self.config.radarr_url, self.config.radarr_api_key)
        out = self.store.sync_movies(rows)
        with self._lock:
            self._state["message"] = f"Synkade {out['total']} filmer ({out['missing']} utan fil)."

    def scan(self, movie_id=None, force=False):
        return self._start("scan", lambda: self._scan(movie_id=movie_id, force=force))

    def _scan(self, movie_id=None, force=False):
        if not self.config.opensubtitles_api_key:
            raise ProviderError("OPENSUBTITLES_API_KEY saknas")
        movies = self.store.all_movies()
        if movie_id is not None:
            movies = [m for m in movies if m["id"] == movie_id]
            if not movies:
                raise ProviderError("Filmen finns inte eller har redan en videofil")
        if not force:
            cutoff = datetime.now(timezone.utc) - timedelta(hours=self.config.cache_hours)
            movies = [m for m in movies if not m["checked_at"] or datetime.fromisoformat(m["checked_at"]) < cutoff]
        if self.config.max_scan_movies and movie_id is None:
            movies = movies[:self.config.max_scan_movies]
        with self._lock:
            self._state["total"] = len(movies)
        for index, movie in enumerate(movies):
            with self._lock:
                self._state["current"] = movie["title"]
            try:
                sv = self.search(self.config.opensubtitles_api_key, movie, "sv")
                sleep(self.config.request_delay_ms / 1000)
                en = self.search(self.config.opensubtitles_api_key, movie, "en")
                self.store.result(movie["id"], sv, en, sv["method"])
            except Exception as e:
                self.store.error(movie["id"], str(e))
                with self._lock:
                    self._state["errors"] += 1
            finally:
                with self._lock:
                    self._state["done"] = index + 1
                sleep(self.config.request_delay_ms / 1000)
        with self._lock:
            self._state["message"] = f"Kontrollerade {len(movies)} filmer. Fel: {self._state['errors']}."

    def maybe_auto_scan(self):
        if not self.config.auto_scan_hours:
            return
        def loop():
            # No automatic sync or scan before explicit user setup and first visit.
            while True:
                sleep(self.config.auto_scan_hours * 3600)
                if self.config.radarr_api_key and self.config.opensubtitles_api_key:
                    if self.sync():
                        while self.state()["running"]:
                            sleep(1)
                        self.scan()
        Thread(target=loop, daemon=True).start()
