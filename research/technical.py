"""
RSI, MACD, moving averages, volume analysis.
"""
import numpy as np
import pandas as pd
import yfinance as yf
from utils.logger import get_logger

log = get_logger("technical")


def _rsi(series: pd.Series, period: int = 14) -> float:
    """Compute RSI from closing prices."""
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.rolling(window=period, min_periods=period).mean()
    avg_loss = loss.rolling(window=period, min_periods=period).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))
    return float(rsi.iloc[-1]) if not rsi.empty else 50.0


def _sma(series: pd.Series, window: int) -> float:
    sma = series.rolling(window=window, min_periods=window).mean()
    return float(sma.iloc[-1]) if not sma.empty else float(series.iloc[-1])


def get_technical_score(ticker: str) -> dict:
    """Return dict with sub-signals and composite score (0-100)."""
    stock = yf.Ticker(ticker)
    hist = stock.history(period="6mo", interval="1d")

    if hist.empty or len(hist) < 50:
        log.warning(f"Insufficient history for {ticker}")
        return {"composite": 50, "price": None, "rsi": 50, "rsi_score": 50,
                "sma20": None, "sma50": None, "trend_score": 50,
                "volume_ratio": 1.0, "volume_score": 50}

    close = hist["Close"]
    volume = hist["Volume"]
    price = float(close.iloc[-1])

    # ── RSI (weight 0.3) ──────────────────────────────────────────────
    rsi = _rsi(close)
    if 40 <= rsi <= 60:
        rsi_score = 100
    elif 30 <= rsi < 40 or 60 < rsi <= 70:
        rsi_score = 70
    elif rsi < 30 or rsi > 70:
        rsi_score = 40
    else:
        rsi_score = 50

    # ── Trend vs SMAs (weight 0.5) ────────────────────────────────────
    sma20 = _sma(close, 20)
    sma50 = _sma(close, 50)
    if price > sma20 > sma50:
        trend_score = 100
    elif price > sma20 and price > sma50:
        trend_score = 80
    elif price < sma20 < sma50:
        trend_score = 30
    elif price < sma20 and price < sma50:
        trend_score = 50
    else:
        trend_score = 60

    # ── Volume vs 20-day avg (weight 0.2) ─────────────────────────────
    avg_vol = float(volume.rolling(20, min_periods=1).mean().iloc[-1])
    cur_vol = float(volume.iloc[-1])
    vol_ratio = cur_vol / avg_vol if avg_vol > 0 else 1.0
    volume_score = min(100, int(vol_ratio * 50))  # 2× avg = 100

    composite = rsi_score * 0.3 + trend_score * 0.5 + volume_score * 0.2

    return {
        "price": price,
        "rsi": round(rsi, 2),
        "rsi_score": rsi_score,
        "sma20": round(sma20, 2),
        "sma50": round(sma50, 2),
        "trend_score": trend_score,
        "volume_ratio": round(vol_ratio, 2),
        "volume_score": volume_score,
        "composite": round(composite, 2),
    }
