"""Settings from environment variables prefixed `RISO_` (guide §6.10).

| Variable | Default | Meaning |
|---|---|---|
| `RISO_ENV` | unset | `dev`, `test` or `prod`; `riso seed` refuses unless dev or test |
| `RISO_VAR_DIR` | `<repo>/var` | runtime state: the database, files, models, reports |
| `RISO_DB_URL` | `sqlite:///<var>/riso.db` | SQLAlchemy URL |
| `RISO_TESSDATA` | `<var>/tessdata` | Tesseract models |
| `RISO_SMTP_HOST`, `_PORT`, `_USER`, `_PASSWORD`, `_FROM` | unset | optional mail sending |
"""

from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from riso import paths


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="RISO_", extra="ignore", frozen=True)

    env: Literal["dev", "test", "prod"] | None = None
    var_dir: Path = Field(default_factory=lambda: paths.REPO_ROOT / "var")
    db_url: str = ""
    tessdata: Path | None = None
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_user: str | None = None
    smtp_password: SecretStr | None = None
    smtp_from: str | None = None

    @model_validator(mode="after")
    def _defaults_from_var_dir(self) -> "Settings":
        # Frozen model: fill the derived defaults through object.__setattr__.
        if not self.db_url:
            object.__setattr__(self, "db_url", f"sqlite:///{self.var_dir / 'riso.db'}")
        if self.tessdata is None:
            object.__setattr__(self, "tessdata", self.var_dir / "tessdata")
        return self

    @property
    def files_dir(self) -> Path:
        return self.var_dir / "files"

    @property
    def smtp_enabled(self) -> bool:
        return self.smtp_host is not None
