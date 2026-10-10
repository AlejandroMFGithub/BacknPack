from flask import Blueprint, redirect, url_for

from .helpers import is_dm, login_required

bp = Blueprint("main", __name__)


@bp.route("/")
@login_required
def index():
    return redirect(url_for("dm.index" if is_dm() else "characters.index"))
