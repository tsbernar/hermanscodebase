"""SQLite-based persistence layer for the order blotter.

Orders are stored at ~/.options_pricer/orders.db using SQLite with WAL mode
for safe concurrent access by multiple users. Each order is stored as a row
with its full dict serialized as JSON in the `data` column.

Migrates automatically from the legacy orders.json file on first use.
"""

import json
import logging
import sqlite3
from pathlib import Path

logger = logging.getLogger(__name__)

_ORDERS_DIR = Path.home() / ".options_pricer"
_DB_FILE = _ORDERS_DIR / "orders.db"
_LEGACY_JSON = _ORDERS_DIR / "orders.json"

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS orders (
    id TEXT PRIMARY KEY,
    data TEXT NOT NULL,
    created_by TEXT DEFAULT '',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
"""


def _get_db(db_path: Path | None = None) -> sqlite3.Connection:
    """Open a SQLite connection with WAL mode for concurrent access."""
    fp = db_path or _DB_FILE
    fp.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(fp), timeout=10)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute(_CREATE_TABLE)
    return conn


def _migrate_from_json(db_path: Path | None = None) -> None:
    """One-time migration: import orders from legacy orders.json into SQLite."""
    json_fp = _LEGACY_JSON
    if not json_fp.exists():
        return
    try:
        with open(json_fp, "r", encoding="utf-8") as f:
            data = json.load(f)
        orders = data.get("orders", [])
        if not orders:
            return
        conn = _get_db(db_path)
        try:
            for order in orders:
                order_id = order.get("id")
                if not order_id:
                    continue
                conn.execute(
                    "INSERT OR IGNORE INTO orders (id, data, created_by) VALUES (?, ?, ?)",
                    (order_id, json.dumps(order, default=str), order.get("created_by", "")),
                )
            conn.commit()
            # Rename legacy file so migration doesn't re-run
            json_fp.rename(json_fp.with_suffix(".json.bak"))
            logger.info("Migrated %d orders from JSON to SQLite", len(orders))
        finally:
            conn.close()
    except Exception:
        logger.warning("Failed to migrate legacy orders.json", exc_info=True)


def _ensure_db(db_path: Path | None = None) -> None:
    """Ensure the DB exists and run migration if needed."""
    fp = db_path or _DB_FILE
    first_run = not fp.exists()
    conn = _get_db(db_path)
    conn.close()
    if first_run:
        _migrate_from_json(db_path)


def load_orders(db_path: Path | None = None) -> list[dict]:
    """Load all orders from SQLite. Returns [] if DB is missing or corrupt."""
    _ensure_db(db_path)
    try:
        conn = _get_db(db_path)
        try:
            rows = conn.execute(
                "SELECT data FROM orders ORDER BY created_at ASC"
            ).fetchall()
            return [json.loads(row[0]) for row in rows]
        finally:
            conn.close()
    except Exception:
        logger.warning("Failed to load orders from SQLite", exc_info=True)
        return []


def save_orders(orders: list[dict], db_path: Path | None = None) -> None:
    """Replace all orders in SQLite (full sync from in-memory state)."""
    _ensure_db(db_path)
    conn = _get_db(db_path)
    try:
        conn.execute("DELETE FROM orders")
        for order in orders:
            order_id = order.get("id", "")
            conn.execute(
                "INSERT OR REPLACE INTO orders (id, data, created_by) VALUES (?, ?, ?)",
                (order_id, json.dumps(order, default=str), order.get("created_by", "")),
            )
        conn.commit()
    except Exception:
        logger.warning("Failed to save orders to SQLite", exc_info=True)
        conn.rollback()
        raise
    finally:
        conn.close()


def add_order(order: dict, db_path: Path | None = None) -> list[dict]:
    """Add a new order and persist. Returns updated orders list."""
    _ensure_db(db_path)
    conn = _get_db(db_path)
    try:
        order_id = order.get("id", "")
        conn.execute(
            "INSERT INTO orders (id, data, created_by) VALUES (?, ?, ?)",
            (order_id, json.dumps(order, default=str), order.get("created_by", "")),
        )
        conn.commit()
        rows = conn.execute(
            "SELECT data FROM orders ORDER BY created_at ASC"
        ).fetchall()
        return [json.loads(row[0]) for row in rows]
    except Exception:
        logger.warning("Failed to add order to SQLite", exc_info=True)
        conn.rollback()
        raise
    finally:
        conn.close()


def update_order(order_id: str, updates: dict, db_path: Path | None = None) -> list[dict]:
    """Update an existing order by ID and persist. Returns updated orders list."""
    _ensure_db(db_path)
    conn = _get_db(db_path)
    try:
        row = conn.execute(
            "SELECT data FROM orders WHERE id = ?", (order_id,)
        ).fetchone()
        if row:
            order = json.loads(row[0])
            order.update(updates)
            conn.execute(
                "UPDATE orders SET data = ?, created_by = ? WHERE id = ?",
                (json.dumps(order, default=str), order.get("created_by", ""), order_id),
            )
            conn.commit()
        rows = conn.execute(
            "SELECT data FROM orders ORDER BY created_at ASC"
        ).fetchall()
        return [json.loads(r[0]) for r in rows]
    except Exception:
        logger.warning("Failed to update order %s in SQLite", order_id, exc_info=True)
        conn.rollback()
        raise
    finally:
        conn.close()
