"""
Global settings, thresholds, and API keys.
"""
import os
from pathlib import Path

# ── Paths ──────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite+aiosqlite:///{BASE_DIR / 'trading.db'}")
DATABASE_PATH = str(BASE_DIR / "trading.db")

# ── Scoring Weights ───────────────────────────────────────────────────
WEIGHTS = {
    "technical": 0.40,
    "fundamental": 0.30,
    "sentiment": 0.20,
    "risk": 0.10,
}

# ── Trading Thresholds ────────────────────────────────────────────────
MIN_TOTAL_SCORE = 65
MIN_TECHNICAL_SCORE = 50
MAX_VOLATILITY = 0.60  # 60%
STOP_LOSS_PCT = -0.03  # -3%
TAKE_PROFIT_PCT = 0.10  # +10%
MISTAKE_LOSS_THRESHOLD = -0.05  # -5%
MIN_TRADES_FOR_LEARNING = 10

# ── Scheduler ─────────────────────────────────────────────────────────
SCAN_INTERVAL_HOURS = 24  # daily scan
LEARN_INTERVAL_HOURS = 168  # weekly learn

# ── External APIs (set via env vars) ──────────────────────────────────
REDDIT_CLIENT_ID = os.getenv("REDDIT_CLIENT_ID", "")
REDDIT_CLIENT_SECRET = os.getenv("REDDIT_CLIENT_SECRET", "")
REDDIT_USER_AGENT = os.getenv("REDDIT_USER_AGENT", "trading-bot/1.0")

# ── Logging ───────────────────────────────────────────────────────────
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
