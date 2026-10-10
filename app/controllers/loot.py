from flask import Blueprint, abort, flash, g, redirect, render_template, request, url_for

from ..models import Currency, Item, Loot, RuleError
from ..models.item import CATEGORIES, RARITIES
from ..models.loot import KINDS
from .helpers import (
    ListArgs, acting_character, campaign_required, dm_required, form_int, get_character_or_404,
    in_campaign_or_404, is_dm, redirect_back,
)

bp = Blueprint("loot", __name__, url_prefix="/loot")


def _get_pool(pool_id):
    pool = in_campaign_or_404(Loot.get(pool_id))
    if not pool["active"] and not is_dm():
        abort(404)
    return pool


@bp.route("/")
@campaign_required
def index():
    args = ListArgs(Loot.SORTS, "recent", filters=["kind"])
    pools = Loot.all(g.campaign["id"], active_only=not is_dm(), q=args.q, kind=args.kind, sort=args.sort)
    return render_template("loot/index.html", pools=pools, args=args, kinds=KINDS)


@bp.route("/new", methods=["POST"])
@dm_required
@campaign_required
def new():
    try:
        pool_id = Loot.create(request.form.get("name"), request.form.get("description"),
                              request.form.get("kind"), g.campaign["id"])
    except RuleError as e:
        flash(str(e), "error")
        return redirect(url_for("loot.index"))
    return redirect(url_for("loot.show", pool_id=pool_id))


@bp.route("/<int:pool_id>")
@campaign_required
def show(pool_id):
    pool = _get_pool(pool_id)
    args = ListArgs(Loot.ENTRY_SORTS, "type")
    acting = acting_character()
    return render_template(
        "loot/show.html",
        pool=pool,
        kinds=KINDS,
        args=args,
        entries=Loot.entries(pool_id, sort=args.sort),
        acting=acting,
        balance=Currency.balances(acting["id"]) if acting else [],
        categories=CATEGORIES,
        rarities=RARITIES,
        currencies=Currency.all() if is_dm() else [],
    )


@bp.route("/<int:pool_id>/claim/<int:entry_id>", methods=["POST"])
@campaign_required
def claim(pool_id, entry_id):
    _get_pool(pool_id)
    character = get_character_or_404(form_int("character_id")) if is_dm() else g.character
    qty = form_int("quantity", 1)
    try:
        label = Loot.claim(entry_id, character["id"], qty)
    except RuleError as e:
        flash(str(e), "error")
    else:
        flash(f"{character['name']} recoge {qty}× {label}.", "ok")
    return redirect_back(url_for("loot.show", pool_id=pool_id, **{"as": character["id"]}))


# --- Gestión (DM) -------------------------------------------------------------------

@bp.route("/<int:pool_id>/toggle", methods=["POST"])
@dm_required
@campaign_required
def toggle(pool_id):
    Loot.toggle(pool_id)
    return redirect_back(url_for("loot.show", pool_id=pool_id))


@bp.route("/<int:pool_id>/delete", methods=["POST"])
@dm_required
@campaign_required
def delete(pool_id):
    Loot.delete(pool_id)
    flash("Botín eliminado.", "ok")
    return redirect(url_for("loot.index"))


@bp.route("/<int:pool_id>/entries", methods=["POST"])
@dm_required
@campaign_required
def add_entry(pool_id):
    """Añade un objeto (item_id) o monedas (currency_id) al botín."""
    _get_pool(pool_id)
    item_id, currency_id = form_int("item_id"), form_int("currency_id")
    try:
        if item_id and not Item.get(item_id):
            raise RuleError("Ese objeto no existe.")
        if currency_id and not Currency.get(currency_id):
            raise RuleError("Esa divisa no existe.")
        Loot.add_entry(
            pool_id, item_id=item_id or None, currency_id=currency_id or None,
            quantity=form_int("quantity", 1),
        )
    except RuleError as e:
        flash(str(e), "error")
    return redirect_back(url_for("loot.show", pool_id=pool_id))


@bp.route("/<int:pool_id>/entries/<int:entry_id>/delete", methods=["POST"])
@dm_required
@campaign_required
def remove_entry(pool_id, entry_id):
    Loot.remove_entry(entry_id)
    return redirect_back(url_for("loot.show", pool_id=pool_id))
