"""
News / Reddit / Twitter sentiment scoring.
In dev mode (no API keys), returns a seeded neutral score.
"""
import random
import config
from utils.logger import get_logger

log = get_logger("sentiment")


def get_sentiment_score(ticker: str) -> dict:
    """
    Returns sentiment composite (0-100).
    In production, wire up Reddit r/wallstreetbets + HuggingFace finbert.
    In dev, returns a seeded pseudo-random neutral score for reproducibility.
    """
    seed_val = sum(ord(c) for c in ticker)
    rng = random.Random(seed_val)

    if config.REDDIT_CLIENT_ID and config.REDDIT_CLIENT_SECRET:
        # TODO: live Reddit + finbert sentiment
        score = _live_sentiment(ticker)
    else:
        # Dev mode: neutral-ish score
        score = rng.randint(40, 70)
        log.info(f"[DEV] Seeded sentiment for {ticker}: {score}")

    return {
        "score": score,
        "source": "live" if config.REDDIT_CLIENT_ID else "seeded",
    }


def _live_sentiment(ticker: str) -> int:
    """Placeholder for live sentiment integration."""
    # Future: fetch Reddit posts, run through finbert, aggregate
    return 50
