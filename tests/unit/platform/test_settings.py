from pathlib import Path

import pytest

from riso import paths
from riso.platform import Settings


@pytest.fixture(autouse=True)
def clean_environment(monkeypatch):
    for name in ("RISO_ENV", "RISO_VAR_DIR", "RISO_DB_URL", "RISO_TESSDATA", "RISO_SMTP_HOST"):
        monkeypatch.delenv(name, raising=False)


def test_the_defaults_put_everything_in_var():
    settings = Settings()
    assert settings.var_dir == paths.REPO_ROOT / "var"
    assert settings.db_url == f"sqlite:///{paths.REPO_ROOT / 'var' / 'riso.db'}"
    assert settings.tessdata == paths.REPO_ROOT / "var" / "tessdata"
    assert settings.env is None
    assert not settings.smtp_enabled


def test_the_database_and_models_follow_the_var_dir(monkeypatch, tmp_path):
    monkeypatch.setenv("RISO_VAR_DIR", str(tmp_path))
    settings = Settings()
    assert settings.var_dir == tmp_path
    assert settings.db_url == f"sqlite:///{tmp_path / 'riso.db'}"
    assert settings.files_dir == tmp_path / "files"


def test_explicit_variables_win(monkeypatch, tmp_path):
    monkeypatch.setenv("RISO_ENV", "test")
    monkeypatch.setenv("RISO_DB_URL", "sqlite:///elsewhere.db")
    monkeypatch.setenv("RISO_TESSDATA", str(tmp_path / "models"))
    monkeypatch.setenv("RISO_SMTP_HOST", "localhost")
    settings = Settings()
    assert settings.env == "test"
    assert settings.db_url == "sqlite:///elsewhere.db"
    assert settings.tessdata == Path(tmp_path / "models")
    assert settings.smtp_enabled


def test_an_unknown_environment_is_refused(monkeypatch):
    monkeypatch.setenv("RISO_ENV", "staging")
    with pytest.raises(ValueError):
        Settings()
