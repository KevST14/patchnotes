import pytest

from app import storage as storage_module


@pytest.fixture
def storage(tmp_path, monkeypatch):
    """Point app.storage at an isolated temp SQLite file per test."""
    monkeypatch.setattr(storage_module, "DB_PATH", tmp_path / "test.db")
    storage_module.init_db()
    return storage_module
