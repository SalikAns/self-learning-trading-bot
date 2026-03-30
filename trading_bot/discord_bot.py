import discord
from discord.ext import commands, tasks
import asyncio
import os
from datetime import datetime

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="$", intents=intents, help_command=None)

# Channel ID where alerts go (set this after creating channel)
ALERT_CHANNEL_ID = None  # Will set from env

@bot.event
async def on_ready():
    print(f'🤖 Trading Bot logged in as {bot.user}')
    # Start background tasks
    daily_summary.start()

@bot.command(name="portfolio")
async def portfolio_cmd(ctx):
    """Show current portfolio."""
    from broker.alpaca import trader
    
    summary = trader.get_portfolio_summary()
    
    embed = discord.Embed(
        title="📈 Portfolio Summary",
        description=f"""
**Value:** ${summary['portfolio_value']:,.2f}
**Starting:** ${summary['starting_value']:,.2f}
**Return:** {(summary['total_return'] * 100):.2f}%
        """,
        color=0x00d4aa if summary['total_return'] >= 0 else 0xff6b6b,
        timestamp=datetime.now()
    )
    await ctx.send(embed=embed)

@bot.command(name="research")
async def research_cmd(ctx, ticker: str):
    """Research a stock."""
    async with ctx.typing():
        from research.comprehensive import ComprehensiveResearch
        
        researcher = ComprehensiveResearch()
        report = researcher.analyze(ticker.upper())
        
        if not report:
            await ctx.send(f"❌ Could not analyze {ticker}")
            return
        
        embed = discord.Embed(
            title=f"🔍 {report['ticker']} Research",
            description=f"""
**Overall Score:** {report['total_score']:.1f}/100

📊 Technical: {report['technical']:.1f}
📈 Fundamental: {report['fundamental']:.1f}
💭 Sentiment: {report['sentiment']:.1f}
⚠️ Risk: {report['risk']:.1f}

**Price:** ${report['price']:.2f}
**Volatility:** {report['volatility']:.1f}%
**Volume:** {report['volume_trend']}
            """,
            color=0x00d4aa if report['total_score'] > 70 else 0xffd93d if report['total_score'] > 50 else 0xff6b6b,
            timestamp=datetime.now()
        )
        await ctx.send(embed=embed)

@bot.command(name="trades")
async def trades_cmd(ctx, limit: int = 5):
    """Show recent trades."""
    # Fetch from database
    trades = await get_recent_trades(limit)
    
    if not trades:
        await ctx.send("No trades yet.")
        return
    
    embed = discord.Embed(
        title="🔄 Recent Trades",
        color=0x667eea
    )
    
    for trade in trades:
        emoji = "🟢" if trade['pnl_pct'] > 0 else "🔴" if trade['pnl_pct'] < 0 else "⚪"
        embed.add_field(
            name=f"{emoji} {trade['ticker']} ({trade['action']})",
            value=f"P&L: {trade['pnl_pct']:.2f}% | {trade['exit_reason'][:50]}",
            inline=False
        )
    
    await ctx.send(embed=embed)

@bot.command(name="learn")
async def learn_cmd(ctx):
    """Force strategy learning."""
    async with ctx.typing():
        from ml_engine.feedback_loop import memory
        
        adjustments = await memory.get_strategy_adjustments()
        
        if adjustments['adjustments']:
            changes = "\n".join([f"• {k}" for k in adjustments['adjustments'].keys()])
            msg = f"🧠 Strategy updated:\n{changes}\n\nWin rate: {adjustments['win_rate']:.1%}"
        else:
            msg = "📊 Not enough trades to learn yet. Need 10+ closed trades."
        
        await ctx.send(msg)

@tasks.loop(hours=24)
async def daily_summary():
    """Send daily summary to channel."""
    if not ALERT_CHANNEL_ID:
        return
    
    channel = bot.get_channel(int(ALERT_CHANNEL_ID))
    if not channel:
        return
    
    from broker.alpaca import trader
    summary = trader.get_portfolio_summary()
    
    # Calculate today's P&L (simplified)
    day_pnl = summary['portfolio_value'] - summary['starting_value']
    
    embed = discord.Embed(
        title="📊 Daily Trading Summary",
        description=f"""
Portfolio: ${summary['portfolio_value']:,.2f}
Today's P&L: {'+' if day_pnl >= 0 else ''}${day_pnl:,.2f}

View dashboard: https://your-trading-bot.up.railway.app/
        """,
        color=0x00d4aa if day_pnl >= 0 else 0xff6b6b,
        timestamp=datetime.now()
    )
    
    await channel.send(embed=embed)

# Alert functions called from main bot
async def send_trade_alert(ticker: str, action: str, price: float, confidence: float):
    """Send trade alert to Discord."""
    if not ALERT_CHANNEL_ID:
        return
    
    channel = bot.get_channel(int(ALERT_CHANNEL_ID))
    if not channel:
        return
    
    emoji = "🟢" if action == "BUY" else "🔴"
    
    embed = discord.Embed(
        title=f"{emoji} {action} Executed: {ticker}",
        description=f"""
**Price:** ${price:.2f}
**Confidence:** {confidence:.0%}
**Mode:** Paper Trading (no real money)

View details: https://your-trading-bot.up.railway.app/
        """,
        color=0x00d4aa if action == "BUY" else 0xff6b6b,
        timestamp=datetime.now()
    )
    
    await channel.send(embed=embed)

def run_discord_bot():
    token = os.getenv("DISCORD_TOKEN")
    if not token:
        print("⚠️ DISCORD_TOKEN not set")
        return
    
    global ALERT_CHANNEL_ID
    ALERT_CHANNEL_ID = os.getenv("DISCORD_ALERT_CHANNEL_ID")
    
    bot.run(token)

if __name__ == "__main__":
    run_discord_bot()
