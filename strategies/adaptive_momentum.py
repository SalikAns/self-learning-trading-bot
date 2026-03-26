"""
Self-optimizing momentum strategy.
Uses ComprehensiveResearch + AdaptiveStrategy to make BUY/PASS decisions.
"""
import config
from research.comprehensive import ComprehensiveResearch
from ml_engine.feedback_loop import AdaptiveStrategy
from utils.logger import get_logger

log = get_logger("adaptive_momentum")


class AdaptiveMomentumStrategy:
    """
    Combines research scoring with adaptive thresholds.
    Decision logic:
        1. Run ComprehensiveResearch for the ticker
        2. Apply adaptive thresholds from AdaptiveStrategy
        3. If all gates pass → BUY with confidence score
        4. Otherwise → PASS
    """

    def __init__(self, adaptive: AdaptiveStrategy):
        self.adaptive = adaptive
        self.researcher = None  # lazy init to pick up latest weights

    def _get_researcher(self) -> ComprehensiveResearch:
        if self.researcher is None:
            self.researcher = ComprehensiveResearch(weights=self.adaptive.get_weights())
        return self.researcher

    def evaluate(self, ticker: str) -> dict:
        """
        Run full evaluation pipeline.
        Returns dict with decision, confidence, scores, and suggested risk params.
        """
        params = self.adaptive.get_params()
        researcher = self._get_researcher()
        research = researcher.research(ticker)

        tech_score = research["technical"]["composite"]
        total_score = research["composite_score"]
        volatility = research["risk"].get("volatility", 0)

        # ── Gate checks ───────────────────────────────────────────────
        gates = {
            "total_score": total_score >= params["min_total_score"],
            "technical_score": tech_score >= params["min_technical_score"],
            "volatility": volatility <= params["max_volatility"] * 100,
        }

        all_pass = all(gates.values())

        # ── Confidence ────────────────────────────────────────────────
        if all_pass:
            # Higher score = higher confidence, capped at 0.95
            confidence = min(0.95, 0.5 + (total_score - params["min_total_score"]) / 100)
        else:
            confidence = 0.0

        decision = "BUY" if all_pass else "PASS"

        # ── Risk management ───────────────────────────────────────────
        price = research.get("price")
        stop_loss = price * (1 + config.STOP_LOSS_PCT) if price else None
        take_profit = price * (1 + config.TAKE_PROFIT_PCT) if price else None

        result = {
            "ticker": ticker,
            "decision": decision,
            "confidence": round(confidence, 4),
            "total_score": total_score,
            "technical_score": tech_score,
            "gates": gates,
            "entry_price": price,
            "stop_loss": round(stop_loss, 2) if stop_loss else None,
            "take_profit": round(take_profit, 2) if take_profit else None,
            "research": research,
            "params_used": params,
        }

        log.info(f"{ticker}: {decision} (score={total_score}, confidence={confidence:.2f}, gates={gates})")
        return result
