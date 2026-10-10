from ..db import get_db
from ..text import LIKE_ESCAPE, like_terms
from .errors import RuleError
from .item import CATEGORIES, rarity_order
from .item_trait import ItemTrait
from .listing import sort_sql

_SELECT = """
    SELECT ii.*, i.name, i.category, i.rarity, i.weight, i.properties,
           i.description, i.attunement
    FROM inventory_items ii JOIN items i ON i.id = ii.item_id
"""

SORTS = {
    "equipped": ("Equipados primero", "ii.equipped DESC, i.category, i.search_name, ii.id"),
    "name": ("Nombre", "i.search_name, ii.id"),
    "category": ("Categoría", "i.category, i.search_name, ii.id"),
    "rarity": ("Rareza (de más rara)", f"{rarity_order('i.rarity')} DESC, i.name, ii.id"),
    "weight": ("Peso total (mayor primero)", "i.weight * ii.quantity DESC, i.name, ii.id"),
    "quantity": ("Cantidad (mayor primero)", "ii.quantity DESC, i.name, ii.id"),
    "recent": ("Añadidos recientemente", "ii.id DESC"),
}


class Inventory:
    SORTS = SORTS

    @staticmethod
    def for_character(character_id, include_hidden=False, q="", category="", sort="equipped"):
        sql = _SELECT + " WHERE ii.character_id = ?"
        params = [character_id]
        if not include_hidden:
            sql += " AND ii.visible = 1"
        for term in like_terms(q):
            sql += " AND i.search_name LIKE ?" + LIKE_ESCAPE
            params.append(term)
        if category in CATEGORIES:
            sql += " AND i.category = ?"
            params.append(category)
        sql += " ORDER BY " + sort_sql(SORTS, sort, "equipped")
        return get_db().execute(sql, tuple(params)).fetchall()

    @staticmethod
    def get(inventory_id):
        return get_db().execute(_SELECT + " WHERE ii.id = ?", (inventory_id,)).fetchone()

    @staticmethod
    def total_weight(character_id, include_hidden=False):
        """Peso de todo lo que lleva (sin aplicar los filtros de la lista)."""
        sql = """SELECT COALESCE(SUM(i.weight * ii.quantity), 0)
                 FROM inventory_items ii JOIN items i ON i.id = ii.item_id WHERE ii.character_id = ?"""
        if not include_hidden:
            sql += " AND ii.visible = 1"
        return round(get_db().execute(sql, (character_id,)).fetchone()[0], 2)

    @staticmethod
    def count(character_id, include_hidden=False):
        sql = "SELECT COUNT(*) FROM inventory_items WHERE character_id = ?"
        if not include_hidden:
            sql += " AND visible = 1"
        return get_db().execute(sql, (character_id,)).fetchone()[0]

    # --- Operaciones sin commit (para componer dentro de transaction()) -------

    @staticmethod
    def _insert(character_id, item_id, quantity, visible):
        return get_db().insert(
            "INSERT INTO inventory_items (character_id, item_id, quantity, visible) VALUES (?, ?, ?, ?)",
            (character_id, item_id, quantity, 1 if visible else 0),
        )

    @staticmethod
    def _find_stack(character_id, item_id, visible, signature):
        """Pila existente donde apilar: mismas cualidades y ninguna con usos.

        Así dos pociones iguales se apilan, pero una espada maldita o una varita
        con cargas ocupan su propia fila y no «contagian» a las demás.
        """
        if ItemTrait.signature_has_uses(signature):
            return None
        candidates = get_db().execute(
            """SELECT id FROM inventory_items
               WHERE character_id = ? AND item_id = ? AND visible = ? AND equipped = 0""",
            (character_id, item_id, 1 if visible else 0),
        ).fetchall()
        for row in candidates:
            if ItemTrait.signature(inventory_item_id=row["id"]) == signature:
                return row["id"]
        return None

    @staticmethod
    def _grow(inventory_id, quantity):
        get_db().execute(
            "UPDATE inventory_items SET quantity = quantity + ? WHERE id = ?", (quantity, inventory_id)
        )

    @staticmethod
    def add(character_id, item_id, quantity, visible=True):
        """Añade objetos nuevos, con las cualidades de su plantilla del catálogo."""
        if quantity < 1:
            raise RuleError("La cantidad debe ser al menos 1.")
        signature = ItemTrait.signature(item_id=item_id)
        stack_id = Inventory._find_stack(character_id, item_id, visible, signature)
        if stack_id:
            Inventory._grow(stack_id, quantity)
            return stack_id
        new_id = Inventory._insert(character_id, item_id, quantity, visible)
        if signature:
            ItemTrait.copy(new_id, from_item_id=item_id)
        return new_id

    @staticmethod
    def _checked(inventory_id, quantity, character_id=None, visible_only=False):
        row = Inventory.get(inventory_id)
        if row is None or (character_id is not None and row["character_id"] != character_id):
            raise RuleError("Ese objeto ya no está en el inventario.")
        if visible_only and not row["visible"]:
            raise RuleError("Ese objeto no está disponible.")
        if quantity < 1 or quantity > row["quantity"]:
            raise RuleError(f"Cantidad no válida de {row['name']} (tienes {row['quantity']}).")
        return row

    @staticmethod
    def take(inventory_id, quantity, character_id=None, visible_only=False):
        """Quita `quantity` unidades de una pila. Devuelve la fila original."""
        row = Inventory._checked(inventory_id, quantity, character_id, visible_only)
        db = get_db()
        if quantity == row["quantity"]:
            db.execute("DELETE FROM inventory_items WHERE id = ?", (inventory_id,))
        else:
            db.execute(
                "UPDATE inventory_items SET quantity = quantity - ? WHERE id = ?",
                (quantity, inventory_id),
            )
        return row

    @staticmethod
    def transfer(inventory_id, from_character_id, to_character_id, quantity):
        """Mueve objetos entre personajes conservando sus cualidades (también las ocultas)."""
        row = Inventory._checked(inventory_id, quantity, from_character_id, visible_only=True)
        db = get_db()
        signature = ItemTrait.signature(inventory_item_id=inventory_id)
        stack_id = Inventory._find_stack(to_character_id, row["item_id"], True, signature)
        whole = quantity == row["quantity"]

        if stack_id:
            Inventory._grow(stack_id, quantity)
        elif whole:
            # La pila entera cambia de dueño tal cual, con sus cualidades y usos.
            db.execute(
                "UPDATE inventory_items SET character_id = ?, equipped = 0 WHERE id = ?",
                (to_character_id, inventory_id),
            )
            return row
        else:
            new_id = Inventory._insert(to_character_id, row["item_id"], quantity, True)
            if signature:
                ItemTrait.copy(new_id, from_inventory_item_id=inventory_id)

        if whole:
            db.execute("DELETE FROM inventory_items WHERE id = ?", (inventory_id,))
        else:
            db.execute(
                "UPDATE inventory_items SET quantity = quantity - ? WHERE id = ?", (quantity, inventory_id)
            )
        return row

    # --- Operaciones simples con commit ---------------------------------------

    @staticmethod
    def toggle(inventory_id, column):
        if column not in ("equipped", "visible"):
            raise ValueError(column)
        db = get_db()
        db.execute(
            f"UPDATE inventory_items SET {column} = 1 - {column} WHERE id = ?", (inventory_id,)
        )
        db.commit()
