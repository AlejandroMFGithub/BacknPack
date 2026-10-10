"""BacknPack: gestor de personajes e inventario para D&D 5e."""
import os
from datetime import timedelta

from flask import Flask, flash, request, url_for
from werkzeug.exceptions import RequestEntityTooLarge

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
        # Peticiones de más de 9 MB se rechazan (imágenes de hasta 8 MB + margen del formulario)
        MAX_CONTENT_LENGTH=9 * 1024 * 1024,
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
    from .controllers.helpers import redirect_back
    register_controllers(app)

    @app.errorhandler(RequestEntityTooLarge)
    def too_large(e):
        flash("El archivo es demasiado grande (máximo 8 MB).", "error")
        return redirect_back(url_for("main.index"))

    from .models.avatar import color_for, initial
    from .models.campaign import format_code
    app.jinja_env.globals.update(avatar_color=color_for, avatar_initial=initial, format_code=format_code)

    @app.template_filter("mod")
    def ability_modifier(score):
        return f"{(int(score) - 10) // 2:+d}"

    @app.template_global()
    def asset(filename):
        """URL de un archivo estático con su fecha de modificación: tras cada despliegue
        el navegador descarga la versión nueva en vez de usar la de su caché."""
        try:
            version = int(os.path.getmtime(os.path.join(app.static_folder, filename)))
        except OSError:
            version = 0
        return url_for("static", filename=filename, v=version)

    @app.template_global()
    def url_with(**changes):
        """URL de la página actual cambiando algunos parámetros (p. ej. page=2)."""
        args = request.args.to_dict()
        args.update(changes)
        args = {k: v for k, v in args.items() if v not in (None, "")}
        return url_for(request.endpoint, **(request.view_args or {}), **args)

    @app.template_global()
    def field(obj, key, default=""):
        """Lee obj[key] tolerando None/claves ausentes (útil en formularios de alta/edición)."""
        try:
            value = obj[key]
        except (KeyError, IndexError, TypeError):
            return default
        return default if value is None else value

    return app
