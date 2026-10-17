"""Pestaña de conjuros de un personaje: espacios, trucos, conjuros por nivel y lanzamientos.

La manejan el dueño del personaje y el DM (como el resto de la ficha).
"""
from flask import Blueprint, abort, flash, redirect, render_template, request, url_for

from ..models import Character, DndClass, Magic, RuleError, effects, rules
from ..models.class_data import CASTER_TYPES, SCHOOLS, SPELL_PREP, SPELL_SOURCES
from ..models.spell import LEVEL_NAMES
from .helpers import get_character_or_404, is_dm, login_required

bp = Blueprint("spells", __name__, url_prefix="/characters")


def _back(character_id, anchor=None):
    return redirect(url_for("spells.show", character_id=character_id, _anchor=anchor))


def _entry_or_404(character_id, entry_id):
    entry = Magic.entry(character_id, entry_id)
    if entry is None:
        abort(404)
    return entry


@bp.route("/<int:character_id>/spells")
@login_required
def show(character_id):
    character = get_character_or_404(character_id)
    dm = is_dm()
    stats = rules.sheet(character, Character.proficiencies(character_id), effects.active(character_id, show_hidden=dm))
    spells = Magic.spells(character_id)
    by_level = {}
    for s in spells:
        by_level.setdefault(s["level"], []).append(s)
    slots = Magic.slots(character)
    # Listas de conjuros por clase (el buscador empieza en la suya; caballero y embaucador arcanos: la de mago)
    class_lists = [(c["code"], c["name"]) for c in DndClass.all() if c["code"] and c["caster"] != "none"]
    if character["subclass_progress"] in ("eldritch_knight", "arcane_trickster"):
        default_list = "wizard"
    else:
        default_list = character["class_code"] if character["class_code"] in dict(class_lists) else ""
    return render_template(
        "characters/spells.html",
        character=character,
        stats=stats,
        by_level=by_level,
        level_names=LEVEL_NAMES,
        slots=slots,
        item_spells=Magic.item_spells(character_id, include_hidden=dm),
        info=Magic.summary(character, stats, spells),
        has_magic=Magic.has_magic(character, include_hidden=dm),
        sources=SPELL_SOURCES,
        caster_types=CASTER_TYPES,
        spell_prep=SPELL_PREP,
        schools=SCHOOLS,
        class_lists=class_lists,
        default_list=default_list,
    )


@bp.route("/<int:character_id>/spells/add", methods=["POST"])
@login_required
def add(character_id):
    get_character_or_404(character_id)
    try:
        spell = Magic.add(character_id, request.form.get("spell_id", type=int), request.form.get("source", "class"),
                          always_prepared=bool(request.form.get("always_prepared")))
    except RuleError as e:
        flash(str(e), "error")
    else:
        flash(f"«{spell['name']}» añadido a su lista.", "ok")
        return _back(character_id, f"nivel-{spell['level']}")
    return _back(character_id)


@bp.route("/<int:character_id>/spells/<int:entry_id>/remove", methods=["POST"])
@login_required
def remove(character_id, entry_id):
    get_character_or_404(character_id)
    entry = _entry_or_404(character_id, entry_id)
    Magic.remove(entry_id)
    flash(f"«{entry['name']}» quitado de su lista.", "ok")
    return _back(character_id, f"nivel-{entry['level']}")


@bp.route("/<int:character_id>/spells/<int:entry_id>/prepare", methods=["POST"])
@login_required
def prepare(character_id, entry_id):
    get_character_or_404(character_id)
    entry = _entry_or_404(character_id, entry_id)
    Magic.toggle_prepared(entry_id)
    return _back(character_id, f"nivel-{entry['level']}")


@bp.route("/<int:character_id>/spells/<int:entry_id>/always", methods=["POST"])
@login_required
def always(character_id, entry_id):
    get_character_or_404(character_id)
    entry = _entry_or_404(character_id, entry_id)
    Magic.toggle_always(entry_id)
    return _back(character_id, f"nivel-{entry['level']}")


@bp.route("/<int:character_id>/spells/<int:entry_id>/cast", methods=["POST"])
@login_required
def cast(character_id, entry_id):
    character = get_character_or_404(character_id)
    entry = _entry_or_404(character_id, entry_id)
    try:
        slot = Magic.cast(character, entry, request.form.get("slot"), ritual=bool(request.form.get("ritual")))
    except RuleError as e:
        flash(str(e), "error")
    else:
        flash(f"Lanza «{entry['name']}»" + (f" (gasta un espacio de {slot['label'].lower()})." if slot else "."), "ok")
    return _back(character_id, f"nivel-{entry['level']}")


@bp.route("/<int:character_id>/slots/<slot>/<action>", methods=["POST"])
@login_required
def slot(character_id, slot, action):
    character = get_character_or_404(character_id)
    if action not in ("use", "restore"):
        abort(404)
    try:
        Magic.change_slot(character, slot, +1 if action == "use" else -1)
    except RuleError as e:
        flash(str(e), "error")
    return _back(character_id, "espacios")


@bp.route("/<int:character_id>/slots", methods=["POST"])
@login_required
def set_slots(character_id):
    character = get_character_or_404(character_id)
    keys = [str(n) for n in range(1, 10)] + ["pact"]
    Magic.set_slot_max(character, {k: request.form.get(f"max_{k}", "").strip() for k in keys if f"max_{k}" in request.form})
    flash("Espacios de conjuro actualizados.", "ok")
    return _back(character_id, "espacios")


@bp.route("/<int:character_id>/rest", methods=["POST"])
@login_required
def rest(character_id):
    character = get_character_or_404(character_id)
    kind = "short" if request.form.get("kind") == "short" else "long"
    Magic.rest(character, kind)
    flash("Descanso largo: espacios de conjuro recuperados." if kind == "long"
          else "Descanso corto: espacios de pacto recuperados.", "ok")
    return _back(character_id, "espacios")
