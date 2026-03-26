"""
Financial statements: P/E, revenue growth, margins, debt-to-equity.
"""
import yfinance as yf
from utils.logger import get_logger

log = get_logger("fundamental")


def _safe_ratio(numerator, denominator):
    """Return ratio or None if denominator is zero/None."""
    if numerator is None or denominator is None or denominator == 0:
        return None
    return numerator / denominator


def get_fundamental_score(ticker: str) -> dict:
    """Return dict with sub-scores (0-100) and a weighted composite (0-100)."""
    stock = yf.Ticker(ticker)
    info = stock.info or {}

    # ── P/E Ratio ─────────────────────────────────────────────────────
    pe = info.get("trailingPE")
    if pe is not None:
        if 10 <= pe <= 25:
            pe_score = 80
        elif 5 <= pe < 10 or 25 < pe <= 40:
            pe_score = 60
        else:
            pe_score = 30
    else:
        pe_score = 50  # neutral when unavailable

    # ── Revenue Growth (YoY) ──────────────────────────────────────────
    revenue_growth = info.get("revenueGrowth")  # fraction, e.g. 0.15 = 15%
    if revenue_growth is not None:
        growth_pct = revenue_growth * 100
        if growth_pct > 20:
            growth_score = 100
        elif growth_pct > 10:
            growth_score = 80
        elif growth_pct > 0:
            growth_score = 60
        else:
            growth_score = 40
    else:
        growth_score = 50

    # ── Profit Margin ─────────────────────────────────────────────────
    profit_margin = info.get("profitMargins")
    if profit_margin is not None:
        margin_pct = profit_margin * 100
        if margin_pct > 20:
            margin_score = 100
        elif margin_pct > 10:
            margin_score = 80
        elif margin_pct > 0:
            margin_score = 60
        else:
            margin_score = 20
    else:
        margin_score = 50

    # ── Debt / Equity ─────────────────────────────────────────────────
    de_ratio = info.get("debtToEquity")
    if de_ratio is not None:
        de = de_ratio  # already a ratio (e.g. 45 = 0.45×)
        if de < 50:
            de_score = 100
        elif de < 100:
            de_score = 70
        else:
            de_score = 40
    else:
        de_score = 50

    composite = (pe_score + growth_score + margin_score + de_score) / 4

    return {
        "pe_ratio": pe,
        "pe_score": pe_score,
        "revenue_growth_pct": (revenue_growth or 0) * 100,
        "growth_score": growth_score,
        "profit_margin_pct": (profit_margin or 0) * 100,
        "margin_score": margin_score,
        "debt_equity": de_ratio,
        "de_score": de_score,
        "composite": round(composite, 2),
    }
