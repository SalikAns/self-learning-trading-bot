# database.py - SQLite database manager for trading bot
import sqlite3
import json
import asyncio
import aiosqlite
from datetime import datetime
from typing import List, Dict, Optional
import logging

logger = logging.getLogger(__name__)

DB_PATH = "trading.db"

async def init_db():
    """Initialize database tables"""
    async with aiosqlite.connect(DB_PATH) as db:
        # Trades table
        await db.execute("""
            CREATE TABLE IF NOT EXISTS trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ticker TEXT NOT NULL,
                action TEXT NOT NULL,
                shares REAL,
                price REAL,
                timestamp DATETIME,
                reason TEXT,
                score INTEGER,
                autonomous BOOLEAN DEFAULT 0,
                pnl REAL DEFAULT 0,
                exit_price REAL,
                exit_timestamp DATETIME,
                status TEXT DEFAULT 'OPEN'
            )
        """)
        
        # Strategy evolution table
        await db.execute("""
            CREATE TABLE IF NOT EXISTS strategy_evolution (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp DATETIME,
                risk REAL,
                win_rate REAL,
                adjustments TEXT,
                params_snapshot TEXT
            )
        """)
        
        # Watchlist table
        await db.execute("""
            CREATE TABLE IF NOT EXISTS watchlist (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ticker TEXT UNIQUE,
                added_at DATETIME
            )
        """)
        
        # Mistakes journal
        await db.execute("""
            CREATE TABLE IF NOT EXISTS mistakes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ticker TEXT,
                loss_pct REAL,
                red_flags TEXT,
                timestamp DATETIME,
                trade_id INTEGER
            )
        """)
        
        await db.commit()
        logger.info("Database initialized.")

async def record_trade(trade_data: Dict) -> int:
    """Record a trade"""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("""
            INSERT INTO trades (
                ticker, action, shares, price, timestamp, reason, score, autonomous
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            trade_data['ticker'],
            trade_data['action'],
            trade_data.get('shares'),
            trade_data['price'],
            trade_data.get('timestamp', datetime.now()),
            trade_data.get('reason'),
            trade_data.get('score'),
            trade_data.get('autonomous', False)
        ))
        await db.commit()
        return cursor.lastrowid

async def get_holdings(ticker: str) -> float:
    """Get current holdings for a ticker"""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("""
            SELECT SUM(CASE 
                WHEN action = 'BUY' THEN shares 
                WHEN action = 'SELL' THEN -shares 
                ELSE 0 
            END) as holdings
            FROM trades
            WHERE ticker = ? AND status = 'OPEN'
        """, (ticker,))
        row = await cursor.fetchone()
        return row[0] if row[0] else 0

async def get_portfolio_value() -> float:
    """Calculate total portfolio value"""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("""
            SELECT SUM(shares * price) FROM trades WHERE status = 'OPEN'
        """)
        row = await cursor.fetchone()
        return row[0] if row[0] else 10000  # Start with $10,000

async def get_recent_trades(hours: int = 24) -> List[Dict]:
    """Get recent trades"""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("""
            SELECT * FROM trades 
            WHERE timestamp > datetime('now', '-' || ? || ' hours')
            ORDER BY timestamp DESC
        """, (hours,))
        rows = await cursor.fetchall()
        
        trades = []
        for row in rows:
            trades.append({
                'id': row[0],
                'ticker': row[1],
                'action': row[2],
                'shares': row[3],
                'price': row[4],
                'timestamp': row[5],
                'reason': row[6],
                'score': row[7],
                'autonomous': row[8],
                'pnl': row[9]
            })
        return trades

async def get_autonomous_trades() -> List[Dict]:
    """Get all autonomous trades"""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("""
            SELECT * FROM trades WHERE autonomous = 1
            ORDER BY timestamp DESC
        """)
        rows = await cursor.fetchall()
        
        trades = []
        for row in rows:
            trades.append({
                'id': row[0],
                'ticker': row[1],
                'action': row[2],
                'shares': row[3],
                'price': row[4],
                'timestamp': row[5],
                'reason': row[6],
                'score': row[7],
                'pnl': row[9]
            })
        return trades

async def log_strategy_evolution(data: Dict):
    """Log strategy evolution"""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            INSERT INTO strategy_evolution (
                timestamp, risk, win_rate, adjustments, params_snapshot
            ) VALUES (?, ?, ?, ?, ?)
        """, (
            data['timestamp'],
            data.get('risk'),
            data.get('win_rate'),
            json.dumps(data.get('adjustments', {})),
            json.dumps(data.get('params_snapshot', {}))
        ))
        await db.commit()

async def get_watchlist() -> List[str]:
    """Get user's watchlist"""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("SELECT ticker FROM watchlist")
        rows = await cursor.fetchall()
        return [row[0] for row in rows]

async def add_to_watchlist(ticker: str):
    """Add ticker to watchlist"""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR IGNORE INTO watchlist (ticker, added_at) VALUES (?, ?)",
            (ticker.upper(), datetime.now())
        )
        await db.commit()

async def log_mistake(ticker: str, loss_pct: float, red_flags: List[str], trade_id: int = None):
    """Log a mistake for learning"""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            INSERT INTO mistakes (ticker, loss_pct, red_flags, timestamp, trade_id)
            VALUES (?, ?, ?, ?, ?)
        """, (
            ticker,
            loss_pct,
            json.dumps(red_flags),
            datetime.now(),
            trade_id
        ))
        await db.commit()

async def get_mistakes(limit: int = 10) -> List[Dict]:
    """Get recent mistakes"""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("""
            SELECT * FROM mistakes 
            ORDER BY timestamp DESC 
            LIMIT ?
        """, (limit,))
        rows = await cursor.fetchall()
        
        mistakes = []
        for row in rows:
            mistakes.append({
                'id': row[0],
                'ticker': row[1],
                'loss_pct': row[2],
                'red_flags': json.loads(row[3]) if row[3] else [],
                'timestamp': row[4],
                'trade_id': row[5]
            })
        return mistakes
