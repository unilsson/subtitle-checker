"""API clients: only read metadata from Radarr and OpenSubtitles.

Never accepts URLs from web requests. URL roots are fixed in configuration.
"""
from __future__ import annotations
import json
import re
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

OS_API = "https://api.opensubtitles.com/api/v1"
AGENT = "SubtitleChecker v0.2.0"


class ProviderError(Exception):
    pass


def request_json(url: str, headers: dict, *, retries: int = 2, timeout: int = 25) -> dict | list:
    for attempt in range(retries + 1):
        req = Request(url, headers={"Accept": "application/json", **headers})
        try:
            with urlopen(req, timeout=timeout) as r:
                return json.load(r)
        except HTTPError as e:
            if e.code in (429, 500, 502, 503, 504) and attempt < retries:
                try:
                    delay = min(max(float(e.headers.get("Retry-After", 2)), 1), 20)
                except (ValueError, TypeError):
                    delay = 2
                time.sleep(delay * (attempt + 1))
                continue
            desc = {401: "Ogiltiga inloggningsuppgifter", 403: "API-nyckeln nekas", 429: "API-begränsning (429)"}.get(e.code, f"HTTP {e.code}")
            raise ProviderError(desc) from e
        except (URLError, TimeoutError, OSError) as e:
            if attempt < retries:
                time.sleep(1 + attempt)
                continue
            raise ProviderError(f"Anslutningen misslyckades: {type(e).__name__}") from e
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            raise ProviderError("API:et returnerade inte giltig JSON") from e
    raise ProviderError("API-fel")


def radarr_movies(base: str, api_key: str) -> list[dict]:
    if not api_key:
        raise ProviderError("RADARR_API_KEY saknas")
    rows = request_json(f"{base}/api/v3/movie", {"X-Api-Key": api_key})
    if not isinstance(rows, list):
        raise ProviderError("Radarr gav ett oväntat svar")
    return rows


def normalize_imdb(value: str | None) -> str | None:
    """OpenSubtitles canonical IMDb key: numeric part with no leading zeros."""
    if not value:
        return None
    m = re.fullmatch(r"(?:tt)?(\d{1,12})", str(value).strip(), flags=re.I)
    if not m:
        return None
    return str(int(m.group(1)))


def canonical_search_params(movie: dict, language: str) -> dict[str, str]:
    params = {"languages": language}
    imdb = normalize_imdb(movie.get("imdb_id"))
    if imdb:
        params["imdb_id"] = imdb
    else:
        title = str(movie.get("title") or "").strip()
        if not title:
            raise ProviderError("Filmen saknar både IMDb-ID och titel")
        params["query"] = title.lower()
        if movie.get("year"):
            params["year"] = str(movie["year"])
    return dict(sorted(params.items()))


def normalize_subtitle(row: dict) -> dict | None:
    a = row.get("attributes") or {}
    if not isinstance(a, dict):
        return None
    files = a.get("files") or []
    if not isinstance(files, list):
        files = []
    file_id = next((f.get("file_id") for f in files if isinstance(f, dict) and f.get("file_id")), None)
    feature = a.get("feature_details") if isinstance(a.get("feature_details"), dict) else {}
    return {
        "subtitle_id": str(row.get("id") or ""),
        "language": a.get("language") or "",
        "release": str(a.get("release") or feature.get("movie_name") or "")[:260],
        "downloads": a.get("download_count") or 0,
        "hearing_impaired": bool(a.get("hearing_impaired")),
        "machine_translated": bool(a.get("machine_translated") or a.get("ai_translated")),
        "file_id": file_id,
        "page_url": a.get("url") or "",
        "format": str(a.get("format") or ""),
    }


def opensubtitles_search(key: str, movie: dict, language: str) -> dict:
    if not key:
        raise ProviderError("OPENSUBTITLES_API_KEY saknas")
    params = canonical_search_params(movie, language)
    url = f"{OS_API}/subtitles?{urlencode(params)}"
    raw = request_json(url, {"Api-Key": key, "User-Agent": AGENT})
    if not isinstance(raw, dict) or not isinstance(raw.get("data"), list):
        raise ProviderError("OpenSubtitles gav ett oväntat svar")
    results = [x for r in raw["data"] if (x := normalize_subtitle(r)) is not None]
    results = [x for x in results if x["language"] in (language, "")]
    results.sort(key=lambda x: (x["machine_translated"], x["hearing_impaired"], -(int(x["downloads"]) if str(x["downloads"]).isdigit() else 0)))
    total = raw.get("total_count")
    if not isinstance(total, int) or total < len(results):
        total = len(results)
    return {"count": total, "results": results[:50], "method": "imdb" if "imdb_id" in params else "title",
            "incomplete": total > len(results)}

def radarr_releases(base: str, api_key: str, movie_id: int) -> dict:
    """Read-only Radarr Interactive Search for one EXISTING movie id."""
    if not api_key:
        raise ProviderError("RADARR_API_KEY saknas")
    if type(movie_id) is not int or movie_id < 1:
        raise ProviderError("Ogiltigt Radarr movieId")
    payload = request_json(f"{base}/api/v3/release?{urlencode({'movieId': movie_id})}",
                           {"X-Api-Key": api_key}, timeout=90)
    if not isinstance(payload, list):
        raise ProviderError("Radarr returnerade inte en lista med releaser")
    items = []
    for row in payload[:200]:
        if not isinstance(row, dict):
            continue
        quality = row.get('quality') or {}
        q = quality.get('quality') or {} if isinstance(quality, dict) else {}
        if not isinstance(q, dict):
            q = {}
        reasons = row.get('rejections') or []
        if not isinstance(reasons, list):
            reasons = []
        items.append({
            'title': str(row.get('title') or '')[:320],
            'indexer': str(row.get('indexer') or '')[:120],
            'quality': str(q.get('name') or '')[:80],
            'size': row.get('size') if type(row.get('size')) is int else None,
            'rejected': bool(row.get('rejected') or reasons),
            'rejections': [str(reason)[:150] for reason in reasons[:4]],
            'protocol': str(row.get('protocol') or '')[:30],
        })
    return {'count': len(payload), 'releases': items, 'incomplete': len(payload) > len(items)}
