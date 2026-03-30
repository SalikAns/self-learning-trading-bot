import discord
from discord.ext import commands
import os
import asyncio

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="$", intents=intents, help_command=None)

@bot.event
async def on_ready():
    print(f'🤖 Trading Bot logged in as {bot.user}')
    print(f'Bot is in {len(bot.guilds)} servers')

@bot.command(name="research")
async def research_cmd(ctx, ticker: str):
    """Research a stock."""
    await ctx.send(f"🔍 Researching {ticker.upper()}... (connect to your research endpoint)")

@bot.command(name="portfolio")
async def portfolio_cmd(ctx):
    """Show portfolio."""
    await ctx.send("📈 Portfolio: $100,000 (Paper Trading)")

@bot.command(name="help")
async def help_cmd(ctx):
    """Show help."""
    await ctx.send("""
💰 **Trading Bot Commands:**
`$research [ticker]` - Research stock
`$portfolio` - View portfolio
`$trades` - Recent trades
`$learn` - Force learning cycle
    """)

def run_discord_bot():
    """Start Discord bot."""
    token = os.getenv("DISCORD_TOKEN")
    if not token:
        print("⚠️ DISCORD_TOKEN not set")
        return
    
    try:
        bot.run(token)
    except Exception as e:
        print(f"❌ Discord error: {e}")

if __name__ == "__main__":
    run_discord_bot()
