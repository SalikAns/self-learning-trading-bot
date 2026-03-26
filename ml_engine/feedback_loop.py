"""
Core learning engine: TradeMemory + AdaptiveStrategy.
Tracks trades, analyses mistakes, and dynamically adjusts strategy parameters.
"""
import json
from datetime import datetime, timezone
import config
import database as db
from utils.logger import get_logger

log = get_logger("feedback_loop")


# ═══════════════════════════════════════════════════════════════════════
# TradeMemory — persistence and mistake analysis
# ═══════════════════════════════════════════════════════════════════════
class TradeMemory:
    """Stores every trade decision and analyses mistakes after exit."""

    @staticmethod
    async def log_trade_decision(
        ticker: str,
        features: dict,
        decision: str,
        confidence: float,
        entry_price: float | None = None,
    ) -> int:
        """Save a trade decision to the database. Returns the new row id."""
        now = datetime.now(timezone.utc).isoformat()
        trade_id = await db.execute_returning(
            """INSERT INTO trade_decisions
               (ticker, entry_time, features, decision, confidence, status, entry_price)
               VALUES (?, ?, ?, ?, ?, 'OPEN', ?)""",
            (ticker, now, json.dumps(features), decision, confidence, entry_price),
        )
        log.info(f"Logged {decision} for {ticker} (id={trade_id}, confidence={confidence:.2f})")
        return trade_id

    @staticmethod
    async def update_trade_outcome(
        trade_id: int,
        exit_price: float,
        exit_reason: str = "manual",
    ) -> dict:
        """
        Calculate PnL% and close the trade. Triggers mistake analysis if loss > -5%.
        """
        row = await db.fetch_one(
            "SELECT * FROM trade_decisions WHERE id = ?", (trade_id,)
        )
        if not row:
            return {"error": f"Trade {trade_id} not found"}

        entry_price = row["entry_price"]
        if entry_price is None or entry_price == 0:
            return {"error": "No entry price recorded"}

        pnl_pct = (exit_price - entry_price) / entry_price
        entry_time = datetime.fromisoformat(row["entry_time"])
        holding_days = (datetime.now(timezone.utc) - entry_time).days

        await db.execute(
            """UPDATE trade_decisions
               SET status='CLOSED', exit_price=?, pnl_pct=?, exit_reason=?, holding_days=?
               WHERE id=?""",
            (exit_price, round(pnl_pct, 6), exit_reason, holding_days, trade_id),
        )

        result = {
            "trade_id": trade_id,
            "ticker": row["ticker"],
            "pnl_pct": round(pnl_pct * 100, 2),
            "exit_reason": exit_reason,
            "holding_days": holding_days,
        }

        # Trigger mistake analysis on significant losses
        if pnl_pct <= config.MISTAKE_LOSS_THRESHOLD:
            mistake = await TradeMemory._analyze_mistake(trade_id, row, pnl_pct)
            result["mistake_analysis"] = mistake

        log.info(f"Closed trade {trade_id}: PnL {result['pnl_pct']:+.2f}%")
        return result

    @staticmethod
    async def _analyze_mistake(trade_id: int, trade_row: dict, pnl_pct: float) -> dict:
        """Inspect entry conditions and write red flags to mistake_journal."""
        features = json.loads(trade_row["features"]) if trade_row["features"] else {}
        ticker = trade_row["ticker"]
        red_flags = []

        tech = features.get("technical", {})
        fund = features.get("fundamental", {})
        risk = features.get("risk", {})

        if tech.get("rsi_score", 100) < 40:
            red_flags.append("low_rsi_score")
        if tech.get("trend_score", 100) < 50:
            red_flags.append("weak_trend")
        if fund.get("de_score", 100) < 50:
            red_flags.append("high_debt")
        if risk.get("vol_score", 100) < 50:
            red_flags.append("high_volatility")
        if risk.get("dd_score", 100) < 50:
            red_flags.append("deep_drawdown")
        if features.get("composite_score", 100) < 60:
            red_flags.append("low_composite")

        if not red_flags:
            red_flags.append("unidentified_pattern")

        lesson = f"{ticker}: loss {pnl_pct*100:.1f}% with flags {red_flags}"

        await db.execute(
            """INSERT INTO mistake_journal (trade_id, ticker, loss_pct, red_flags, lesson_learned)
               VALUES (?, ?, ?, ?, ?)""",
            (trade_id, ticker, round(pnl_pct, 4), json.dumps(red_flags), lesson),
        )

        log.warning(f"Mistake logged for {ticker}: {red_flags}")
        return {"red_flags": red_flags, "lesson": lesson}

    @staticmethod
    async def get_recent_trades(limit: int = 50) -> list[dict]:
        return await db.fetch_all(
            "SELECT * FROM trade_decisions ORDER BY created_at DESC LIMIT ?", (limit,)
        )

    @staticmethod
    async def get_closed_trades() -> list[dict]:
        return await db.fetch_all(
            "SELECT * FROM trade_decisions WHERE status='CLOSED' ORDER BY exit_price IS NOT NULL, created_at DESC"
        )

    @staticmethod
    async def get_mistakes(limit: int = 10) -> list[dict]:
        return await db.fetch_all(
            "SELECT * FROM mistake_journal ORDER BY date DESC LIMIT ?", (limit,)
        )


# ═══════════════════════════════════════════════════════════════════════
# AdaptiveStrategy — dynamic parameter adjustment
# ═══════════════════════════════════════════════════════════════════════
class AdaptiveStrategy:
    """Holds current trading parameters and applies learnings in-place."""

    def __init__(self):
        self.params = {
            "min_total_score": config.MIN_TOTAL_SCORE,
            "min_technical_score": config.MIN_TECHNICAL_SCORE,
            "max_volatility": config.MAX_VOLATILITY,
            "weights": config.WEIGHTS.copy(),
        }
        self.history: list[dict] = []

    def get_params(self) -> dict:
        return self.params.copy()

    def get_weights(self) -> dict:
        return self.params["weights"].copy()

    async def learn(self) -> dict:
        """
        Analyse all closed trades, compare winners vs losers, and adjust parameters.
        Requires ≥10 closed trades.
        """
        closed = await TradeMemory.get_closed_trades()
        if len(closed) < config.MIN_TRADES_FOR_LEARNING:
            return {
                "status": "insufficient_data",
                "closed_trades": len(closed),
                "required": config.MIN_TRADES_FOR_LEARNING,
            }

        winners = [t for t in closed if (t["pnl_pct"] or 0) > 0]
        losers = [t for t in closed if (t["pnl_pct"] or 0) <= 0]
        total = len(closed)
        win_rate = len(winners) / total if total > 0 else 0

        adjustments = {}

        # ── Compare avg scores between winners and losers ─────────────
        def avg_field(trades: list, path: str) -> float:
            vals = []
            for t in trades:
                feats = json.loads(t["features"]) if t.get("features") else {}
                parts = path.split(".")
                v = feats
                for p in parts:
                    v = v.get(p, {}) if isinstance(v, dict) else {}
                if isinstance(v, (int, float)):
                    vals.append(v)
            return sum(vals) / len(vals) if vals else 0

        winner_tech = avg_field(winners, "technical.composite")
        loser_tech = avg_field(losers, "technical.composite")

        winner_fund = avg_field(winners, "fundamental.composite")
        loser_fund = avg_field(losers, "fundamental.composite")

        winner_sent = avg_field(winners, "sentiment.score")
        loser_sent = avg_field(losers, "sentiment.score")

        winner_vol = avg_field(winners, "risk.volatility")
        loser_vol = avg_field(losers, "risk.volatility")

        # ── Adjust min_technical_score ────────────────────────────────
        tech_gap = winner_tech - loser_tech
        if tech_gap > 10:
            new_min_tech = max(30, int(winner_tech - 5))
            if new_min_tech != self.params["min_technical_score"]:
                adjustments["min_technical_score"] = {
                    "old": self.params["min_technical_score"],
                    "new": new_min_tech,
                }
                self.params["min_technical_score"] = new_min_tech

        # ── Adjust max_volatility ─────────────────────────────────────
        if winner_vol > 0 and winner_vol < 40 and self.params["max_volatility"] > 0.45:
            new_max_vol = 0.45
            adjustments["max_volatility"] = {
                "old": self.params["max_volatility"],
                "new": new_max_vol,
            }
            self.params["max_volatility"] = new_max_vol

        # ── Adjust sentiment weight ───────────────────────────────────
        sent_gap = abs(winner_sent - loser_sent)
        if sent_gap < 5 and self.params["weights"]["sentiment"] > 0.10:
            old_w = self.params["weights"]["sentiment"]
            new_w = round(old_w - 0.10, 2)
            # Redistribute to fundamental
            self.params["weights"]["sentiment"] = max(0.05, new_w)
            self.params["weights"]["fundamental"] = round(
                1.0 - self.params["weights"]["technical"]
                - max(0.05, new_w)
                - self.params["weights"]["risk"], 2
            )
            adjustments["weights.sentiment"] = {
                "old": old_w,
                "new": self.params["weights"]["sentiment"],
            }

        # ── Adjust fundamental weight ─────────────────────────────────
        fund_gap = winner_fund - loser_fund
        if fund_gap > 5 and self.params["weights"]["fundamental"] < 0.40:
            old_w = self.params["weights"]["fundamental"]
            new_w = 0.40
            diff = new_w - old_w
            # Take from risk weight
            self.params["weights"]["fundamental"] = new_w
            self.params["weights"]["risk"] = round(
                max(0.05, self.params["weights"]["risk"] - diff), 2
            )
            adjustments["weights.fundamental"] = {
                "old": old_w,
                "new": new_w,
            }

        # ── Adjust min_total_score based on win rate ──────────────────
        if win_rate < 0.35 and self.params["min_total_score"] < 80:
            new_min = self.params["min_total_score"] + 5
            adjustments["min_total_score"] = {
                "old": self.params["min_total_score"],
                "new": new_min,
            }
            self.params["min_total_score"] = new_min

        # ── Save snapshot ─────────────────────────────────────────────
        snapshot = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "win_rate": round(win_rate, 4),
            "total_trades": total,
            "adjustments": adjustments,
            "params": self.params.copy(),
        }
        self.history.append(snapshot)

        await db.execute(
            """INSERT INTO strategy_evolution (win_rate, total_trades, adjustments, params_snapshot)
               VALUES (?, ?, ?, ?)""",
            (
                round(win_rate, 4),
                total,
                json.dumps(adjustments),
                json.dumps(self.params),
            ),
        )

        log.info(f"Learn complete: win_rate={win_rate:.2%}, adjustments={list(adjustments.keys())}")
        return {
            "status": "learned",
            "win_rate": round(win_rate, 4),
            "total_trades": total,
            "winners": len(winners),
            "losers": len(losers),
            "adjustments": adjustments,
            "new_params": self.params,
        }
