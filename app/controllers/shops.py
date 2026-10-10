from flask import Blueprint, abort, flash, redirect, render_template, request, url_for

from ..models import Currency, Item, ItemTrait, RuleError, Shop
from ..models.item import CATEGORIES, RARITIES
from ..models.item_trait import KINDS as TRAIT_KINDS
from .helpers import (
    ListArgs, acting_character, dm_required, form_int, get_character_or_404, is_dm, login_required,
    my_characters, redirect_back,
)

bp = Blueprint("shops", __name__, url_prefix="/shops")


def _get_shop(shop_id):
    shop = Shop.get(shop_id)
    if shop is None or (not shop["active"] and not is_dm()):
        abort(404)
    return shop


@bp.route("/")
@login_required
def index():
    args = ListArgs(Shop.SORTS, "name")
    shops = Shop.all(active_only=not is_dm(), q=args.q, sort=args.sort)
    return render_template("shops/index.html", shops=shops, args=args)


@bp.route("/new", methods=["POST"])
@dm_required
def new():
    try:
        shop_id = Shop.create(
            request.form.get("name"), request.form.get("description"),
            bool(request.form.get("allow_exchange")),
        )
    except RuleError as e:
        flash(str(e), "error")
        return redirect(url_for("shops.index"))
    return redirect(url_for("shops.show", shop_id=shop_id))


@bp.route("/<int:shop_id>")
@login_required
def show(shop_id):
    shop = _get_shop(shop_id)
    args = ListArgs(Shop.LISTING_SORTS, "category", filters=["category"])
    listings = Shop.listings(shop_id, q=args.q, category=args.category, sort=args.sort)
    acting = acting_character()
    return render_template(
        "shops/show.html",
        shop=shop,
        listings=listings,
        args=args,
        categories=CATEGORIES,
        rarities=RARITIES,
        traits=ItemTrait.for_items({l["item_id"] for l in listings}, include_hidden=is_dm()),
        trait_kinds=TRAIT_KINDS,
        currencies=Currency.all(),
        acting=acting,
        own_characters=[] if is_dm() else my_characters(),
        balance=Currency.balances(acting["id"]) if acting else [],
    )


@bp.route("/<int:shop_id>/buy/<int:listing_id>", methods=["POST"])
@login_required
def buy(shop_id, listing_id):
    _get_shop(shop_id)
    character = get_character_or_404(form_int("character_id"))
    listing = Shop.get_listing(listing_id)
    if listing is None or listing["shop_id"] != shop_id:
        abort(404)
    try:
        cost, pay = Shop.buy(listing_id, character["id"], form_int("quantity", 1), form_int("currency_id"))
    except RuleError as e:
        flash(str(e), "error")
    else:
        flash(f"{character['name']} compra {listing['name']} por {cost} {pay['code']}.", "ok")
    return redirect_back(url_for("shops.show", shop_id=shop_id, **{"as": character["id"]}))


# --- Gestión (DM) ----------------------------------------------------------------------

@bp.route("/<int:shop_id>/toggle/<column>", methods=["POST"])
@dm_required
def toggle(shop_id, column):
    if column not in ("active", "allow_exchange"):
        abort(400)
    Shop.toggle(shop_id, column)
    return redirect_back(url_for("shops.show", shop_id=shop_id))


@bp.route("/<int:shop_id>/delete", methods=["POST"])
@dm_required
def delete(shop_id):
    Shop.delete(shop_id)
    flash("Tienda eliminada.", "ok")
    return redirect(url_for("shops.index"))


@bp.route("/<int:shop_id>/listings", methods=["POST"])
@dm_required
def add_listing(shop_id):
    _get_shop(shop_id)
    stock = request.form.get("stock", "").strip()
    try:
        if not Item.get(form_int("item_id")) or not Currency.get(form_int("currency_id")):
            raise RuleError("Elige objeto y divisa.")
        Shop.add_listing(
            shop_id, form_int("item_id"), form_int("price", 0), form_int("currency_id"),
            int(stock) if stock.isdigit() else None,
        )
    except RuleError as e:
        flash(str(e), "error")
    return redirect_back(url_for("shops.show", shop_id=shop_id))


@bp.route("/<int:shop_id>/listings/<int:listing_id>/delete", methods=["POST"])
@dm_required
def remove_listing(shop_id, listing_id):
    Shop.remove_listing(listing_id)
    return redirect_back(url_for("shops.show", shop_id=shop_id))
