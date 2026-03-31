# main.py - Complete Working Version
import sys
import os
import asyncio
import threading
import logging
from contextlib import asynccontextmanager
from datetime import datetime
from typing import List, Dict, Optional

# Fix audioop issue for Discord
try:
    import audioop
except ImportError:
    import types
    audioop = types.ModuleType('audioop')
    audioop.ratecv = lambda *args, **kwargs: (b'', 0)
    audioop.lin2lin = lambda *args, **kwargs: b''
    sys.modules['audioop'] = audioop

# FastAPI imports
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse, HTMLResponse

# Discord imports
import discord
from discord.ext import commands

# Project imports
import config
import database as db
from research.comprehensive import ComprehensiveResearch
from ml_engine.feedback_loop import TradeMemory, AdaptiveStrategy
from strategies.adaptive_momentum import AdaptiveMomentumStrategy
from notifier import notify_trade, notify_learn, notify_mistake
from autonomous_trading import AutonomousTradingEngine
from utils.logger import get_logger

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ── Initialize Singletons ─────────────────────────────────────────────
adaptive_strategy = AdaptiveStrategy()
momentum_strategy = AdaptiveMomentumStrategy(adaptive_strategy)
researcher = ComprehensiveResearch()
trade_memory = TradeMemory()

# ── FastAPI App ───────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifecycle management"""
    logger.info("Starting trading bot...")
    
    # Initialize database
    await db.init_db()
    logger.info("Database initialized.")
    
    # Start background scheduler
    scheduler_task = asyncio.create_task(_background_scheduler())
    
    # Initialize autonomous trading engine
    global trading_engine
    trading_engine = AutonomousTradingEngine(db, adaptive_strategy)
    logger.info("Autonomous trading engine initialized.")
    
    # Start autonomous trading loop
    auto_trade_task = asyncio.create_task(_autonomous_trading_loop())
    
    yield
    
    # Cleanup
    scheduler_task.cancel()
    auto_trade_task.cancel()
    logger.info("Trading bot shut down.")


app = FastAPI(
    title="Self-Learning Trading Bot",
    description="Multi-factor research, adaptive strategy, and self-learning feedback loop.",
    version="2.0.0",
    lifespan=lifespan,
)


# ── Background Tasks ──────────────────────────────────────────────────
async def _background_scheduler():
    """Periodically run learning cycles."""
    while True:
        try:
            logger.info("Background: running learning cycle")
            await adaptive_strategy.learn()
        except Exception as e:
            logger.error(f"Background learn error: {e}")
        await asyncio.sleep(config.LEARN_INTERVAL_HOURS * 3600)


async def _autonomous_trading_loop():
    """Runs autonomous trading every 30 minutes"""
    while True:
        try:
            if trading_engine and trading_engine.active:
                logger.info("Running autonomous trading cycle...")
                await trading_engine.run_trading_cycle()
            await asyncio.sleep(1800)  # 30 minutes
        except Exception as e:
            logger.error(f"Autonomous trading error: {e}")
            await asyncio.sleep(300)  # Wait 5 min on error


# ── Discord Bot Setup ─────────────────────────────────────────────────
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='$', intents=intents)


@bot.event
async def on_ready():
    logger.info(f'✅ Discord bot online: {bot.user.name}')
    
    # Sync slash commands
    try:
        synced = await bot.tree.sync()
        logger.info(f"Synced {len(synced)} commands")
    except Exception as e:
        logger.error(f"Command sync error: {e}")


# Discord Commands
@bot.command(name='ping')
async def ping(ctx):
    """Check if bot is alive"""
    await ctx.send(f'Pong! Latency: {round(bot.latency * 1000)}ms')


@bot.command(name='research')
async def research_cmd(ctx, ticker: str):
    """Research a stock - $research AAPL"""
    ticker = ticker.upper()
    await ctx.send(f"🔍 Researching {ticker}...")
    try:
        result = researcher.research(ticker)
        embed = discord.Embed(title=f"📊 {ticker} Analysis", color=0x00ff00)
        embed.add_field(name="Technical Score", value=f"{result['technical']:.1f}/100")
        embed.add_field(name="Fundamental Score", value=f"{result['fundamental']:.1f}/100")
        embed.add_field(name="Sentiment Score", value=f"{result['sentiment']:.1f}/100")
        embed.add_field(name="Risk Score", value=f"{result['risk']:.1f}/100")
        embed.add_field(name="Total Score", value=f"{result['total_score']:.1f}/100")
        embed.add_field(name="Current Price", value=f"${result['price']:.2f}")
        await ctx.send(embed=embed)
    except Exception as e:
        await ctx.send(f"❌ Error researching {ticker}: {e}")


@bot.command(name='buy')
async def buy_cmd(ctx, ticker: str, shares: float = None):
    """Paper trade buy - $buy AAPL 10"""
    ticker = ticker.upper()
    await ctx.send(f"📈 Evaluating {ticker} for purchase...")
    try:
        evaluation = momentum_strategy.evaluate(ticker)
        if evaluation['decision'] == 'BUY':
            if shares:
                price = evaluation['entry_price']
                total = price * shares
                await ctx.send(f"✅ BUY {shares} shares of {ticker} @ ${price:.2f} = ${total:.2f}")
            else:
                await ctx.send(f"✅ BUY signal for {ticker} at ${evaluation['entry_price']:.2f}")
        else:
            await ctx.send(f"⏸️ HOLD signal for {ticker} (score: {evaluation['total_score']:.1f})")
    except Exception as e:
        await ctx.send(f"❌ Error: {e}")


@bot.command(name='portfolio')
async def portfolio_cmd(ctx):
    """View paper trading portfolio"""
    await ctx.send("📊 Portfolio feature coming soon!")
    # Add portfolio logic here


@bot.command(name='learn')
async def learn_cmd(ctx):
    """Force strategy learning"""
    await ctx.send("🧠 Running learning cycle...")
    try:
        result = await adaptive_strategy.learn()
        await ctx.send(f"✅ Learning complete! Win rate: {(result.get('win_rate', 0) * 100):.1f}%")
    except Exception as e:
        await ctx.send(f"❌ Learning error: {e}")


@bot.command(name='mistakes')
async def mistakes_cmd(ctx):
    """View recent mistakes"""
    try:
        mistakes = await trade_memory.get_mistakes(5)
        if mistakes:
            embed = discord.Embed(title="📓 Mistake Journal", color=0xff6b6b)
            for m in mistakes[:5]:
                embed.add_field(
                    name=f"{m['ticker']} - Loss: {m.get('loss_pct', 0):.1f}%",
                    value=f"Flags: {', '.join(m.get('red_flags', []))}",
                    inline=False
                )
            await ctx.send(embed=embed)
        else:
            await ctx.send("📓 No mistakes logged yet!")
    except Exception as e:
        await ctx.send(f"❌ Error: {e}")


@bot.command(name='autostart')
async def autostart_cmd(ctx):
    """Start autonomous trading"""
    global trading_engine
    if trading_engine:
        trading_engine.active = True
        await ctx.send("🤖 Autonomous trading ACTIVATED! Bot will trade automatically.")
    else:
        await ctx.send("❌ Trading engine not available")


@bot.command(name='autostop')
async def autostop_cmd(ctx):
    """Stop autonomous trading"""
    global trading_engine
    if trading_engine:
        trading_engine.active = False
        await ctx.send("🛑 Autonomous trading DEACTIVATED.")
    else:
        await ctx.send("❌ Trading engine not available")


@bot.command(name='stats')
async def stats_cmd(ctx):
    """Show trading statistics"""
    try:
        stats = await trading_engine.get_stats() if trading_engine else {}
        embed = discord.Embed(title="📈 Trading Statistics", color=0x00d4aa)
        embed.add_field(name="Active", value="✅ Yes" if stats.get('active') else "❌ No")
        embed.add_field(name="Risk per Trade", value=f"{stats.get('risk_per_trade', 0)*100:.1f}%")
        embed.add_field(name="Min Score", value=stats.get('min_score', 50))
        embed.add_field(name="Trades Today", value=stats.get('trades_today', 0))
        embed.add_field(name="Max Daily", value=stats.get('max_daily', 5))
        embed.add_field(name="Market Open", value="✅" if stats.get('market_open') else "❌")
        await ctx.send(embed=embed)
    except Exception as e:
        await ctx.send(f"❌ Error: {e}")


def run_discord_bot():
    """Run Discord bot in separate thread"""
    try:
        token = os.getenv('DISCORD_TOKEN')
        if not token:
            logger.error("DISCORD_TOKEN not set")
            return
        bot.run(token)
    except Exception as e:
        logger.error(f"Discord bot error: {e}")


# Start Discord bot in background thread
discord_thread = threading.Thread(target=run_discord_bot, daemon=True)
discord_thread.start()
logger.info("🎓 Discord bot started in background thread")


# ── API Endpoints ─────────────────────────────────────────────────────
@app.get("/")
async def root():
    return {"status": "online", "service": "Self-Learning Trading Bot"}


@app.get("/research/{ticker}")
async def research_endpoint(ticker: str):
    """Full research report"""
    ticker = ticker.upper()
    try:
        result = researcher.research(ticker)
        return JSONResponse(result)
    except Exception as e:
        logger.error(f"Research error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/scan")
async def scan_market():
    """Scan watchlist for opportunities"""
    try:
        watchlist = ['AAPL', 'MSFT', 'GOOGL', 'AMZN', 'TSLA', 'NVDA', 'META']
        signals = []
        
        for ticker in watchlist:
            evaluation = momentum_strategy.evaluate(ticker)
            if evaluation['decision'] == 'BUY':
                signals.append({
                    'ticker': ticker,
                    'action': 'BUY',
                    'price': evaluation['entry_price'],
                    'score': evaluation['total_score'],
                    'reason': f"Score: {evaluation['total_score']:.1f}"
                })
        
        return JSONResponse({"signals": signals, "timestamp": datetime.now().isoformat()})
    except Exception as e:
        logger.error(f"Scan error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/learn")
async def learn_endpoint():
    """Force strategy learning"""
    try:
        result = await adaptive_strategy.learn()
        return JSONResponse(result)
    except Exception as e:
        logger.error(f"Learn error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/journal")
async def journal_endpoint(limit: int = 10):
    """Mistake journal"""
    try:
        mistakes = await trade_memory.get_mistakes(limit)
        return JSONResponse({"mistakes": mistakes})
    except Exception as e:
        logger.error(f"Journal error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/stats")
async def stats_endpoint():
    """Trading statistics"""
    try:
        stats = await trading_engine.get_stats() if trading_engine else {}
        return JSONResponse(stats)
    except Exception as e:
        logger.error(f"Stats error: {e}")
        return JSONResponse({"error": str(e)})


@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard():
    """Web dashboard"""
    return """
    <!DOCTYPE html>
    <html>
    <head>
        <title>🤖 AI Trading Bot</title>
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
                text-align: center;
            }
            .stat-value { font-size: 28px; font-weight: bold; margin-top: 10px; }
            .positive { color: #00d4aa; }
            .btn {
                padding: 15px 30px;
                border: none;
                border-radius: 10px;
                cursor: pointer;
                font-size: 16px;
                font-weight: bold;
                margin: 10px;
            }
            .btn-primary { background: #00d4aa; color: #0f1419; }
            .research-section {
                padding: 30px;
                max-width: 1200px;
                margin: 0 auto;
            }
            .research-input {
                display: flex;
                gap: 10px;
                margin: 20px 0;
            }
            input {
                flex: 1;
                padding: 15px;
                background: #1a2332;
                border: 1px solid #2a3441;
                color: #fff;
                border-radius: 10px;
            }
            .results {
                background: #1a2332;
                padding: 20px;
                border-radius: 15px;
                min-height: 150px;
            }
        </style>
    </head>
    <body>
        <div class="header">
            <h1>🤖 AI Trading Bot</h1>
            <p>Self-learning algorithmic trading | Autonomous Mode: <span id="autostatus">Loading...</span></p>
        </div>
        
        <div class="stats-grid">
            <div class="stat-card">
                <h3>Risk per Trade</h3>
                <div class="stat-value" id="risk">-</div>
            </div>
            <div class="stat-card">
                <h3>Trades Today</h3>
                <div class="stat-value" id="trades">-</div>
            </div>
            <div class="stat-card">
                <h3>Market Status</h3>
                <div class="stat-value" id="market">-</div>
            </div>
        </div>
        
        <div style="text-align: center;">
            <button class="btn btn-primary" onclick="scanMarket()">🔍 Scan Market</button>
        </div>
        
        <div class="research-section">
            <h2>Research Stock</h2>
            <div class="research-input">
                <input type="text" id="ticker" placeholder="Enter ticker (AAPL, TSLA, etc.)">
                <button class="btn btn-primary" onclick="research()">Research</button>
            </div>
            <div class="results" id="results">Enter a ticker to see analysis...</div>
        </div>
        
        <script>
            async function loadStats() {
                try {
                    const res = await fetch('/stats');
                    const data = await res.json();
                    document.getElementById('risk').textContent = (data.risk_per_trade * 100).toFixed(1) + '%';
                    document.getElementById('trades').textContent = data.trades_today || 0;
                    document.getElementById('market').textContent = data.market_open ? 'Open' : 'Closed';
                    document.getElementById('autostatus').textContent = data.active ? 'ACTIVE' : 'INACTIVE';
                } catch(e) {}
            }
            
            async function scanMarket() {
                alert('Scanning market for opportunities...');
                const res = await fetch('/scan');
                const data = await res.json();
                alert(`Found ${data.signals.length} buy signals!`);
            }
            
            async function research() {
                const ticker = document.getElementById('ticker').value.toUpperCase();
                if (!ticker) return;
                
                const results = document.getElementById('results');
                results.innerHTML = 'Researching...';
                
                try {
                    const res = await fetch(`/research/${ticker}`);
                    const data = await res.json();
                    results.innerHTML = `
                        <h3 style="color: #00d4aa;">${data.ticker}</h3>
                        <p>Technical: ${data.technical.toFixed(1)}/100</p>
                        <p>Fundamental: ${data.fundamental.toFixed(1)}/100</p>
                        <p>Sentiment: ${data.sentiment.toFixed(1)}/100</p>
                        <p>Risk: ${data.risk.toFixed(1)}/100</p>
                        <p>Price: $${data.price.toFixed(2)}</p>
                        <p><strong>Total Score: ${data.total_score.toFixed(1)}/100</strong></p>
                    `;
                } catch(e) {
                    results.innerHTML = 'Error researching stock';
                }
            }
            
            loadStats();
            setInterval(loadStats, 30000);
        </script>
    </body>
    </html>
    """


@app.get("/health")
async def health_check():
    return {"status": "ok", "service": "self-learning-trading-bot"}


# ── Global Variables ──────────────────────────────────────────────────
trading_engine = None


# ── Run Server ────────────────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)
