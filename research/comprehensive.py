"""
Aggregates all research factors into a single composite score (0-100).
"""
import config
from research.technical import get_technical_score
from research.fundamental import get_fundamental_score
from research.sentiment import get_sentiment_score
from utils.logger import get_logger
import numpy as np
import yfinance as yf

log = get_logger("comprehensive")


class ComprehensiveResearch:
    """Combines four independent scoring dimensions into a composite score."""

    def __init__(self, weights: dict | None = None):
        self.weights = weights or config.WEIGHTS.copy()

    # ── Risk Score ────────────────────────────────────────────────────
    def _get_risk_score(self, ticker: str) -> dict:
        stock = yf.Ticker(ticker)
        hist = stock.history(period="3mo", interval="1d")
        if hist.empty or len(hist) < 20:
            return {"volatility": 0, "vol_score": 50,
                    "max_drawdown": 0, "dd_score": 50, "composite": 50}

        close = hist["Close"]
        daily_ret = close.pct_change().dropna()
        annual_vol = float(daily_ret.std() * np.sqrt(252))

        if annual_vol < 0.20:
            vol_score = 100
        elif annual_vol < 0.40:
            vol_score = 70
        else:
            vol_score = 40

        # Max drawdown
        rolling_max = close.expanding().max()
        drawdown = (close - rolling_max) / rolling_max
        max_dd = float(drawdown.min())

        if max_dd > -0.10:
            dd_score = 100
        elif max_dd > -0.20:
            dd_score = 70
        else:
            dd_score = 40

        composite = vol_score * 0.6 + dd_score * 0.4

        return {
            "volatility": round(annual_vol * 100, 2),
            "vol_score": vol_score,
            "max_drawdown": round(max_dd * 100, 2),
            "dd_score": dd_score,
            "composite": round(composite, 2),
        }

    # ── Main Research ─────────────────────────────────────────────────
    def research(self, ticker: str) -> dict:
        log.info(f"Running comprehensive research for {ticker}")

        technical = get_technical_score(ticker)
        fundamental = get_fundamental_score(ticker)
        sentiment = get_sentiment_score(ticker)
        risk = self._get_risk_score(ticker)

        composite = (
            technical["composite"] * self.weights["technical"]
            + fundamental["composite"] * self.weights["fundamental"]
            + sentiment["score"] * self.weights["sentiment"]
            + risk["composite"] * self.weights["risk"]
        )

        return {
            "ticker": ticker,
            "price": technical.get("price"),
            "technical": technical,
            "fundamental": fundamental,
            "sentiment": sentiment,
            "risk": risk,
            "composite_score": round(composite, 2),
            "weights": self.weights,
        }
