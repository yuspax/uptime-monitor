import time
from unittest.mock import MagicMock, patch

import psycopg2
from fastapi.testclient import TestClient
from requests.exceptions import Timeout

import app


def test_sites_loaded():
    assert app.SITES
    assert all(site.strip().startswith(("https://", "http://")) for site in app.SITES)


@patch("app.requests.get")
def test_check_site_up_200(mock_get):
    mock_get.return_value = MagicMock(status_code=200)

    status, code, latency = app.check_site("https://example.com")

    assert status == "UP"
    assert code == 200
    assert isinstance(latency, int)
    assert latency >= 0
    mock_get.assert_called_once_with("https://example.com", timeout=5)


@patch("app.requests.get")
def test_check_site_down_500(mock_get):
    mock_get.return_value = MagicMock(status_code=500)

    status, code, latency = app.check_site("https://example.com")

    assert status == "DOWN"
    assert code == 500
    assert isinstance(latency, int)


@patch("app.requests.get")
def test_check_site_timeout(mock_get):
    mock_get.side_effect = Timeout("Connection timed out")

    status, code, latency = app.check_site("https://example.com")

    assert status == "DOWN"
    assert code == 0
    assert latency == 0


client = TestClient(app.app)


def test_health_ok():
    app.last_loop_at = time.monotonic()

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_health_stalled():
    app.last_loop_at = time.monotonic() - app.HEALTH_TIMEOUT - 1

    response = client.get("/health")

    assert response.status_code == 503


@patch("app.connect_db")
def test_sites_status(mock_connect):
    rows = [{"site": "https://example.com", "status": "UP", "status_code": 200, "latency_ms": 42}]
    cursor = mock_connect.return_value.cursor.return_value.__enter__.return_value
    cursor.fetchall.return_value = rows

    response = client.get("/sites")

    assert response.status_code == 200
    assert response.json() == rows


@patch("app.connect_db")
def test_sites_status_db_down(mock_connect):
    mock_connect.side_effect = psycopg2.OperationalError("connection refused")

    response = client.get("/sites")

    assert response.status_code == 503


@patch("app.connect_db")
def test_site_history(mock_connect):
    site = app.SITES[0]
    cursor = mock_connect.return_value.cursor.return_value.__enter__.return_value
    cursor.fetchall.return_value = []

    response = client.get("/sites/history", params={"site": site, "limit": 10})

    assert response.status_code == 200
    assert cursor.execute.call_args.args[1] == (site, 10)


def test_site_history_unknown_site():
    response = client.get("/sites/history", params={"site": "https://unknown.example"})

    assert response.status_code == 404
