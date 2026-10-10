"""Cualidades de objetos: propiedades, bendiciones, maldiciones y usos limitados.

Una cualidad pertenece a una plantilla del catálogo (item_id) o a un objeto concreto
de un inventario (inventory_item_id). Al dar un objeto a un personaje se copian las
cualidades de su plantilla, y desde ahí cada ejemplar evoluciona por su cuenta
(gasta cargas, el DM le añade una maldición...).
"""
from collections import defaultdict

from ..db import get_db, transaction
from .activity_log import ActivityLog
from .errors import RuleError

KINDS = {
    "property": "Propiedad",
    "blessing": "Bendición",
    "curse": "Maldición",
    "charges": "Usos limitados",
}

_COLUMNS = "name, kind, description, uses_max, uses_current, recharge, visible"

_SELECT = """
    SELECT t.*, ii.character_id, i.name AS item_name
    FROM item_traits t
    LEFT JOIN inventory_items ii ON ii.id = t.inventory_item_id
    LEFT JOIN items i ON i.id = COALESCE(t.item_id, ii.item_id)
"""


def _int_or_none(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


class ItemTrait:
    # --- Consultas -------------------------------------------------------------------

    @staticmethod
    def get(trait_id):
        return get_db().execute(_SELECT + " WHERE t.id = ?", (trait_id,)).fetchone()

    @staticmethod
    def _grouped(column, ids, include_hidden):
        result = defaultdict(list)
        ids = list(ids)
        if not ids:
            return result
        sql = f"SELECT * FROM item_traits WHERE {column} IN ({','.join('?' for _ in ids)})"
        if not include_hidden:
            sql += " AND visible = 1"
        sql += " ORDER BY kind = 'curse', kind, name"
        for row in get_db().execute(sql, tuple(ids)).fetchall():
            result[row[column]].append(row)
        return result

    @staticmethod
    def for_items(item_ids, include_hidden=True):
        """{item_id: [cualidades de plantilla]}"""
        return ItemTrait._grouped("item_id", item_ids, include_hidden)

    @staticmethod
    def for_inventory(inventory_ids, include_hidden=True):
        """{inventory_item_id: [cualidades del ejemplar]}"""
        return ItemTrait._grouped("inventory_item_id", inventory_ids, include_hidden)

    @staticmethod
    def signature(item_id=None, inventory_item_id=None):
        """Lista comparable de las cualidades: dos pilas con la misma firma son intercambiables."""
        column, value = ("item_id", item_id) if item_id is not None else ("inventory_item_id", inventory_item_id)
        rows = get_db().execute(
            f"SELECT {_COLUMNS} FROM item_traits WHERE {column} = ?", (value,)
        ).fetchall()
        return sorted((tuple(r) for r in rows), key=repr)

    @staticmethod
    def signature_has_uses(signature):
        return any(trait[3] is not None for trait in signature)  # uses_max

    # --- Alta / baja ---------------------------------------------------------------------

    @staticmethod
    def _clean(data):
        name = (data.get("name") or "").strip()
        kind = data.get("kind")
        if not name:
            raise RuleError("La cualidad necesita un nombre.")
        if kind not in KINDS:
            raise RuleError("Tipo de cualidad no válido.")
        uses_max = _int_or_none(data.get("uses_max"))
        if uses_max is not None and uses_max < 1:
            uses_max = None
        if kind == "charges" and uses_max is None:
            raise RuleError("Indica cuántos usos tiene como máximo.")
        uses_current = _int_or_none(data.get("uses_current"))
        if uses_max is None:
            uses_current = None
        elif uses_current is None or not 0 <= uses_current <= uses_max:
            uses_current = uses_max
        return (
            name, kind, (data.get("description") or "").strip(), uses_max, uses_current,
            (data.get("recharge") or "").strip(), 1 if data.get("visible") else 0,
        )

    @staticmethod
    def create(data, item_id=None, inventory_item_id=None):
        db = get_db()
        trait_id = db.insert(
            f"INSERT INTO item_traits (item_id, inventory_item_id, {_COLUMNS}) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (item_id, inventory_item_id, *ItemTrait._clean(data)),
        )
        db.commit()
        return trait_id

    @staticmethod
    def copy(to_inventory_item_id, from_item_id=None, from_inventory_item_id=None):
        """Copia cualidades de una plantilla o de otro ejemplar. Sin commit."""
        column, value = (
            ("item_id", from_item_id) if from_item_id is not None
            else ("inventory_item_id", from_inventory_item_id)
        )
        get_db().execute(
            f"""INSERT INTO item_traits (inventory_item_id, {_COLUMNS})
                SELECT ?, {_COLUMNS} FROM item_traits WHERE {column} = ?""",
            (to_inventory_item_id, value),
        )

    @staticmethod
    def delete(trait_id):
        db = get_db()
        db.execute("DELETE FROM item_traits WHERE id = ?", (trait_id,))
        db.commit()

    @staticmethod
    def toggle_visible(trait_id):
        db = get_db()
        db.execute("UPDATE item_traits SET visible = 1 - visible WHERE id = ?", (trait_id,))
        db.commit()

    # --- Usos ------------------------------------------------------------------------------

    @staticmethod
    def use(trait_id):
        with transaction() as db:
            trait = ItemTrait.get(trait_id)
            if trait is None or trait["uses_max"] is None:
                raise RuleError("Esa cualidad no tiene usos.")
            if trait["uses_current"] <= 0:
                raise RuleError(f"«{trait['name']}» no tiene usos restantes.")
            remaining = trait["uses_current"] - 1
            db.execute("UPDATE item_traits SET uses_current = ? WHERE id = ?", (remaining, trait_id))
            if trait["visible"] and trait["character_id"]:
                ActivityLog.add(
                    trait["character_id"],
                    f"Usa «{trait['name']}» de {trait['item_name']} ({remaining}/{trait['uses_max']})",
                )
        return remaining

    @staticmethod
    def set_uses(trait_id, value):
        """Fija los usos restantes (None = recargar al máximo)."""
        trait = ItemTrait.get(trait_id)
        if trait is None or trait["uses_max"] is None:
            raise RuleError("Esa cualidad no tiene usos.")
        value = trait["uses_max"] if value is None else max(0, min(value, trait["uses_max"]))
        db = get_db()
        db.execute("UPDATE item_traits SET uses_current = ? WHERE id = ?", (value, trait_id))
        db.commit()
        return value
