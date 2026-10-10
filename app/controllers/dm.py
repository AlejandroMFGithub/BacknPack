from flask import Blueprint, abort, flash, redirect, render_template, request, url_for

from ..models import ActivityLog, Character, Condition, Currency, Item, ItemTrait, RuleError, Trade
from ..models.item import CATEGORIES, RARITIES
from ..models.item_trait import KINDS as TRAIT_KINDS
from .helpers import ListArgs, dm_required, form_int, redirect_back

bp = Blueprint("dm", __name__, url_prefix="/dm")


@bp.route("/")
@dm_required
def index():
    args = ListArgs(Character.SORTS, "name")
    characters = Character.search(args.q, sort=args.sort, page=args.page)
    effects = {c["id"]: Condition.for_character(c["id"], include_hidden=True) for c in characters}
    return render_template(
        "dm/index.html",
        characters=characters,
        args=args,
        effects=effects,
        pending_trades=Trade.pending_count(),
        log=ActivityLog.recent(),
    )


# --- Catálogo de objetos -------------------------------------------------------------

@bp.route("/items", methods=["GET", "POST"])
@dm_required
def items():
    if request.method == "POST":
        try:
            Item.create(request.form)
        except RuleError as e:
            flash(str(e), "error")
        else:
            flash("Objeto añadido al catálogo.", "ok")
        return redirect_back(url_for("dm.items"))
    args = ListArgs(Item.SORTS, "name", filters=["category", "rarity"])
    items = Item.search(args.q, args.category, args.rarity, sort=args.sort, page=args.page)
    return render_template(
        "dm/items.html", items=items, args=args, item=None, categories=CATEGORIES, rarities=RARITIES,
        traits=ItemTrait.for_items([i["id"] for i in items]), trait_kinds=TRAIT_KINDS,
    )


@bp.route("/items/<int:item_id>/edit", methods=["GET", "POST"])
@dm_required
def edit_item(item_id):
    item = Item.get(item_id) or abort(404)
    if request.method == "POST":
        try:
            Item.update(item_id, request.form)
        except RuleError as e:
            flash(str(e), "error")
        else:
            flash("Objeto actualizado.", "ok")
            return redirect(url_for("dm.items"))
    return render_template(
        "dm/item_form.html", item=item, categories=CATEGORIES, rarities=RARITIES,
        traits=ItemTrait.for_items([item_id])[item_id], trait_kinds=TRAIT_KINDS,
    )


@bp.route("/items/<int:item_id>/delete", methods=["POST"])
@dm_required
def delete_item(item_id):
    Item.delete(item_id)
    flash("Objeto eliminado del catálogo (y de todos los inventarios y tiendas).", "ok")
    return redirect_back(url_for("dm.items"))


# --- Cualidades de plantilla (se copian a cada ejemplar nuevo) ------------------------

def _template_trait(item_id, trait_id):
    trait = ItemTrait.get(trait_id)
    if trait is None or trait["item_id"] != item_id:
        abort(404)
    return trait


@bp.route("/items/<int:item_id>/traits", methods=["POST"])
@dm_required
def add_item_trait(item_id):
    Item.get(item_id) or abort(404)
    try:
        ItemTrait.create(request.form, item_id=item_id)
    except RuleError as e:
        flash(str(e), "error")
    return redirect(url_for("dm.edit_item", item_id=item_id))


@bp.route("/items/<int:item_id>/traits/<int:trait_id>/visibility", methods=["POST"])
@dm_required
def toggle_item_trait_visibility(item_id, trait_id):
    _template_trait(item_id, trait_id)
    ItemTrait.toggle_visible(trait_id)
    return redirect(url_for("dm.edit_item", item_id=item_id))


@bp.route("/items/<int:item_id>/traits/<int:trait_id>/delete", methods=["POST"])
@dm_required
def delete_item_trait(item_id, trait_id):
    _template_trait(item_id, trait_id)
    ItemTrait.delete(trait_id)
    return redirect(url_for("dm.edit_item", item_id=item_id))


# --- Divisas -----------------------------------------------------------------------------

@bp.route("/currencies", methods=["GET", "POST"])
@dm_required
def currencies():
    if request.method == "POST":
        try:
            Currency.create(request.form.get("code"), request.form.get("name"), form_int("value_cp", 0))
        except RuleError as e:
            flash(str(e), "error")
        else:
            flash("Divisa creada.", "ok")
        return redirect(url_for("dm.currencies"))
    return render_template("dm/currencies.html", currencies=Currency.all())


@bp.route("/currencies/<int:currency_id>", methods=["POST"])
@dm_required
def update_currency(currency_id):
    try:
        Currency.update(currency_id, request.form.get("name"), form_int("value_cp", 0))
    except RuleError as e:
        flash(str(e), "error")
    return redirect(url_for("dm.currencies"))


@bp.route("/currencies/<int:currency_id>/delete", methods=["POST"])
@dm_required
def delete_currency(currency_id):
    Currency.delete(currency_id)
    flash("Divisa eliminada.", "ok")
    return redirect(url_for("dm.currencies"))
