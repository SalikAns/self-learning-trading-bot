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
from notifier import notify_trade, notify_learn, notify_mistake
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

        # Fire Telegram alert (non-blocking, don't fail the trade if it errors)
        try:
            await notify_trade(
                ticker=ticker,
                action=evaluation["decision"],
                price=evaluation["entry_price"],
                confidence=evaluation["confidence"],
                score=evaluation["total_score"],
                gates=evaluation["gates"],
            )
        except Exception:
            pass

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

        # Fire Telegram alert on mistake analysis
        if "mistake_analysis" in result:
            try:
                ma = result["mistake_analysis"]
                await notify_mistake(
                    ticker=result.get("ticker", "?"),
                    loss_pct=result.get("pnl_pct", 0),
                    red_flags=ma.get("red_flags", []),
                )
            except Exception:
                pass

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

        # Fire Telegram alert on parameter changes
        if result.get("adjustments"):
            try:
                await notify_learn(
                    adjustments=result["adjustments"],
                    win_rate=result.get("win_rate", 0),
                    total_trades=result.get("total_trades", 0),
                )
            except Exception:
                pass

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
from fastapi.responses import HTMLResponse

@app.get("/", response_class=HTMLResponse)
async def trading_dashboard():
    """Trading dashboard - works in any browser."""
    return """
    <!DOCTYPE html>
    <html>
    <head>
        <title>AI Trading Bot</title>
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <style>
            * { box-sizing: border-box; margin: 0; padding: 0; }
            body {
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                background: #0f1419;
                color: #fff;
                min-height: 100vh;
            }
            .header {
                background: linear-gradient(90deg, #00d4aa 0%, #00a8e8 100%);
                padding: 30px;
                text-align: center;
            }
            .header h1 { font-size: 32px; margin-bottom: 10px; }
            .header p { opacity: 0.9; }
            .stats-grid {
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
                gap: 20px;
                padding: 30px;
                max-width: 1200px;
                margin: 0 auto;
            }
            .stat-card {
                background: #1a2332;
                padding: 25px;
                border-radius: 15px;
                border: 1px solid #2a3441;
            }
            .stat-card h3 {
                color: #8899a6;
                font-size: 14px;
                text-transform: uppercase;
                margin-bottom: 10px;
            }
            .stat-value {
                font-size: 28px;
                font-weight: bold;
                color: #fff;
            }
            .positive { color: #00d4aa; }
            .negative { color: #ff6b6b; }
            .actions {
                padding: 30px;
                max-width: 1200px;
                margin: 0 auto;
                display: flex;
                gap: 15px;
                flex-wrap: wrap;
            }
            .btn {
                padding: 15px 30px;
                border: none;
                border-radius: 10px;
                cursor: pointer;
                font-size: 16px;
                font-weight: bold;
                transition: all 0.3s;
            }
            .btn-primary {
                background: #00d4aa;
                color: #0f1419;
            }
            .btn-secondary {
                background: #2a3441;
                color: #fff;
                border: 1px solid #3a4451;
            }
            .btn:hover {
                transform: translateY(-2px);
                box-shadow: 0 10px 20px rgba(0,0,0,0.3);
            }
            .research-section {
                padding: 30px;
                max-width: 1200px;
                margin: 0 auto;
            }
            .research-input {
                display: flex;
                gap: 10px;
                margin-bottom: 20px;
            }
            input[type="text"] {
                flex: 1;
                padding: 15px;
                background: #1a2332;
                border: 1px solid #2a3441;
                color: #fff;
                border-radius: 10px;
                font-size: 16px;
            }
            .results {
                background: #1a2332;
                padding: 20px;
                border-radius: 15px;
                min-height: 200px;
            }
            .trade-log {
                padding: 30px;
                max-width: 1200px;
                margin: 0 auto;
            }
            table {
                width: 100%;
                border-collapse: collapse;
                background: #1a2332;
                border-radius: 15px;
                overflow: hidden;
            }
            th, td {
                padding: 15px;
                text-align: left;
                border-bottom: 1px solid #2a3441;
            }
            th {
                background: #2a3441;
                color: #8899a6;
                font-size: 12px;
                text-transform: uppercase;
            }
            .badge {
                padding: 5px 12px;
                border-radius: 20px;
                font-size: 12px;
                font-weight: bold;
            }
            .badge-buy { background: #00d4aa20; color: #00d4aa; }
            .badge-sell { background: #ff6b6b20; color: #ff6b6b; }
            .badge-hold { background: #ffd93d20; color: #ffd93d; }
        </style>
    </head>
    <body>
        <div class="header">
            <h1>🤖 AI Trading Bot</h1>
            <p>Self-learning algorithmic trading | Paper Trading Mode</p>
        </div>
        
        <div class="stats-grid">
            <div class="stat-card">
                <h3>Portfolio Value</h3>
                <div class="stat-value" id="portfolio">$100,000</div>
            </div>
            <div class="stat-card">
                <h3>Today's P&L</h3>
                <div class="stat-value positive" id="pnl">+$0</div>
            </div>
            <div class="stat-card">
                <h3>Win Rate</h3>
                <div class="stat-value" id="winrate">0%</div>
            </div>
            <div class="stat-card">
                <h3>Open Positions</h3>
                <div class="stat-value" id="positions">0</div>
            </div>
        </div>
        
        <div class="actions">
            <button class="btn btn-primary" onclick="scanMarket()">🔍 Scan Market</button>
            <button class="btn btn-secondary" onclick="forceLearn()">🧠 Force Learning</button>
            <button class="btn btn-secondary" onclick="viewJournal()">📓 Mistake Journal</button>
        </div>
        
        <div class="research-section">
            <h2 style="margin-bottom: 15px;">Deep Research</h2>
            <div class="research-input">
                <input type="text" id="tickerInput" placeholder="Enter stock ticker (e.g., AAPL, TSLA, NVDA)">
                <button class="btn btn-primary" onclick="researchStock()">Research</button>
            </div>
            <div class="results" id="researchResults">
                <p style="color: #8899a6;">Enter a ticker above to see comprehensive analysis...</p>
            </div>
        </div>
        
        <div class="trade-log">
            <h2 style="margin-bottom: 15px;">Recent Trades</h2>
            <table id="tradesTable">
                <thead>
                    <tr>
                        <th>Time</th>
                        <th>Ticker</th>
                        <th>Action</th>
                        <th>Price</th>
                        <th>P&L</th>
                        <th>Reason</th>
                    </tr>
                </thead>
                <tbody id="tradesBody">
                    <tr>
                        <td colspan="6" style="text-align: center; color: #8899a6;">No trades yet. Click "Scan Market" to start.</td>
                    </tr>
                </tbody>
            </table>
        </div>

        <script>
            async function scanMarket() {
                const btn = document.querySelector('.btn-primary');
                btn.textContent = 'Scanning...';
                btn.disabled = true;
                
                try {
                    const response = await fetch('/scan');
                    const data = await response.json();
                    
                    updateTrades(data.signals);
                    btn.textContent = '🔍 Scan Market';
                    btn.disabled = false;
                    
                } catch (error) {
                    alert('Error scanning market');
                    btn.textContent = '🔍 Scan Market';
                    btn.disabled = false;
                }
            }
            
            async function researchStock() {
                const ticker = document.getElementById('tickerInput').value.toUpperCase();
                if (!ticker) return;
                
                const results = document.getElementById('researchResults');
                results.innerHTML = '<p style="color: #8899a6;">Researching...</p>';
                
                try {
                    const response = await fetch(`/research/${ticker}`);
                    const data = await response.json();
                    
                    results.innerHTML = `
                        <h3 style="color: #00d4aa; margin-bottom: 15px;">
                            ${data.ticker} - Score: ${data.total_score.toFixed(1)}/100
                        </h3>
                        <div style="display: grid; grid-template-columns: repeat(2, 1fr); gap: 15px;">
                            <div>📊 Technical: ${data.technical.toFixed(1)}</div>
                            <div>📈 Fundamental: ${data.fundamental.toFixed(1)}</div>
                            <div>💭 Sentiment: ${data.sentiment.toFixed(1)}</div>
                            <div>⚠️ Risk: ${data.risk.toFixed(1)}</div>
                        </div>
                        <div style="margin-top: 15px; padding-top: 15px; border-top: 1px solid #2a3441;">
                            <div>Price: $${data.price.toFixed(2)}</div>
                            <div>Volatility: ${data.volatility.toFixed(1)}%</div>
                            <div>Volume: ${data.volume_trend}</div>
                        </div>
                    `;
                    
                } catch (error) {
                    results.innerHTML = '<p style="color: #ff6b6b;">Error researching stock</p>';
                }
            }
            
            async function forceLearn() {
                try {
                    const response = await fetch('/learn');
                    const data = await response.json();
                    alert(`Strategy updated! Win rate: ${(data.win_rate * 100).toFixed(1)}%`);
                } catch (error) {
                    alert('Error running learning algorithm');
                }
            }
            
            async function viewJournal() {
                try {
                    const response = await fetch('/journal');
                    const data = await response.json();
                    alert(`Found ${data.mistakes.length} mistakes logged. Check console for details.`);
                    console.log(data.mistakes);
                } catch (error) {
                    alert('Error loading mistake journal');
                }
            }
            
            function updateTrades(signals) {
                const tbody = document.getElementById('tradesBody');
                if (signals.length === 0) {
                    tbody.innerHTML = '<tr><td colspan="6" style="text-align: center; color: #8899a6;">No signals found this scan.</td></tr>';
                    return;
                }
                
                tbody.innerHTML = signals.map(s => `
                    <tr>
                        <td>${new Date().toLocaleTimeString()}</td>
                        <td><b>${s.ticker}</b></td>
                        <td><span class="badge badge-${s.action.toLowerCase()}">${s.action}</span></td>
                        <td>$${s.price?.toFixed(2) || '-'}</td>
                        <td class="${(s.pnl || 0) >= 0 ? 'positive' : 'negative'}">${s.pnl ? '$' + s.pnl.toFixed(2) : '-'}</td>
                        <td>${s.reason || '-'}</td>
                    </tr>
                `).join('');
            }
            
            // Auto-refresh stats every 30 seconds
            setInterval(async () => {
                try {
                    const response = await fetch('/stats');
                    const data = await response.json();
                    document.getElementById('portfolio').textContent = '$' + data.portfolio_value.toLocaleString();
                    document.getElementById('winrate').textContent = (data.win_rate * 100).toFixed(1) + '%';
                    document.getElementById('positions').textContent = data.open_positions;
                } catch (e) {}
            }, 30000);
        </script>
    </body>
    </html>
    """

@app.get("/stats")
async def get_stats():
    """Get current trading stats for dashboard."""
    summary = trader.get_portfolio_summary()
    trades = await get_all_trades()
    
    wins = [t for t in trades if t.get('pnl_pct', 0) > 0]
    losses = [t for t in trades if t.get('pnl_pct', 0) <= 0]
    
    win_rate = len(wins) / len(trades) if trades else 0
    
    return {
        "portfolio_value": summary['portfolio_value'],
        "total_return": summary['total_return'],
        "win_rate": win_rate,
        "open_positions": len([t for t in trades if t['status'] == 'OPEN']),
        "total_trades": len(trades)
    }
    from discord_bot import run_discord_bot, send_trade_alert
import threading

# Modify your trade execution to call:
# await send_trade_alert(ticker, "BUY", price, confidence)

# At end of file:
if __name__ == "__main__":
    discord_thread = threading.Thread(target=run_discord_bot, daemon=True)
    discord_thread.start()
    
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=settings.PORT)
