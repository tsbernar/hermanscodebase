"""JSON-based persistence layer for the order blotter.

Orders are stored at ~/.options_pricer/orders.json with atomic writes
(write to temp file, then rename) to prevent corruption.
Both dashboards can read/write the same file.
"""

import json
import os
import tempfile
from pathlib import Path


_ORDERS_DIR = Path.home() / ".options_pricer"
_ORDERS_FILE = _ORDERS_DIR / "orders.json"


def load_orders(filepath: Path | None = None) -> list[dict]:
    """Load all orders from the JSON file. Returns [] if missing or corrupt."""
    fp = filepath or _ORDERS_FILE
    if not fp.exists():
        return []
    try:
        with open(fp, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get("orders", [])
    except (json.JSONDecodeError, KeyError, IOError):
        return []


def save_orders(orders: list[dict], filepath: Path | None = None) -> None:
    """Atomically write orders to the JSON file (write to temp, then rename)."""
    fp = filepath or _ORDERS_FILE
    fp.parent.mkdir(parents=True, exist_ok=True)

    fd, tmp_path = tempfile.mkstemp(
        dir=str(fp.parent), suffix=".tmp", prefix=".orders_"
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump({"orders": orders}, f, indent=2, default=str)
        os.replace(tmp_path, str(fp))
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def add_order(order: dict, filepath: Path | None = None) -> list[dict]:
    """Add a new order and persist. Returns updated orders list."""
    orders = load_orders(filepath)
    orders.append(order)
    save_orders(orders, filepath)
    return orders


def update_order(order_id: str, updates: dict, filepath: Path | None = None) -> list[dict]:
    """Update an existing order by ID and persist. Returns updated orders list."""
    orders = load_orders(filepath)
    for order in orders:
        if order.get("id") == order_id:
            order.update(updates)
            break
    save_orders(orders, filepath)
    return orders
