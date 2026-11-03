"""Editar un objeto desde donde aparece (inventario, tienda, botín): este ejemplar o todos.

«Todos los ejemplares» cambia el objeto del catálogo. «Solo este ejemplar» crea una versión
única del objeto (una copia en items con unique_copy = 1 y parent_id = el original, con sus
cualidades de plantilla y conjuros) y solo esa fila pasa a usarla. Así viaja con el objeto al
comerciar, comprar o recoger, y no aparece en el catálogo normal.
"""
from ..db import get_db, transaction
from .errors import RuleError
from .item import Item

KINDS = {"inventory": "inventario", "shop": "tienda", "loot": "botín"}


def context(kind, ref_id):
    """Dónde está el objeto: fila, objeto, cantidad y una etiqueta para la página."""
    db = get_db()
    if kind == "inventory":
        row = db.execute(
            """SELECT ii.*, c.name AS owner_name FROM inventory_items ii JOIN characters c ON c.id = ii.character_id
               WHERE ii.id = ?""", (ref_id,)).fetchone()
        label = row and f"el inventario de {row['owner_name']}"
        quantity = row and row["quantity"]
    elif kind == "shop":
        row = db.execute(
            """SELECT si.*, s.name AS owner_name FROM shop_items si JOIN shops s ON s.id = si.shop_id
               WHERE si.id = ?""", (ref_id,)).fetchone()
        label = row and f"la tienda «{row['owner_name']}»"
        quantity = None  # una oferta se cambia entera
    elif kind == "loot":
        row = db.execute(
            """SELECT le.*, p.name AS owner_name FROM loot_entries le JOIN loot_pools p ON p.id = le.pool_id
               WHERE le.id = ? AND le.item_id IS NOT NULL""", (ref_id,)).fetchone()
        label = row and f"el botín «{row['owner_name']}»"
        quantity = row and row["quantity"]
    else:
        row = None
    if row is None:
        return None
    item = Item.get(row["item_id"])
    parent = Item.get(item["parent_id"]) if item["parent_id"] else None
    return {"kind": kind, "ref_id": ref_id, "row": row, "item": item, "parent": parent, "label": label,
            "quantity": quantity, "uses": references(item["id"])}


def references(item_id):
    """En cuántos sitios (filas de inventario, ofertas, entradas de botín) se usa un objeto."""
    db = get_db()
    return sum(db.execute(f"SELECT COUNT(*) FROM {table} WHERE item_id = ?", (item_id,)).fetchone()[0]
               for table in ("inventory_items", "shop_items", "loot_entries"))


def _fork(db, item, clean):
    """Crea la versión única con los datos nuevos y copia cualidades de plantilla y conjuros. Sin commit."""
    clean = dict(clean, parent_id=item["parent_id"] or item["id"], unique_copy=1)
    new_id = db.insert(
        f"INSERT INTO items ({', '.join(clean)}) VALUES ({', '.join('?' for _ in clean)})", tuple(clean.values()),
    )
    from .item_trait import _COLUMNS
    db.execute(f"""INSERT INTO item_traits (item_id, {_COLUMNS})
                   SELECT ?, {_COLUMNS} FROM item_traits WHERE item_id = ?""", (new_id, item["id"]))
    db.execute("INSERT INTO item_spells (item_id, spell_id) SELECT ?, spell_id FROM item_spells WHERE item_id = ?",
               (new_id, item["id"]))
    return new_id


def _repoint(db, ctx, new_item_id, one_unit):
    """Hace que la fila use el objeto nuevo; con one_unit, separa una unidad de la pila. Sin commit."""
    row, kind = ctx["row"], ctx["kind"]
    split = one_unit and (ctx["quantity"] or 1) > 1
    if kind == "inventory":
        if not split:
            db.execute("UPDATE inventory_items SET item_id = ? WHERE id = ?", (new_item_id, row["id"]))
            return row["id"]
        db.execute("UPDATE inventory_items SET quantity = quantity - 1 WHERE id = ?", (row["id"],))
        new_row = db.insert(
            """INSERT INTO inventory_items (character_id, item_id, quantity, equipped, visible, proficient)
               VALUES (?, ?, 1, ?, ?, ?)""",
            (row["character_id"], new_item_id, row["equipped"], row["visible"], row["proficient"]),
        )
        from .item_trait import ItemTrait
        ItemTrait.copy(new_row, from_inventory_item_id=row["id"])  # sus cualidades de ejemplar van con él
        return new_row
    if kind == "loot" and split:
        db.execute("UPDATE loot_entries SET quantity = quantity - 1 WHERE id = ?", (row["id"],))
        return db.insert("INSERT INTO loot_entries (pool_id, item_id, quantity) VALUES (?, ?, 1)",
                         (row["pool_id"], new_item_id))
    table = {"shop": "shop_items", "loot": "loot_entries"}[kind]
    db.execute(f"UPDATE {table} SET item_id = ? WHERE id = ?", (new_item_id, row["id"]))
    return row["id"]


def save(ctx, data, scope, one_unit=False):
    """Guarda los cambios. scope: «copy» (solo este ejemplar) o «all» (el objeto del catálogo).
    Devuelve (id de la fila que queda con el objeto editado, texto para el aviso)."""
    item = ctx["item"]
    clean = Item._clean(data)
    with transaction() as db:
        if scope == "all":
            if item["unique_copy"]:
                raise RuleError("Este ejemplar ya es una versión única: sus cambios no afectan al catálogo.")
            db.execute(f"UPDATE items SET {', '.join(f'{k} = ?' for k in clean)} WHERE id = ?",
                       (*clean.values(), item["id"]))
            return ctx["ref_id"], f"«{clean['name']}» actualizado en el catálogo (todos los ejemplares)."
        splitting = one_unit and (ctx["quantity"] or 1) > 1
        if item["unique_copy"] and ctx["uses"] == 1 and not splitting:
            # Ya es la versión única de esta fila: se edita tal cual
            db.execute(f"UPDATE items SET {', '.join(f'{k} = ?' for k in clean)} WHERE id = ?",
                       (*clean.values(), item["id"]))
            return ctx["ref_id"], f"Ejemplar «{clean['name']}» actualizado."
        new_id = _fork(db, item, clean)
        ref = _repoint(db, ctx, new_id, one_unit)
    where = "una unidad de " + ctx["label"] if splitting else ctx["label"]
    return ref, f"Ahora {where} tiene su propia versión de «{clean['name']}»; el catálogo no cambia."


def revert(ctx):
    """Vuelve a usar el objeto original del catálogo y borra la versión única si ya no se usa."""
    item, parent = ctx["item"], ctx["parent"]
    if not item["unique_copy"]:
        raise RuleError("Este ejemplar ya es el del catálogo.")
    if parent is None:
        raise RuleError("El objeto original ya no está en el catálogo.")
    with transaction() as db:
        table = {"inventory": "inventory_items", "shop": "shop_items", "loot": "loot_entries"}[ctx["kind"]]
        db.execute(f"UPDATE {table} SET item_id = ? WHERE id = ?", (parent["id"], ctx["ref_id"]))
        if references(item["id"]) == 0:
            db.execute("DELETE FROM items WHERE id = ?", (item["id"],))
    return parent
