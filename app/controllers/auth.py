import hmac

from flask import (
    Blueprint, current_app, flash, g, redirect, render_template, request, session, url_for,
)

from ..models import RuleError, User
from .helpers import login_required

bp = Blueprint("auth", __name__)


@bp.before_app_request
def load_logged_in_user():
    user_id = session.get("user_id")
    g.user = User.get(user_id) if user_id else None


def _start_session(user_id):
    session.clear()
    session.permanent = True  # recordar la sesión 30 días
    session["user_id"] = user_id


def registration_mode():
    """'open' (local sin código), 'invite' (pide código) o 'closed' (producción sin código)."""
    if current_app.config.get("INVITE_CODE"):
        return "invite"
    return "closed" if current_app.config["PRODUCTION"] else "open"


@bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        user = User.authenticate(request.form.get("username"), request.form.get("password"))
        if user is None:
            flash("Usuario o contraseña incorrectos.", "error")
        else:
            _start_session(user["id"])
            next_url = request.args.get("next", "")
            safe = next_url.startswith("/") and not next_url.startswith("//")
            return redirect(next_url if safe else url_for("main.index"))
    return render_template("auth/login.html", registration=registration_mode())


@bp.route("/register", methods=["GET", "POST"])
def register():
    mode = registration_mode()
    if request.method == "POST" and mode != "closed":
        code = current_app.config.get("INVITE_CODE") or ""
        sent = request.form.get("invite", "").strip()
        try:
            if mode == "invite" and not hmac.compare_digest(sent.encode(), code.encode()):
                raise RuleError("El código de invitación no es correcto. Pídeselo a tu DM.")
            user_id = User.create(request.form.get("username"), request.form.get("password"))
        except RuleError as e:
            flash(str(e), "error")
        else:
            _start_session(user_id)
            flash("¡Bienvenido, aventurero! Crea tu primer personaje.", "ok")
            return redirect(url_for("characters.new"))
    return render_template("auth/register.html", registration=mode)


@bp.route("/account", methods=["GET", "POST"])
@login_required
def account():
    if request.method == "POST":
        try:
            User.change_password(
                g.user["id"], request.form.get("current"), request.form.get("new"), request.form.get("repeat"),
            )
        except RuleError as e:
            flash(str(e), "error")
        else:
            flash("Contraseña cambiada.", "ok")
            return redirect(url_for("main.index"))
    return render_template("auth/account.html")


@bp.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("auth.login"))
