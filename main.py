"""
FastAPI server + background task scheduler.
Entry point for the self-learning trading bot.
"""
import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse

import config
import database as db
from research.comprehensive import ComprehensiveResearch
from ml_engine.feedback_loop import TradeMemory, AdaptiveStrategy
from strategies.adaptive_momentum import AdaptiveMomentumStrategy
from utils.logger import get_logger

log = get_logger("main")

# ── Singletons ────────────────────────────────────────────────────────
adaptive_strategy = AdaptiveStrategy()
momentum_strategy = AdaptiveMomentumStrategy(adaptive_strategy)
researcher = ComprehensiveResearch()


# ── Background scheduler ──────────────────────────────────────────────
async def _background_scheduler():
    """Periodically run scans and learning cycles."""
    while True:
        try:
            log.info("Background: running learning cycle")
            await adaptive_strategy.learn()
        except Exception as e:
            log.error(f"Background learn error: {e}")

        await asyncio.sleep(config.LEARN_INTERVAL_HOURS * 3600)


_scheduler_task: asyncio.Task | None = None


# ── App lifecycle ─────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    global _scheduler_task
    log.info("Starting trading bot...")
    await db.init_db()
    _scheduler_task = asyncio.create_task(_background_scheduler())
    log.info("Background scheduler started.")
    yield
    if _scheduler_task:
        _scheduler_task.cancel()
    log.info("Trading bot shut down.")


app = FastAPI(
    title="Self-Learning Trading Bot",
    description="Multi-factor research, adaptive strategy, and self-learning feedback loop.",
    version="1.0.0",
    lifespan=lifespan,
)


# ═══════════════════════════════════════════════════════════════════════
# API Endpoints
# ═══════════════════════════════════════════════════════════════════════

@app.get("/research/{ticker}")
async def research_endpoint(ticker: str):
    """Returns full 4-dimension research report."""
    ticker = ticker.upper()
    try:
        result = researcher.research(ticker)
        return JSONResponse(result)
    except Exception as e:
        log.error(f"Research error for {ticker}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/paper-trade")
async def paper_trade_endpoint(ticker: str = "AAPL"):
    """
    Runs research, applies learnings, makes adaptive BUY/PASS decision.
    Returns entry price, stop-loss (-3%), and take-profit (+10%).
    """
    ticker = ticker.upper()
    try:
        evaluation = momentum_strategy.evaluate(ticker)

        # Log the decision
        trade_id = await TradeMemory.log_trade_decision(
            ticker=ticker,
            features=evaluation["research"],
            decision=evaluation["decision"],
            confidence=evaluation["confidence"],
            entry_price=evaluation["entry_price"],
        )

        evaluation["trade_id"] = trade_id
        return JSONResponse(evaluation)
    except Exception as e:
        log.error(f"Paper trade error for {ticker}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/trade/{trade_id}/close")
async def close_trade_endpoint(trade_id: int, exit_price: float):
    """Close a trade with the given exit price. Triggers mistake analysis if loss > -5%."""
    try:
        result = await TradeMemory.update_trade_outcome(trade_id, exit_price)
        if "error" in result:
            raise HTTPException(status_code=404, detail=result["error"])
        return JSONResponse(result)
    except HTTPException:
        raise
    except Exception as e:
        log.error(f"Close trade error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/learn")
async def learn_endpoint():
    """Forces strategy to ingest all closed trades and update parameters."""
    try:
        result = await adaptive_strategy.learn()
        # Invalidate researcher so it picks up new weights
        momentum_strategy.researcher = None
        return JSONResponse(result)
    except Exception as e:
        log.error(f"Learn error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/journal")
async def journal_endpoint(limit: int = 10):
    """Returns the most recent mistake journal entries with red flags."""
    try:
        mistakes = await TradeMemory.get_mistakes(limit)
        for m in mistakes:
            import json
            if isinstance(m.get("red_flags"), str):
                m["red_flags"] = json.loads(m["red_flags"])
        return JSONResponse({"mistakes": mistakes})
    except Exception as e:
        log.error(f"Journal error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/history")
async def history_endpoint(limit: int = 50):
    """Returns full trade_decisions log with outcomes."""
    try:
        trades = await TradeMemory.get_recent_trades(limit)
        import json
        for t in trades:
            if isinstance(t.get("features"), str):
                t["features"] = json.loads(t["features"])
        return JSONResponse({"trades": trades})
    except Exception as e:
        log.error(f"History error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/evolution")
async def evolution_endpoint():
    """Returns strategy_evolution timeline showing how parameters changed."""
    try:
        rows = await db.fetch_all(
            "SELECT * FROM strategy_evolution ORDER BY timestamp DESC"
        )
        import json
        for r in rows:
            if isinstance(r.get("adjustments"), str):
                r["adjustments"] = json.loads(r["adjustments"])
            if isinstance(r.get("params_snapshot"), str):
                r["params_snapshot"] = json.loads(r["params_snapshot"])
        return JSONResponse({"evolution": rows})
    except Exception as e:
        log.error(f"Evolution error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/strategy/params")
async def strategy_params_endpoint():
    """Returns current adaptive strategy parameters."""
    return JSONResponse(adaptive_strategy.get_params())


@app.get("/health")
async def health_check():
    return {"status": "ok", "service": "self-learning-trading-bot"}


# ── Run ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
