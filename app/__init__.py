"""BacknPack: gestor de personajes e inventario para D&D 5e."""
import os
from datetime import timedelta

from flask import Flask

DEV_SECRET = "dev-cambia-esta-clave"


def create_app(test_config=None):
    app = Flask(__name__, template_folder="views", instance_relative_config=True)
    os.makedirs(app.instance_path, exist_ok=True)

    # Render define RENDER=true; en otro hosting usa BACKNPACK_ENV=production
    production = os.environ.get("RENDER") == "true" or os.environ.get("BACKNPACK_ENV") == "production"
    app.config.from_mapping(
        PRODUCTION=production,
        SECRET_KEY=os.environ.get("BACKNPACK_SECRET", DEV_SECRET),
        # DATABASE_URL (PostgreSQL de Neon) o, si no existe, SQLite local
        DATABASE=os.environ.get("DATABASE_URL") or os.path.join(app.instance_path, "backnpack.sqlite"),
        DM_PASSWORD=os.environ.get("DM_PASSWORD"),
        INVITE_CODE=os.environ.get("INVITE_CODE"),
        CSRF_ENABLED=True,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=production,
        PERMANENT_SESSION_LIFETIME=timedelta(days=30),
    )
    if test_config:
        app.config.update(test_config)
    if app.config["PRODUCTION"] and app.config["SECRET_KEY"] == DEV_SECRET:
        raise RuntimeError("En producción define la variable de entorno BACKNPACK_SECRET.")

    from . import db
    db.init_app(app)

    from . import security
    security.init_app(app)

    from .controllers import register_controllers
    register_controllers(app)

    @app.template_filter("mod")
    def ability_modifier(score):
        return f"{(int(score) - 10) // 2:+d}"

    @app.template_global()
    def field(obj, key, default=""):
        """Lee obj[key] tolerando None/claves ausentes (útil en formularios de alta/edición)."""
        try:
            value = obj[key]
        except (KeyError, IndexError, TypeError):
            return default
        return default if value is None else value

    return app
