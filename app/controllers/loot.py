from flask import Blueprint, abort, flash, redirect, render_template, request, url_for

from ..models import Currency, Item, Loot, RuleError
from ..models.loot import KINDS
from .helpers import dm_required, form_int, get_character_or_404, is_dm, login_required, my_characters

bp = Blueprint("loot", __name__, url_prefix="/loot")


def _get_pool(pool_id):
    pool = Loot.get(pool_id)
    if pool is None or (not pool["active"] and not is_dm()):
        abort(404)
    return pool


@bp.route("/")
@login_required
def index():
    return render_template("loot/index.html", pools=Loot.all(active_only=not is_dm()), kinds=KINDS)


@bp.route("/new", methods=["POST"])
@dm_required
def new():
    try:
        pool_id = Loot.create(request.form.get("name"), request.form.get("description"), request.form.get("kind"))
    except RuleError as e:
        flash(str(e), "error")
        return redirect(url_for("loot.index"))
    return redirect(url_for("loot.show", pool_id=pool_id))


@bp.route("/<int:pool_id>")
@login_required
def show(pool_id):
    pool = _get_pool(pool_id)
    return render_template(
        "loot/show.html",
        pool=pool,
        kinds=KINDS,
        entries=Loot.entries(pool_id),
        characters=my_characters(),
        catalog=Item.all() if is_dm() else [],
        currencies=Currency.all() if is_dm() else [],
    )


@bp.route("/<int:pool_id>/claim/<int:entry_id>", methods=["POST"])
@login_required
def claim(pool_id, entry_id):
    _get_pool(pool_id)
    character = get_character_or_404(form_int("character_id"))
    qty = form_int("quantity", 1)
    try:
        label = Loot.claim(entry_id, character["id"], qty)
    except RuleError as e:
        flash(str(e), "error")
    else:
        flash(f"{character['name']} recoge {qty}× {label}.", "ok")
    return redirect(url_for("loot.show", pool_id=pool_id))


# --- Gestión (DM) -------------------------------------------------------------------

@bp.route("/<int:pool_id>/toggle", methods=["POST"])
@dm_required
def toggle(pool_id):
    Loot.toggle(pool_id)
    return redirect(url_for("loot.show", pool_id=pool_id))


@bp.route("/<int:pool_id>/delete", methods=["POST"])
@dm_required
def delete(pool_id):
    Loot.delete(pool_id)
    flash("Botín eliminado.", "ok")
    return redirect(url_for("loot.index"))


@bp.route("/<int:pool_id>/entries", methods=["POST"])
@dm_required
def add_entry(pool_id):
    _get_pool(pool_id)
    ref = request.form.get("ref", "")  # "item:3" o "currency:2"
    kind, _, ref_id = ref.partition(":")
    try:
        if not ref_id.isdigit() or kind not in ("item", "currency"):
            raise RuleError("Elige un objeto o una divisa.")
        Loot.add_entry(
            pool_id,
            item_id=int(ref_id) if kind == "item" else None,
            currency_id=int(ref_id) if kind == "currency" else None,
            quantity=form_int("quantity", 1),
        )
    except RuleError as e:
        flash(str(e), "error")
    return redirect(url_for("loot.show", pool_id=pool_id))


@bp.route("/<int:pool_id>/entries/<int:entry_id>/delete", methods=["POST"])
@dm_required
def remove_entry(pool_id, entry_id):
    Loot.remove_entry(entry_id)
    return redirect(url_for("loot.show", pool_id=pool_id))
