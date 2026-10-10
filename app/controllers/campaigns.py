"""Campañas: menú del DM, elección de personaje del jugador y contexto de cada petición.

En cada petición se fija:
  g.character  personaje con el que juega el jugador (None para el DM)
  g.campaign   campaña activa: la del personaje, o la que el DM ha elegido
Tiendas, botines e intercambios solo muestran lo de g.campaign.
"""
from flask import Blueprint, abort, flash, g, redirect, render_template, request, session, url_for

from ..models import Campaign, Character, RuleError
from .helpers import dm_required, is_dm, login_required, redirect_back

bp = Blueprint("campaigns", __name__)


@bp.before_app_request
def load_campaign_context():
    g.character = None
    g.campaign = None
    if g.get("user") is None:
        return
    if is_dm():
        # La de esta sesión, o la última que usó, o la primera que haya
        campaign_id = session.get("campaign_id") or g.user["last_campaign_id"]
        campaign = Campaign.get(campaign_id) if campaign_id else None
        if campaign is None:
            campaign = Campaign.first_active()
        if campaign:
            session["campaign_id"] = campaign["id"]
        else:
            session.pop("campaign_id", None)
        g.campaign = campaign
        return

    character_id = session.get("character_id")
    character = Character.get(character_id) if character_id else None
    if character is None or character["user_id"] != g.user["id"]:
        session.pop("character_id", None)
        playable = [c for c in Character.for_user(g.user["id"]) if not c["campaign_archived"]]
        character = playable[0] if len(playable) == 1 else None  # si solo tiene uno, se elige solo
        if character:
            session["character_id"] = character["id"]
    if character:
        g.character = character
        g.campaign = Campaign.get(character["campaign_id"])


def _safe_next(default):
    target = request.values.get("next", "")
    return target if target.startswith("/") and not target.startswith("//") else default


# --- Jugador: elegir personaje ---------------------------------------------------------

@bp.route("/play")
@login_required
def play():
    if is_dm():
        return redirect(url_for("campaigns.index"))
    return render_template("campaigns/play.html", characters=Character.for_user(g.user["id"]),
                           next=request.args.get("next", ""))


@bp.route("/play/<int:character_id>", methods=["POST"])
@login_required
def choose(character_id):
    character = Character.get(character_id)
    if character is None or character["user_id"] != g.user["id"]:
        abort(404)
    if character["campaign_archived"]:
        flash(f"La campaña «{character['campaign_name']}» está archivada.", "error")
        return redirect(url_for("campaigns.play"))
    session["character_id"] = character["id"]
    flash(f"Juegas con {character['name']} en «{character['campaign_name']}».", "ok")
    return redirect(_safe_next(url_for("characters.show", character_id=character["id"])))


@bp.route("/campaigns/join", methods=["POST"])
@login_required
def join():
    """El jugador entra en una campaña con su código y pasa a crear su personaje en ella."""
    if is_dm():
        return redirect(url_for("campaigns.index"))
    try:
        campaign, already = Campaign.join(g.user["id"], request.form.get("code"))
    except RuleError as e:
        flash(str(e), "error")
        return redirect_back(url_for("characters.new"))
    if already:
        flash(f"Ya estabas en «{campaign['name']}».", "ok")
    else:
        flash(f"¡Te has unido a «{campaign['name']}»! Ya puedes crear tu personaje en ella.", "ok")
    return redirect(url_for("characters.new", campaign_id=campaign["id"]))


# --- DM: menú de campañas ------------------------------------------------------------------

@bp.route("/campaigns", methods=["GET", "POST"])
@dm_required
def index():
    if request.method == "POST":
        try:
            campaign_id = Campaign.create(request.form)
        except RuleError as e:
            flash(str(e), "error")
        else:
            _activate(campaign_id)
            flash("Campaña creada. Ahora es tu campaña activa.", "ok")
            return redirect(url_for("campaigns.index"))
    campaigns = Campaign.all()
    return render_template("campaigns/index.html", campaigns=campaigns,
                           members={cp["id"]: Campaign.members(cp["id"]) for cp in campaigns})


def _activate(campaign_id):
    session["campaign_id"] = campaign_id
    Campaign.remember_for(g.user["id"], campaign_id)


def _campaign_or_404(campaign_id):
    campaign = Campaign.get(campaign_id)
    if campaign is None:
        abort(404)
    return campaign


@bp.route("/campaigns/<int:campaign_id>/edit", methods=["POST"])
@dm_required
def edit(campaign_id):
    _campaign_or_404(campaign_id)
    try:
        Campaign.update(campaign_id, request.form)
    except RuleError as e:
        flash(str(e), "error")
    else:
        flash("Campaña actualizada.", "ok")
    return redirect(url_for("campaigns.index"))


@bp.route("/campaigns/<int:campaign_id>/activate", methods=["POST"])
@dm_required
def activate(campaign_id):
    campaign = _campaign_or_404(campaign_id)
    _activate(campaign["id"])
    flash(f"Campaña activa: «{campaign['name']}».", "ok")
    return redirect(_safe_next(url_for("dm.index")))


@bp.route("/campaigns/<int:campaign_id>/toggle/<any(is_open, archived):column>", methods=["POST"])
@dm_required
def toggle(campaign_id, column):
    _campaign_or_404(campaign_id)
    Campaign.toggle(campaign_id, column)
    return redirect_back(url_for("campaigns.index"))


@bp.route("/campaigns/<int:campaign_id>/code", methods=["POST"])
@dm_required
def regenerate_code(campaign_id):
    campaign = _campaign_or_404(campaign_id)
    Campaign.regenerate_code(campaign_id)
    flash(f"Nuevo código para «{campaign['name']}». El anterior ya no sirve.", "ok")
    return redirect(url_for("campaigns.index"))


@bp.route("/campaigns/<int:campaign_id>/delete", methods=["POST"])
@dm_required
def delete(campaign_id):
    campaign = _campaign_or_404(campaign_id)
    try:
        Campaign.delete(campaign_id)
    except RuleError as e:
        flash(str(e), "error")
    else:
        if session.get("campaign_id") == campaign_id:
            session.pop("campaign_id", None)
        flash(f"Campaña «{campaign['name']}» eliminada.", "ok")
    return redirect(url_for("campaigns.index"))
