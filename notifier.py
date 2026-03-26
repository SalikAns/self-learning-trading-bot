"""
Telegram notification alerts for the trading bot.
Sends formatted alerts via the Telegram Bot API.
"""
import httpx
import os
from utils.logger import get_logger

log = get_logger("notifier")

TELEGRAM_BOT_TOKEN = os.getenv("8689981602:AAHHp2DQwxa0HNupqEtCYIjGWqf3f_vTFDU", "")
TELEGRAM_CHAT_ID = os.getenv("6784056041", "")
BASE_URL = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}" if TELEGRAM_BOT_TOKEN else ""


async def _send(message: str, emoji: str = "📊") -> bool:
    """Send a message to Telegram. Returns True on success."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        log.info("Telegram not configured — skipping alert")
        return False

    full_message = f"{emoji} <b>Trading Bot Alert</b>\n\n{message}"

    async with httpx.AsyncClient() as client:
        try:
            resp = await client.post(
                f"{BASE_URL}/sendMessage",
                json={
                    "chat_id": TELEGRAM_CHAT_ID,
                    "text": full_message,
                    "parse_mode": "HTML",
                    "disable_notification": False,
                },
                timeout=10,
            )
            resp.raise_for_status()
            log.info("Alert sent to Telegram")
            return True
        except Exception as e:
            log.error(f"Failed to send Telegram alert: {e}")
            return False


async def notify_trade(ticker: str, action: str, price: float | None,
                       confidence: float, score: float, gates: dict) -> bool:
    """Alert when a trade decision is made."""
    emoji = "🟢" if action == "BUY" else "🔴"
    price_str = f"${price:.2f}" if price else "N/A"
    gates_str = "\n".join(
        f"  • {k}: {'✅' if v else '❌'}" for k, v in gates.items()
    )

    msg = (
        f"<b>{action}: {ticker}</b>\n\n"
        f"Price: {price_str}\n"
        f"Score: {score:.1f}/100\n"
        f"Confidence: {confidence:.0%}\n\n"
        f"<b>Gates:</b>\n{gates_str}\n\n"
        f"<i>Paper trading — no real money at risk</i>"
    )
    return await _send(msg, emoji)


async def notify_learn(adjustments: dict, win_rate: float,
                       total_trades: int) -> bool:
    """Alert when the AI updates strategy parameters."""
    if not adjustments:
        return False

    changes = "\n".join(
        f"  • {k}: {v['old']} → {v['new']}" for k, v in adjustments.items()
    )
    msg = (
        f"<b>🧠 Strategy Updated</b>\n\n"
        f"Win rate: {win_rate:.1%} ({total_trades} trades)\n\n"
        f"<b>Changes:</b>\n{changes}\n\n"
        f"Strategy is now more selective based on what worked."
    )
    return await _send(msg, "🧠")


async def notify_mistake(ticker: str, loss_pct: float,
                         red_flags: list[str]) -> bool:
    """Alert when a significant loss triggers mistake analysis."""
    flags_str = ", ".join(red_flags)
    msg = (
        f"<b>⚠️ Mistake Logged: {ticker}</b>\n\n"
        f"Loss: {loss_pct:+.1f}%\n"
        f"Red flags: {flags_str}\n\n"
        f"This pattern will be penalised in future evaluations."
    )
    return await _send(msg, "⚠️")


async def notify_daily_summary(trades_today: int, winners: int,
                               losers: int) -> bool:
    """End-of-day summary."""
    win_rate = winners / trades_today if trades_today > 0 else 0
    msg = (
        f"<b>📈 Daily Summary</b>\n\n"
        f"Decisions: {trades_today}\n"
        f"Winners: {winners}  |  Losers: {losers}\n"
        f"Win rate: {win_rate:.0%}"
    )
    return await _send(msg, "📈")
