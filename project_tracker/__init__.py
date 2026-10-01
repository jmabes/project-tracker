"""project-tracker: a self-hosted personal project tracker."""

import os
from collections.abc import Mapping
from typing import Any

from flask import Flask

from project_tracker.config import CONFIG_ENV_VAR, CONFIGS, env_overrides
from project_tracker.extensions import csrf, db, migrate, register_sql_functions


def create_app(
    config_name: str | None = None, overrides: Mapping[str, Any] | None = None
) -> Flask:
    """Create and configure the Flask application.

    Args:
        config_name: One of ``development``, ``testing`` or ``production``. Defaults
            to the ``PROJECT_TRACKER_CONFIG`` environment variable, then
            ``development``.
        overrides: Extra config values applied last (used by tests).

    Raises:
        ValueError: If ``config_name`` is not a known configuration.
        RuntimeError: If production is missing ``SECRET_KEY`` or ``DATABASE_URL``.
    """
    name = config_name or os.environ.get(CONFIG_ENV_VAR, "").strip() or "development"
    if name not in CONFIGS:
        raise ValueError(
            f"Unknown config {name!r}; expected one of: {', '.join(CONFIGS)}"
        )

    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object(CONFIGS[name])
    if name != "testing":
        app.config.from_mapping(env_overrides())
    if overrides:
        app.config.from_mapping(overrides)

    if name == "production":
        _require(app, "SECRET_KEY", env_var="SECRET_KEY")
        _require(app, "SQLALCHEMY_DATABASE_URI", env_var="DATABASE_URL")
    if name == "development":
        # The default development database lives in the instance folder.
        os.makedirs(app.instance_path, exist_ok=True)

    db.init_app(app)
    with app.app_context():
        register_sql_functions(db.engine)
    migrate.init_app(app, db)
    csrf.init_app(app)

    from project_tracker import health, projects
    from project_tracker.importer import views as imports

    app.register_blueprint(health.bp)
    app.register_blueprint(projects.bp)
    app.register_blueprint(imports.bp)
    # App-wide: the size check can fire before any view runs (e.g. during CSRF).
    app.register_error_handler(413, imports.request_entity_too_large)

    # Import models so Flask-Migrate sees them in the metadata.
    from project_tracker import models  # noqa: F401

    return app


def _require(app: Flask, key: str, *, env_var: str) -> None:
    """Raise RuntimeError if a config value is missing or blank."""
    if not app.config.get(key):
        raise RuntimeError(f"{env_var} must be set in production")
