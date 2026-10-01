"""Flask extension instances, created unbound and initialised in the app factory."""

from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy
from flask_wtf.csrf import CSRFProtect
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Declarative base class for all models."""


db = SQLAlchemy(model_class=Base)
migrate = Migrate()
csrf = CSRFProtect()
