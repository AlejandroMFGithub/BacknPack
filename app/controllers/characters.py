from flask import (
    Blueprint, abort, flash, g, make_response, redirect, render_template, request, session, url_for,
)

from ..db import transaction
from ..models import (
    ActivityLog, Avatar, Campaign, Character, Condition, Currency, Inventory, Item, ItemTrait, RuleError, User,
)
from ..models.character import ABILITIES
from ..models.condition import KINDS as CONDITION_KINDS, PRESETS
from ..models.item import CATEGORIES, RARITIES
from ..models.item_trait import KINDS as TRAIT_KINDS
from .helpers import ListArgs, dm_required, redirect_back, form_int, get_character_or_404, is_dm, login_required

bp = Blueprint("characters", __name__, url_prefix="/characters")


def _back(character_id):
    return redirect_back(url_for("characters.show", character_id=character_id))


def _own_inventory_row(character_id, inventory_id):
    row = Inventory.get(inventory_id)
    if row is None or row["character_id"] != character_id:
        abort(404)
    if not is_dm() and not row["visible"]:
        abort(404)
    return row


# --- Ficha -----------------------------------------------------------------------

@bp.route("/")
@login_required
def index():
    """DM: personajes de la campaña activa. Jugador: todos los suyos, de cualquier campaña."""
    args = ListArgs(Character.SORTS, "name")
    if is_dm():
        if g.campaign is None:
            return redirect(url_for("campaigns.index"))
        characters = Character.search(args.q, campaign_id=g.campaign["id"], sort=args.sort, page=args.page)
    else:
        characters = Character.search(args.q, user_id=g.user["id"], sort=args.sort, page=args.page)
    return render_template("characters/index.html", characters=characters, args=args)


@bp.route("/new", methods=["GET", "POST"])
@login_required
def new():
    if request.method == "POST":
        owner_id = g.user["id"]
        if is_dm() and form_int("user_id"):
            owner_id = form_int("user_id")
        try:
            if User.get(owner_id) is None:
                raise RuleError("Ese jugador no existe.")
            character_id = Character.create(
                owner_id, request.form, form_int("campaign_id"), for_player=not is_dm(),
            )
        except RuleError as e:
            flash(str(e), "error")
        else:
            if not is_dm():
                session["character_id"] = character_id  # el personaje nuevo pasa a ser el activo
            flash("Personaje creado.", "ok")
            return redirect(url_for("characters.show", character_id=character_id))
    # DM: cualquier campaña. Jugador: solo las suyas (a otras se entra con su código)
    campaigns = Campaign.all(include_archived=False) if is_dm() else Campaign.for_member(g.user["id"])
    selected = form_int("campaign_id") or request.args.get("campaign_id", type=int)
    if selected is None and g.campaign:
        selected = g.campaign["id"]
    return render_template(
        "characters/form.html", character=request.form or None, editing=False, abilities=ABILITIES,
        campaigns=campaigns, selected_campaign=selected,
    )


@bp.route("/<int:character_id>")
@login_required
def show(character_id):
    character = get_character_or_404(character_id)
    dm = is_dm()
    args = ListArgs(Inventory.SORTS, "equipped", filters=["category"])
    inventory = Inventory.for_character(
        character_id, include_hidden=dm, q=args.q, category=args.category, sort=args.sort,
    )
    return render_template(
        "characters/show.html",
        character=character,
        abilities=ABILITIES,
        inventory=inventory,
        inventory_total=Inventory.count(character_id, include_hidden=dm),
        args=args,
        categories=CATEGORIES,
        rarities=RARITIES,
        traits=ItemTrait.for_inventory([row["id"] for row in inventory], include_hidden=dm),
        trait_kinds=TRAIT_KINDS,
        weight=Inventory.total_weight(character_id, include_hidden=dm),
        balances=Currency.balances(character_id),
        conditions=Condition.for_character(character_id, include_hidden=dm),
        condition_kinds=CONDITION_KINDS,
        presets=PRESETS,
        log=ActivityLog.for_character(character_id),
    )


@bp.route("/<int:character_id>/edit", methods=["GET", "POST"])
@login_required
def edit(character_id):
    character = get_character_or_404(character_id)
    if request.method == "POST":
        try:
            moved = Character.update(
                character_id, request.form, campaign_id=form_int("campaign_id") if is_dm() else None,
            )
        except RuleError as e:
            flash(str(e), "error")
        else:
            flash("Ficha actualizada." + (" Ha cambiado de campaña; sus intercambios pendientes se han cancelado."
                                          if moved else ""), "ok")
            return redirect(url_for("characters.show", character_id=character_id))
    return render_template(
        "characters/form.html", character=character, editing=True, abilities=ABILITIES,
        campaigns=Campaign.all(include_archived=False) if is_dm() else [],
        selected_campaign=character["campaign_id"],
    )


@bp.route("/<int:character_id>/delete", methods=["POST"])
@login_required
def delete(character_id):
    """El dueño o el DM eliminan un personaje (con su inventario, imagen e intercambios)."""
    character = get_character_or_404(character_id)
    Character.delete(character_id)
    if session.get("character_id") == character_id:
        session.pop("character_id", None)  # era el personaje con el que jugaba: tendrá que elegir otro
    flash(f"{character['name']} ha sido eliminado.", "ok")
    return redirect(url_for("characters.index"))


# --- Inventario: acciones del jugador (y del DM) ---------------------------------

@bp.route("/<int:character_id>/inventory/<int:inventory_id>/equip", methods=["POST"])
@login_required
def toggle_equip(character_id, inventory_id):
    get_character_or_404(character_id)
    _own_inventory_row(character_id, inventory_id)
    Inventory.toggle(inventory_id, "equipped")
    return _back(character_id)


@bp.route("/<int:character_id>/inventory/<int:inventory_id>/remove", methods=["POST"])
@login_required
def remove_item(character_id, inventory_id):
    """El jugador tira objetos; el DM los retira."""
    get_character_or_404(character_id)
    row = _own_inventory_row(character_id, inventory_id)
    qty = form_int("quantity", row["quantity"])
    try:
        with transaction():
            Inventory.take(inventory_id, qty, character_id)
            verb = "El DM retira" if is_dm() else "Tira"
            ActivityLog.add(character_id, f"{verb} {qty}× {row['name']}")
    except RuleError as e:
        flash(str(e), "error")
    return _back(character_id)


# --- Inventario, dinero y efectos: solo DM ---------------------------------------

@bp.route("/<int:character_id>/inventory/add", methods=["POST"])
@dm_required
def add_item(character_id):
    get_character_or_404(character_id)
    item = Item.get(form_int("item_id"))
    if item is None:
        flash("Elige un objeto del catálogo.", "error")
        return _back(character_id)
    qty = form_int("quantity", 1)
    visible = bool(request.form.get("visible"))
    try:
        with transaction():
            Inventory.add(character_id, item["id"], qty, visible)
            if visible:
                ActivityLog.add(character_id, f"Recibe {qty}× {item['name']} del DM")
    except RuleError as e:
        flash(str(e), "error")
    return _back(character_id)


@bp.route("/<int:character_id>/inventory/<int:inventory_id>/visibility", methods=["POST"])
@dm_required
def toggle_item_visibility(character_id, inventory_id):
    _own_inventory_row(character_id, inventory_id)
    Inventory.toggle(inventory_id, "visible")
    return _back(character_id)


@bp.route("/<int:character_id>/currencies", methods=["POST"])
@dm_required
def set_currencies(character_id):
    get_character_or_404(character_id)
    try:
        with transaction():
            for currency in Currency.all():
                amount = form_int(f"cur_{currency['id']}")
                if amount is None:
                    continue
                old = Currency.balance(character_id, currency["id"])
                if amount != old:
                    Currency.set_amount(character_id, currency["id"], amount)
                    ActivityLog.add(character_id, f"El DM ajusta {currency['code']}: {old} → {amount}")
    except RuleError as e:
        flash(str(e), "error")
    else:
        flash("Bolsa actualizada.", "ok")
    return _back(character_id)


@bp.route("/<int:character_id>/conditions/add", methods=["POST"])
@dm_required
def add_condition(character_id):
    get_character_or_404(character_id)
    try:
        Condition.create(character_id, request.form)
    except RuleError as e:
        flash(str(e), "error")
    return _back(character_id)


def _own_condition(character_id, condition_id):
    condition = Condition.get(condition_id)
    if condition is None or condition["character_id"] != character_id:
        abort(404)


@bp.route("/<int:character_id>/conditions/<int:condition_id>/delete", methods=["POST"])
@dm_required
def delete_condition(character_id, condition_id):
    _own_condition(character_id, condition_id)
    Condition.delete(condition_id)
    return _back(character_id)


@bp.route("/<int:character_id>/conditions/<int:condition_id>/visibility", methods=["POST"])
@dm_required
def toggle_condition_visibility(character_id, condition_id):
    _own_condition(character_id, condition_id)
    Condition.toggle_visible(condition_id)
    return _back(character_id)


# --- Cualidades de los objetos del inventario --------------------------------------

def _own_trait(character_id, trait_id):
    trait = ItemTrait.get(trait_id)
    if trait is None or trait["character_id"] != character_id:
        abort(404)
    if not is_dm() and not trait["visible"]:
        abort(404)
    return trait


@bp.route("/<int:character_id>/inventory/<int:inventory_id>/traits", methods=["POST"])
@dm_required
def add_trait(character_id, inventory_id):
    _own_inventory_row(character_id, inventory_id)
    try:
        ItemTrait.create(request.form, inventory_item_id=inventory_id)
    except RuleError as e:
        flash(str(e), "error")
    return _back(character_id)


@bp.route("/<int:character_id>/traits/<int:trait_id>/use", methods=["POST"])
@login_required
def use_trait(character_id, trait_id):
    """El jugador (o el DM) gasta un uso."""
    get_character_or_404(character_id)
    _own_trait(character_id, trait_id)
    try:
        ItemTrait.use(trait_id)
    except RuleError as e:
        flash(str(e), "error")
    return _back(character_id)


@bp.route("/<int:character_id>/traits/<int:trait_id>/uses", methods=["POST"])
@dm_required
def set_trait_uses(character_id, trait_id):
    """El DM fija los usos restantes o recarga al máximo (sin valor)."""
    _own_trait(character_id, trait_id)
    try:
        ItemTrait.set_uses(trait_id, form_int("uses_current"))
    except RuleError as e:
        flash(str(e), "error")
    return _back(character_id)


@bp.route("/<int:character_id>/traits/<int:trait_id>/visibility", methods=["POST"])
@dm_required
def toggle_trait_visibility(character_id, trait_id):
    _own_trait(character_id, trait_id)
    ItemTrait.toggle_visible(trait_id)
    return _back(character_id)


@bp.route("/<int:character_id>/traits/<int:trait_id>/delete", methods=["POST"])
@dm_required
def delete_trait(character_id, trait_id):
    _own_trait(character_id, trait_id)
    ItemTrait.delete(trait_id)
    return _back(character_id)


# --- Imagen del personaje (dueño o DM) -------------------------------------------------

@bp.route("/<int:character_id>/avatar")
@login_required
def avatar(character_id):
    """Sirve la imagen. La URL lleva ?v=<versión>, así que el navegador puede guardarla
    en caché indefinidamente: al subir otra, cambia la versión y por tanto la URL."""
    row = Avatar.get(character_id)
    if row is None:
        abort(404)
    response = make_response(bytes(row["data"]))
    response.headers["Content-Type"] = row["mime"]
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Cache-Control"] = "private, max-age=31536000, immutable"
    response.set_etag(row["version"])
    return response.make_conditional(request)


@bp.route("/<int:character_id>/avatar", methods=["POST"])
@login_required
def upload_avatar(character_id):
    get_character_or_404(character_id)
    upload = request.files.get("image")
    try:
        size = Avatar.save(character_id, upload.read() if upload else b"")
    except RuleError as e:
        flash(str(e), "error")
    else:
        flash(f"Imagen actualizada ({max(1, size // 1024)} KB).", "ok")
    return _back(character_id)


@bp.route("/<int:character_id>/avatar/delete", methods=["POST"])
@login_required
def delete_avatar(character_id):
    get_character_or_404(character_id)
    Avatar.delete(character_id)
    flash("Imagen quitada: vuelve a mostrarse la inicial.", "ok")
    return _back(character_id)
