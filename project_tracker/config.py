"""Configuration classes, selected by the PROJECT_TRACKER_CONFIG environment variable.

Secrets and paths come from environment variables (see ``.env.example``); the classes
here only hold safe defaults.
"""

import os

CONFIG_ENV_VAR = "PROJECT_TRACKER_CONFIG"


class Config:
    """Settings shared by every environment."""

    TESTING = False
    SECRET_KEY: str | None = None
    SQLALCHEMY_DATABASE_URI: str | None = None


class DevelopmentConfig(Config):
    """Local development: insecure secret key, database in the instance folder."""

    SECRET_KEY = "dev-insecure-key"
    # Flask-SQLAlchemy resolves relative SQLite paths against the instance folder.
    SQLALCHEMY_DATABASE_URI = "sqlite:///project_tracker.db"


class TestingConfig(Config):
    """Automated tests: a fresh in-memory database per app instance."""

    TESTING = True
    SECRET_KEY = "test-insecure-key"
    SQLALCHEMY_DATABASE_URI = "sqlite://"
    WTF_CSRF_ENABLED = False


class ProductionConfig(Config):
    """Production: SECRET_KEY and DATABASE_URL must come from the environment."""


CONFIGS: dict[str, type[Config]] = {
    "development": DevelopmentConfig,
    "testing": TestingConfig,
    "production": ProductionConfig,
}


def env_overrides() -> dict[str, str]:
    """Return config values set through environment variables, ignoring blanks."""
    overrides: dict[str, str] = {}
    if secret_key := os.environ.get("SECRET_KEY", "").strip():
        overrides["SECRET_KEY"] = secret_key
    if database_url := os.environ.get("DATABASE_URL", "").strip():
        overrides["SQLALCHEMY_DATABASE_URI"] = database_url
    return overrides
