"""Protección CSRF: impide que otra web envíe formularios en nombre de un usuario con sesión.

Cada sesión tiene un token secreto; todo POST debe incluirlo (campo csrf_token o
cabecera X-CSRF-Token). base.html lo añade automáticamente a todos los formularios.
"""
import hmac
import secrets

from flask import abort, request, session


def csrf_token():
    if "_csrf" not in session:
        session["_csrf"] = secrets.token_urlsafe(32)
    return session["_csrf"]


def init_app(app):
    app.jinja_env.globals["csrf_token"] = csrf_token

    @app.before_request
    def check_csrf():
        if request.method != "POST" or not app.config["CSRF_ENABLED"]:
            return
        expected = session.get("_csrf")
        sent = request.form.get("csrf_token") or request.headers.get("X-CSRF-Token")
        if not expected or not sent or not hmac.compare_digest(expected, sent):
            abort(400, "La sesión ha caducado o el formulario no es válido. Recarga la página.")
