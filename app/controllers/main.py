from flask import Blueprint, g, redirect, url_for

from ..models import Character
from .helpers import is_dm, login_required

bp = Blueprint("main", __name__)


@bp.route("/")
@login_required
def index():
    """Inicio: el DM va a su panel; el jugador, a la ficha del personaje con el que juega."""
    if is_dm():
        return redirect(url_for("dm.index") if g.campaign else url_for("campaigns.index"))
    if g.character:
        return redirect(url_for("characters.show", character_id=g.character["id"]))
    if Character.for_user(g.user["id"]):
        return redirect(url_for("campaigns.play"))
    return redirect(url_for("characters.new"))
