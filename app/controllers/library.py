"""Catálogos de reglas del DM: clases (con subclases) y conjuros, oficiales y homebrew."""
from flask import Blueprint, abort, flash, redirect, render_template, request, url_for

from ..models import DndClass, Item, RuleError, Spell
from ..models.class_data import CASTER_TYPES, HIT_DICE, SCHOOLS, SPELL_PREP
from ..models.rules import ABILITIES, ABILITY_SHORT
from ..models.spell import LEVEL_NAMES
from .helpers import ListArgs, dm_required, redirect_back

bp = Blueprint("library", __name__, url_prefix="/library")


def _class_context(**extra):
    return {"caster_types": CASTER_TYPES, "spell_prep": SPELL_PREP, "hit_dice": HIT_DICE,
            "abilities": ABILITIES, "ability_short": ABILITY_SHORT, **extra}


# --- Clases ---------------------------------------------------------------------------------

@bp.route("/classes", methods=["GET", "POST"])
@dm_required
def classes():
    if request.method == "POST":
        try:
            class_id = DndClass.create(request.form)
        except RuleError as e:
            flash(str(e), "error")
        else:
            flash("Clase homebrew creada. Añádele subclases si quieres.", "ok")
            return redirect(url_for("library.edit_class", class_id=class_id))
    subs = {}
    for s in DndClass.subclasses():
        subs.setdefault(s["class_id"], []).append(s)
    return render_template("library/classes.html", classes=DndClass.all(), subs=subs, cls=None,
                           **_class_context())


@bp.route("/classes/<int:class_id>", methods=["GET", "POST"])
@dm_required
def edit_class(class_id):
    cls = DndClass.get(class_id) or abort(404)
    if request.method == "POST":
        try:
            DndClass.update(class_id, request.form)
        except RuleError as e:
            flash(str(e), "error")
        else:
            flash("Clase actualizada. Los personajes que ya la tienen conservan sus valores.", "ok")
            return redirect(url_for("library.edit_class", class_id=class_id))
    return render_template("library/class_form.html", cls=cls, subclasses=DndClass.subclasses(class_id),
                           **_class_context())


@bp.route("/classes/<int:class_id>/delete", methods=["POST"])
@dm_required
def delete_class(class_id):
    try:
        DndClass.delete(class_id)
    except RuleError as e:
        flash(str(e), "error")
        return redirect_back(url_for("library.classes"))
    flash("Clase eliminada. Los personajes que la tenían conservan su nombre como clase personalizada.", "ok")
    return redirect(url_for("library.classes"))


@bp.route("/classes/<int:class_id>/subclasses", methods=["POST"])
@dm_required
def add_subclass(class_id):
    try:
        DndClass.add_subclass(class_id, request.form)
    except RuleError as e:
        flash(str(e), "error")
    else:
        flash("Subclase añadida.", "ok")
    return redirect(url_for("library.edit_class", class_id=class_id))


@bp.route("/subclasses/<int:subclass_id>/delete", methods=["POST"])
@dm_required
def delete_subclass(subclass_id):
    sub = DndClass.get_subclass(subclass_id) or abort(404)
    try:
        DndClass.delete_subclass(subclass_id)
    except RuleError as e:
        flash(str(e), "error")
    else:
        flash("Subclase eliminada.", "ok")
    return redirect(url_for("library.edit_class", class_id=sub["class_id"]))


# --- Conjuros ----------------------------------------------------------------------------------

def _spell_context(**extra):
    casters = [c for c in DndClass.all() if c["code"] and c["caster"] != "none"]
    return {"schools": SCHOOLS, "level_names": LEVEL_NAMES, "class_options": casters,
            "class_names": {c["code"]: c["name"] for c in casters}, **extra}


@bp.route("/spells", methods=["GET", "POST"])
@dm_required
def spells():
    if request.method == "POST":
        try:
            Spell.create(request.form)
        except RuleError as e:
            flash(str(e), "error")
        else:
            flash("Conjuro añadido al catálogo.", "ok")
        return redirect_back(url_for("library.spells"))
    args = ListArgs(Spell.SORTS, "level", filters=["level", "school", "cls"])
    found = Spell.search(args.q, args.level, args.school, args.cls, sort=args.sort, page=args.page)
    return render_template("library/spells.html", spells=found, args=args, spell=None, **_spell_context())


@bp.route("/spells/<int:spell_id>", methods=["GET", "POST"])
@dm_required
def edit_spell(spell_id):
    spell = Spell.get(spell_id) or abort(404)
    if request.method == "POST":
        try:
            Spell.update(spell_id, request.form)
        except RuleError as e:
            flash(str(e), "error")
        else:
            flash("Conjuro actualizado.", "ok")
            return redirect(url_for("library.spells"))
    return render_template("library/spell_form.html", spell=spell, **_spell_context())


@bp.route("/spells/<int:spell_id>/delete", methods=["POST"])
@dm_required
def delete_spell(spell_id):
    Spell.delete(spell_id)
    flash("Conjuro eliminado (también de las listas de los personajes).", "ok")
    return redirect_back(url_for("library.spells"))


# --- Conjuros que concede un objeto del catálogo ---------------------------------------------------

@bp.route("/items/<int:item_id>/spells", methods=["POST"])
@dm_required
def add_item_spell(item_id):
    Item.get(item_id) or abort(404)
    try:
        Spell.add_to_item(item_id, request.form.get("spell_id", type=int))
    except RuleError as e:
        flash(str(e), "error")
    return redirect(url_for("dm.edit_item", item_id=item_id, _anchor="conjuros"))


@bp.route("/items/<int:item_id>/spells/<int:spell_id>/delete", methods=["POST"])
@dm_required
def remove_item_spell(item_id, spell_id):
    Spell.remove_from_item(item_id, spell_id)
    return redirect(url_for("dm.edit_item", item_id=item_id, _anchor="conjuros"))
