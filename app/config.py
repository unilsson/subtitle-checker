from dataclasses import dataclass
from pathlib import Path
import os


def _integer(name: str, default: int, minimum: int = 0) -> int:
    try:
        return max(minimum, int(os.environ.get(name, str(default))))
    except ValueError:
        return default


@dataclass(frozen=True)
class Settings:
    radarr_url: str = os.environ.get("RADARR_URL", "http://radarr:7878").rstrip("/")
    radarr_api_key: str = os.environ.get("RADARR_API_KEY", "")
    opensubtitles_api_key: str = os.environ.get("OPENSUBTITLES_API_KEY", "")
    db_path: str = os.environ.get("DB_PATH", "/data/subtitle-checker.sqlite3")
    port: int = _integer("PORT", 8097, 1)
    cache_hours: int = _integer("CACHE_HOURS", 24, 1)
    auto_scan_hours: int = _integer("AUTO_SCAN_HOURS", 0, 0)
    request_delay_ms: int = _integer("REQUEST_DELAY_MS", 500, 250)
    max_scan_movies: int = _integer("MAX_SCAN_MOVIES", 0, 0)

    def diagnostics(self):
        return {
            "radarr_configured": bool(self.radarr_api_key),
            "opensubtitles_configured": bool(self.opensubtitles_api_key),
            "radarr_url": self.radarr_url,
            "cache_hours": self.cache_hours,
            "auto_scan_hours": self.auto_scan_hours,
            "max_scan_movies": self.max_scan_movies,
        }
