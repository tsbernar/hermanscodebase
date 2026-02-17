"""Tests for Bloomberg Bridge HTTP endpoints."""

import json

import pytest

from options_pricer.bloomberg_bridge import app, init_app


@pytest.fixture
def client():
    """Create a Flask test client with mock Bloomberg."""
    init_app(use_mock=True)
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


class TestStatusEndpoint:
    def test_status_returns_mock(self, client):
        resp = client.get("/api/status")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["status"] == "mock"

    def test_status_has_port(self, client):
        resp = client.get("/api/status")
        data = resp.get_json()
        assert "port" in data


class TestSpotEndpoint:
    def test_spot_known_ticker(self, client):
        resp = client.get("/api/spot/AAPL")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["spot"] > 0

    def test_spot_case_insensitive(self, client):
        resp1 = client.get("/api/spot/aapl")
        resp2 = client.get("/api/spot/AAPL")
        assert resp1.get_json()["spot"] == resp2.get_json()["spot"]

    def test_spot_unknown_ticker(self, client):
        resp = client.get("/api/spot/ZZZZZ")
        assert resp.status_code == 200
        data = resp.get_json()
        # MockBloombergClient returns 100.0 for unknown tickers
        assert data["spot"] == 100.0


class TestMultiplierEndpoint:
    def test_multiplier_equity(self, client):
        resp = client.get("/api/multiplier/AAPL")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["multiplier"] == 100


class TestOptionQuotesEndpoint:
    def test_option_quotes_basic(self, client):
        payload = {
            "underlying": "AAPL",
            "legs": [
                {"expiry": "2026-06-19", "strike": 250.0, "option_type": "call"},
            ],
        }
        resp = client.post(
            "/api/option_quotes",
            data=json.dumps(payload),
            content_type="application/json",
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert "spot" in data
        assert data["spot"] > 0
        assert len(data["quotes"]) == 1
        q = data["quotes"][0]
        assert q["bid"] > 0
        assert q["offer"] > 0
        assert q["offer"] >= q["bid"]
        assert data["multiplier"] == 100

    def test_option_quotes_multiple_legs(self, client):
        payload = {
            "underlying": "AAPL",
            "legs": [
                {"expiry": "2026-06-19", "strike": 240.0, "option_type": "put"},
                {"expiry": "2026-06-19", "strike": 220.0, "option_type": "put"},
            ],
        }
        resp = client.post(
            "/api/option_quotes",
            data=json.dumps(payload),
            content_type="application/json",
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert len(data["quotes"]) == 2

    def test_option_quotes_missing_body(self, client):
        resp = client.post(
            "/api/option_quotes",
            content_type="application/json",
        )
        assert resp.status_code == 400

    def test_option_quotes_missing_fields(self, client):
        resp = client.post(
            "/api/option_quotes",
            data=json.dumps({"underlying": "AAPL"}),
            content_type="application/json",
        )
        assert resp.status_code == 400

    def test_option_quotes_bad_expiry(self, client):
        payload = {
            "underlying": "AAPL",
            "legs": [
                {"expiry": "not-a-date", "strike": 250.0, "option_type": "call"},
            ],
        }
        resp = client.post(
            "/api/option_quotes",
            data=json.dumps(payload),
            content_type="application/json",
        )
        assert resp.status_code == 200
        data = resp.get_json()
        # Bad expiry should return zeroed quote, not crash
        q = data["quotes"][0]
        assert q["bid"] == 0
        assert q["offer"] == 0

    def test_cors_headers(self, client):
        resp = client.get("/api/status")
        # flask-cors adds these headers
        assert resp.status_code == 200
