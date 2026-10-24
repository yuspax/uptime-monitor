from unittest.mock import MagicMock, patch

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
