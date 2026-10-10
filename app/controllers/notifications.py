"""Avisos de intercambios: campana de la barra superior, aviso emergente y consulta periódica.

El jugador recibe los avisos del personaje con el que juega:
  incoming  propuestas que le han hecho y esperan su respuesta
  outgoing  propuestas suyas que esperan la respuesta del otro
  unseen    de las recibidas, las que aún no ha visto (para el aviso emergente)
El DM solo ve el número de intercambios pendientes de su campaña.
"""
from flask import Blueprint, g, jsonify, render_template

from ..models import Trade
from .helpers import is_dm, login_required

bp = Blueprint("notifications", __name__, url_prefix="/notifications")


def trade_alerts():
    """Avisos del usuario actual (se calculan una sola vez por petición)."""
    if "trade_alerts" not in g:
        g.trade_alerts = _compute_alerts()
    return g.trade_alerts


def _compute_alerts():
    if g.get("user") is None:
        return None
    if is_dm():
        return {"dm_pending": Trade.pending_count(g.campaign["id"]) if g.get("campaign") else 0}
    if g.get("character") is None:
        return None
    incoming, outgoing = Trade.pending_for(g.character["id"])
    return {
        "incoming": incoming,
        "outgoing": outgoing,
        "unseen": [t for t in incoming if not t["seen_at"]],
        "lines": Trade.lines_for([t["id"] for t in incoming + outgoing]),
    }


@bp.route("/state")
@login_required
def state():
    """Lo consulta la página cada ~30 s para actualizar la campana sin recargar."""
    alerts = trade_alerts() or {}
    if "incoming" not in alerts:
        return jsonify(incoming=0, outgoing=0, unseen=[], dm_pending=alerts.get("dm_pending", 0))
    return jsonify(
        incoming=len(alerts["incoming"]),
        outgoing=len(alerts["outgoing"]),
        unseen=[{"id": t["id"], "from": t["from_name"]} for t in alerts["unseen"]],
        panel=render_template("notifications/_panel.html", alerts=alerts),
    )


@bp.route("/seen", methods=["POST"])
@login_required
def seen():
    """Cerrar el aviso emergente: las propuestas recibidas quedan como vistas."""
    if g.get("character") is not None:
        Trade.mark_seen(g.character["id"])
    return ("", 204)
