"""Endpoints JSON para los buscadores desplegables.

Devuelven páginas pequeñas (20 resultados) para que la página no tenga que cargar
el catálogo entero: {"results": [{id, label, sub}], "has_more": bool, "total": n}
"""
from flask import Blueprint, g, jsonify, request, url_for

from ..models import Character, Item, User
from ..models.avatar import color_for, initial
from .helpers import dm_required, is_dm, login_required

bp = Blueprint("api", __name__, url_prefix="/api")
PAGE_SIZE = 20


def _respond(page, to_result):
    return jsonify(
        results=[to_result(row) for row in page.rows], has_more=page.has_next, total=page.total,
    )


def _args():
    q = request.args.get("q", "").strip()
    return q, max(1, request.args.get("page", 1, type=int)), ("relevance" if q else "name")


@bp.route("/items")
@dm_required
def items():
    q, page, sort = _args()
    found = Item.search(
        q, request.args.get("category", ""), request.args.get("rarity", ""),
        sort=sort, page=page, per_page=PAGE_SIZE,
    )
    return _respond(found, lambda r: {
        "id": r["id"], "label": r["name"],
        "sub": f"{r['category']} · {r['rarity']}" + (f" · {r['properties']}" if r["properties"] else ""),
    })


@bp.route("/characters")
@login_required
def characters():
    """Personajes de la campaña activa. ?mine=1 limita a los del jugador (el DM los ve todos)."""
    q, page, sort = _args()
    if g.campaign is None:  # sin campaña activa no hay a quién buscar
        return jsonify(results=[], has_more=False, total=0)
    mine = request.args.get("mine") == "1" and not is_dm()
    found = Character.search(
        q, user_id=g.user["id"] if mine else None,
        exclude_id=request.args.get("exclude", type=int),
        campaign_id=g.campaign["id"],  # solo personajes de la campaña activa
        sort=sort, page=page, per_page=PAGE_SIZE,
    )
    return _respond(found, lambda r: {
        "id": r["id"], "label": r["name"],
        "sub": f"{r['owner']} · {r['race'] or '¿?'} {r['class_name'] or ''} {r['level']}".strip(),
        "avatar": {
            "url": url_for("characters.avatar", character_id=r["id"], v=r["avatar_version"])
                   if r["avatar_version"] else None,
            "initial": initial(r["name"]),
            "color": color_for(r["id"]),
        },
    })


@bp.route("/users")
@dm_required
def users():
    q, page, _ = _args()
    found = User.search(q, page=page, per_page=PAGE_SIZE)
    return _respond(found, lambda r: {
        "id": r["id"], "label": r["username"], "sub": "DM" if r["role"] == "dm" else "Jugador",
    })
