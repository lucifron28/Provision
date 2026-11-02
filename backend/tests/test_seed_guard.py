import pytest

from app.core.config import settings
from seed import main, seed_database


def test_production_seed_refuses_before_opening_a_database(monkeypatch):
    monkeypatch.setattr(settings, "ENVIRONMENT", "production")
    with pytest.raises(RuntimeError, match="disabled in production"):
        seed_database()


def test_seed_cli_requires_explicit_demo_opt_in():
    with pytest.raises(SystemExit) as exc:
        main([])
    assert exc.value.code == 2
