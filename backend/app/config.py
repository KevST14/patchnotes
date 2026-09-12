import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = Path(os.environ.get("PATCHNOTES_DB_PATH", BASE_DIR / "data" / "patchnotes.db"))

# How often every source is re-fetched, in seconds.
FETCH_INTERVAL_SECONDS = int(os.environ.get("FETCH_INTERVAL_SECONDS", "600"))

# Stories older than this are pruned (saved stories are always kept).
RETENTION_DAYS = int(os.environ.get("RETENTION_DAYS", "30"))

# On an empty database, pull this many days of popular Hacker News stories so
# trends and the quiz have some history to work with straight away.
BACKFILL_DAYS = int(os.environ.get("BACKFILL_DAYS", "7"))

# Optional: a GitHub token lifts the search API's rate limit. Not required.
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")

# Origin allowed to call the API (the Vite dev server, or a deployed frontend).
FRONTEND_ORIGIN = os.environ.get("FRONTEND_ORIGIN", "http://localhost:5173")

USER_AGENT = "PatchNotes/0.1 (personal news reader; +https://github.com/)"

DB_PATH.parent.mkdir(parents=True, exist_ok=True)
