import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import pytest
import app

def test_sites_list_is_not_empty():
    assert len(app.sites) > 0

def test_google_is_monitored():
    assert "google.com" in app.sites

def test_log_directory_creation(tmp_path):
    assert app.log_file.endswith(".txt")