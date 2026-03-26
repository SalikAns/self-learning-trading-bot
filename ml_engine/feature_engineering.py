"""
Transforms raw research data into ML-ready feature vectors.
"""
import numpy as np


def build_feature_vector(research: dict) -> list[float]:
    """
    Flatten a research dict into a numeric feature vector for ML models.
    Features (14 total):
        0: composite_score
        1-3: technical (rsi_score, trend_score, volume_score)
        4-7: fundamental (pe_score, growth_score, margin_score, de_score)
        8: sentiment_score
        9-10: risk (vol_score, dd_score)
        11: price (normalised placeholder — model should learn relative)
        12: volatility_pct
        13: volume_ratio
    """
    t = research.get("technical", {})
    f = research.get("fundamental", {})
    s = research.get("sentiment", {})
    r = research.get("risk", {})

    return [
        research.get("composite_score", 50),
        t.get("rsi_score", 50),
        t.get("trend_score", 50),
        t.get("volume_score", 50),
        f.get("pe_score", 50),
        f.get("growth_score", 50),
        f.get("margin_score", 50),
        f.get("de_score", 50),
        s.get("score", 50),
        r.get("vol_score", 50),
        r.get("dd_score", 50),
        t.get("price") or 0,
        r.get("volatility") or 0,
        t.get("volume_ratio") or 1,
    ]


FEATURE_NAMES = [
    "composite", "rsi_score", "trend_score", "volume_score",
    "pe_score", "growth_score", "margin_score", "de_score",
    "sentiment", "vol_score", "dd_score", "price",
    "volatility_pct", "volume_ratio",
]
