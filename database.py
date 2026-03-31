-- Track strategy evolution
CREATE TABLE IF NOT EXISTS strategy_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp DATETIME,
    strategy_rules TEXT,
    win_rate REAL,
    trades_count INTEGER,
    is_active BOOLEAN DEFAULT 0
)

-- Track autonomous trades separately
CREATE TABLE IF NOT EXISTS autonomous_trades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker TEXT,
    action TEXT,
    shares REAL,
    price REAL,
    timestamp DATETIME,
    reason TEXT,
    score INTEGER,
    pnl REAL DEFAULT 0
)

-- Track learning cycles
CREATE TABLE IF NOT EXISTS learning_cycles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp DATETIME,
    trades_analyzed INTEGER,
    adjustments_made TEXT,
    new_strategy_generated BOOLEAN
)
"""
SQLite schema + async query helpers.
"""
import aiosqlite
import config
from utils.logger import get_logger

log = get_logger("database")


async def get_db() -> aiosqlite.Connection:
    conn = await aiosqlite.connect(config.DATABASE_PATH)
    conn.row_factory = aiosqlite.Row
    await conn.execute("PRAGMA journal_mode=WAL;")
    await conn.execute("PRAGMA foreign_keys=ON;")
    return conn


async def init_db() -> None:
    conn = await get_db()
    await conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS trade_decisions (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker        TEXT    NOT NULL,
            entry_time    TIMESTAMP,
            features      TEXT,       -- JSON: all four research scores + metadata
            decision      TEXT,       -- 'BUY' or 'PASS'
            confidence    REAL,       -- 0.0 – 1.0
            status        TEXT DEFAULT 'OPEN',  -- 'OPEN' or 'CLOSED'
            entry_price   REAL,
            exit_price    REAL,
            pnl_pct       REAL,
            exit_reason   TEXT,
            holding_days  INTEGER,
            created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS mistake_journal (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            trade_id        INTEGER REFERENCES trade_decisions(id),
            ticker          TEXT,
            loss_pct        REAL,
            red_flags       TEXT,   -- JSON array of flag strings
            date            TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            lesson_learned  TEXT
        );

        CREATE TABLE IF NOT EXISTS strategy_evolution (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp       TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            win_rate        REAL,
            total_trades    INTEGER,
            adjustments     TEXT,   -- JSON: keys that changed
            params_snapshot TEXT    -- JSON: full params at this point in time
        );
        """
    )
    await conn.commit()
    await conn.close()
    log.info("Database initialised.")


async def execute(query: str, params: tuple = ()) -> None:
    conn = await get_db()
    await conn.execute(query, params)
    await conn.commit()
    await conn.close()


async def execute_returning(query: str, params: tuple = ()) -> int:
    """Execute INSERT and return the last inserted row id."""
    conn = await get_db()
    cur = await conn.execute(query, params)
    await conn.commit()
    row_id = cur.lastrowid
    await conn.close()
    return row_id


async def fetch_one(query: str, params: tuple = ()) -> dict | None:
    conn = await get_db()
    cur = await conn.execute(query, params)
    row = await cur.fetchone()
    await conn.close()
    return dict(row) if row else None


async def fetch_all(query: str, params: tuple = ()) -> list[dict]:
    conn = await get_db()
    cur = await conn.execute(query, params)
    rows = await cur.fetchall()
    await conn.close()
    return [dict(r) for r in rows]
