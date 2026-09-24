import pytest

from app.db import models
from app.tools.linkedin import oauth
from app.tools.sources import web_search


@pytest.fixture(autouse=True)
def isolate_data(tmp_path, monkeypatch):
    """Tests never read or write the real data/ directory (history, token, search cache)."""
    monkeypatch.setattr(models, "HISTORY_DB", tmp_path / "history.db")
    monkeypatch.setattr(oauth, "TOKEN_PATH", tmp_path / "linkedin_token.json")
    monkeypatch.setattr(web_search, "CACHE_DIR", tmp_path / "search-cache")
