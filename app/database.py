from __future__ import annotations
import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Store:
    def __init__(self, path: str):
        self.path = path
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.initialize()

    @contextmanager
    def conn(self):
        c = sqlite3.connect(self.path, timeout=15)
        try:
            c.row_factory = sqlite3.Row
            c.execute("PRAGMA journal_mode=WAL")
            c.execute("PRAGMA busy_timeout=15000")
            yield c
            c.commit()
        except BaseException:
            c.rollback()
            raise
        finally:
            c.close()

    def initialize(self):
        with self.conn() as c:
            c.execute("""CREATE TABLE IF NOT EXISTS movies (
                id INTEGER PRIMARY KEY,
                title TEXT NOT NULL,
                year INTEGER,
                imdb_id TEXT,
                monitored INTEGER NOT NULL DEFAULT 1,
                has_file INTEGER NOT NULL DEFAULT 0,
                radarr_synced_at TEXT,
                checked_at TEXT,
                sv_count INTEGER,
                en_count INTEGER,
                match_method TEXT,
                results_json TEXT,
                error TEXT
            )""")
            c.execute("CREATE INDEX IF NOT EXISTS idx_movies_missing ON movies(has_file, checked_at)")

    def sync_movies(self, movies: list[dict]) -> dict:
        ids = []
        now = utcnow()
        with self.conn() as c:
            for m in movies:
                try:
                    movie_id = int(m["id"])
                except (KeyError, ValueError, TypeError):
                    continue
                ids.append(movie_id)
                title = str(m.get("title") or "Okänd film")[:300]
                year = m.get("year")
                imdb = m.get("imdbId") or None
                has_file = int(bool(m.get("hasFile", bool(m.get("movieFile")))))
                monitored = int(bool(m.get("monitored", True)))
                c.execute("""INSERT INTO movies(id,title,year,imdb_id,monitored,has_file,radarr_synced_at)
                   VALUES(?,?,?,?,?,?,?)
                   ON CONFLICT(id) DO UPDATE SET
                    title=excluded.title, year=excluded.year,
                    imdb_id=excluded.imdb_id, monitored=excluded.monitored,
                    has_file=excluded.has_file, radarr_synced_at=excluded.radarr_synced_at,
                    checked_at=CASE WHEN movies.imdb_id IS NOT excluded.imdb_id OR movies.title IS NOT excluded.title
                         THEN NULL ELSE movies.checked_at END,
                    sv_count=CASE WHEN movies.imdb_id IS NOT excluded.imdb_id OR movies.title IS NOT excluded.title
                         THEN NULL ELSE movies.sv_count END,
                    en_count=CASE WHEN movies.imdb_id IS NOT excluded.imdb_id OR movies.title IS NOT excluded.title
                         THEN NULL ELSE movies.en_count END,
                    results_json=CASE WHEN movies.imdb_id IS NOT excluded.imdb_id OR movies.title IS NOT excluded.title
                         THEN NULL ELSE movies.results_json END,
                    error=CASE WHEN movies.imdb_id IS NOT excluded.imdb_id OR movies.title IS NOT excluded.title
                         THEN NULL ELSE movies.error END
                """, (movie_id,title,year,imdb,monitored,has_file,now))
            # Prune deleted Radarr entries only on a successful, fully parsed sync.
            if ids:
                c.execute(f"DELETE FROM movies WHERE id NOT IN ({','.join('?' for _ in ids)})", ids)
            else:
                c.execute("DELETE FROM movies")
        return {"total": len(ids), "missing": sum(not (x.get('hasFile') or x.get('movieFile')) for x in movies)}

    def all_movies(self, missing_only=True):
        with self.conn() as c:
            rows = c.execute("SELECT * FROM movies WHERE has_file=0 ORDER BY title COLLATE NOCASE" if missing_only else "SELECT * FROM movies ORDER BY title COLLATE NOCASE").fetchall()
        return [self.to_dict(r) for r in rows]

    def one_movie(self, movie_id: int):
        with self.conn() as c:
            row = c.execute("SELECT * FROM movies WHERE id=?", (movie_id,)).fetchone()
        return self.to_dict(row) if row else None

    @staticmethod
    def to_dict(r):
        x = dict(r)
        try:
            x["results"] = json.loads(x.pop("results_json") or "{}")
        except json.JSONDecodeError:
            x["results"] = {}
        x["has_file"] = bool(x["has_file"])
        x["monitored"] = bool(x["monitored"])
        return x

    def result(self, movie_id: int, sv: dict, en: dict, method: str):
        with self.conn() as c:
            c.execute("""UPDATE movies SET checked_at=?, sv_count=?, en_count=?,
                  match_method=?, results_json=?, error=NULL WHERE id=?""",
                  (utcnow(), sv["count"], en["count"], method,
                   json.dumps({"sv": sv["results"], "en": en["results"]}, ensure_ascii=False),movie_id))

    def error(self, movie_id: int, message: str):
        with self.conn() as c:
            c.execute("UPDATE movies SET error=? WHERE id=?", (str(message)[:500], movie_id))
