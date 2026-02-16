"""Tests for the order store JSON persistence layer."""

import json
from pathlib import Path

import pytest

from options_pricer.order_store import add_order, load_orders, save_orders, update_order


class TestLoadOrders:
    def test_missing_file(self, tmp_path):
        fp = tmp_path / "orders.json"
        assert load_orders(fp) == []

    def test_corrupt_json(self, tmp_path):
        fp = tmp_path / "orders.json"
        fp.write_text("NOT VALID JSON {{{", encoding="utf-8")
        assert load_orders(fp) == []

    def test_empty_orders_key(self, tmp_path):
        fp = tmp_path / "orders.json"
        fp.write_text('{"orders": []}', encoding="utf-8")
        assert load_orders(fp) == []

    def test_loads_existing(self, tmp_path):
        fp = tmp_path / "orders.json"
        data = {"orders": [{"id": "abc", "underlying": "AAPL"}]}
        fp.write_text(json.dumps(data), encoding="utf-8")
        result = load_orders(fp)
        assert len(result) == 1
        assert result[0]["underlying"] == "AAPL"


class TestSaveOrders:
    def test_creates_file(self, tmp_path):
        fp = tmp_path / "orders.json"
        save_orders([{"id": "1", "underlying": "AAPL"}], fp)
        assert fp.exists()
        data = json.loads(fp.read_text(encoding="utf-8"))
        assert len(data["orders"]) == 1

    def test_creates_parent_dirs(self, tmp_path):
        fp = tmp_path / "subdir" / "orders.json"
        save_orders([], fp)
        assert fp.exists()

    def test_overwrites_existing(self, tmp_path):
        fp = tmp_path / "orders.json"
        save_orders([{"id": "1"}], fp)
        save_orders([{"id": "1"}, {"id": "2"}], fp)
        data = json.loads(fp.read_text(encoding="utf-8"))
        assert len(data["orders"]) == 2


class TestAddOrder:
    def test_adds_to_empty(self, tmp_path):
        fp = tmp_path / "orders.json"
        result = add_order({"id": "abc", "underlying": "AAPL"}, fp)
        assert len(result) == 1
        assert result[0]["id"] == "abc"
        # Verify persisted
        assert len(load_orders(fp)) == 1

    def test_appends_to_existing(self, tmp_path):
        fp = tmp_path / "orders.json"
        add_order({"id": "1", "underlying": "AAPL"}, fp)
        result = add_order({"id": "2", "underlying": "MSFT"}, fp)
        assert len(result) == 2
        assert result[1]["underlying"] == "MSFT"


class TestUpdateOrder:
    def test_updates_existing(self, tmp_path):
        fp = tmp_path / "orders.json"
        add_order({"id": "abc", "traded": "No", "initiator": ""}, fp)
        result = update_order("abc", {"traded": "Yes", "initiator": "GS"}, fp)
        assert result[0]["traded"] == "Yes"
        assert result[0]["initiator"] == "GS"
        # Verify persisted
        loaded = load_orders(fp)
        assert loaded[0]["traded"] == "Yes"

    def test_update_nonexistent_id(self, tmp_path):
        fp = tmp_path / "orders.json"
        add_order({"id": "abc", "traded": "No"}, fp)
        result = update_order("nonexistent", {"traded": "Yes"}, fp)
        # Original unchanged
        assert result[0]["traded"] == "No"
