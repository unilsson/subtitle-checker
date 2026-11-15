"""Deployment invariants: host port is configurable without changing app port."""
import sqlite3
import tempfile
import unittest
from pathlib import Path
from app.database import Store


ROOT = Path(__file__).resolve().parents[1]


class DeploymentTests(unittest.TestCase):
    def test_port_is_configurable_via_compose_env(self):
        compose = (ROOT / "compose.yaml").read_text(encoding="utf-8")
        config = (ROOT / ".env.example").read_text(encoding="utf-8")
        self.assertIn("${SUBTITLE_CHECKER_PORT:-8097}:8097", compose)
        self.assertIn("SUBTITLE_CHECKER_PORT=8097", config)
        self.assertIn('PORT: "8097"', compose)

    def test_sqlite_connection_is_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(str(Path(tmp) / "test.sqlite3"))
            with store.conn() as conn:
                self.assertEqual(conn.execute("SELECT 1").fetchone()[0], 1)
            with self.assertRaises(sqlite3.ProgrammingError):
                conn.execute("SELECT 1")


if __name__ == "__main__":
    unittest.main()
