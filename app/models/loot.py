from ..db import get_db, transaction
from .activity_log import ActivityLog
from .campaign import Campaign
from .currency import Currency
from ..text import distances
from .errors import RuleError
from .inventory import Inventory
from .listing import sort_sql
from .shop import filter_by_name

KINDS = {"combat": "Tras combate", "environment": "Entorno"}

SORTS = {
    "recent": ("Más recientes", "id DESC"),
    "name": ("Nombre", "name, id"),
    "kind": ("Tipo", "kind, name, id"),
}
ENTRY_SORTS = {
    "type": ("Monedas primero", "le.currency_id IS NULL, le.id"),
    "name": ("Nombre", "COALESCE(i.name, c.name), le.id"),
    "quantity": ("Cantidad (mayor primero)", "le.quantity DESC, le.id"),
}


class Loot:
    SORTS = SORTS
    ENTRY_SORTS = ENTRY_SORTS

    @staticmethod
    def all(campaign_id, active_only=False, q="", kind="", sort="recent"):
        sql, params = "SELECT * FROM loot_pools WHERE campaign_id = ?", [campaign_id]
        if active_only:
            sql += " AND active = 1"
        if kind in KINDS:
            sql += " AND kind = ?"
            params.append(kind)
        rows = get_db().execute(sql + " ORDER BY " + sort_sql(SORTS, sort, "recent"), tuple(params)).fetchall()
        return filter_by_name(rows, q)

    @staticmethod
    def get(pool_id):
        return get_db().execute("SELECT * FROM loot_pools WHERE id = ?", (pool_id,)).fetchone()

    @staticmethod
    def create(name, description, kind, campaign_id):
        if not (name or "").strip():
            raise RuleError("El botín necesita un nombre.")
        if kind not in KINDS:
            raise RuleError("Tipo de botín no válido.")
        db = get_db()
        pool_id = db.insert(
            "INSERT INTO loot_pools (name, description, kind, campaign_id) VALUES (?, ?, ?, ?)",
            (name.strip(), distances((description or "").strip()), kind, campaign_id),
        )
        db.commit()
        return pool_id

    @staticmethod
    def toggle(pool_id):
        db = get_db()
        db.execute("UPDATE loot_pools SET active = 1 - active WHERE id = ?", (pool_id,))
        db.commit()

    @staticmethod
    def delete(pool_id):
        db = get_db()
        db.execute("DELETE FROM loot_pools WHERE id = ?", (pool_id,))
        db.commit()

    # --- Contenido ----------------------------------------------------------------

    @staticmethod
    def entries(pool_id, sort="type"):
        return get_db().execute(
            """SELECT le.*, i.name AS item_name, i.category, i.rarity, i.description,
                      c.name AS currency_name, c.code AS currency_code
               FROM loot_entries le
               LEFT JOIN items i ON i.id = le.item_id
               LEFT JOIN currencies c ON c.id = le.currency_id
               WHERE le.pool_id = ?
               ORDER BY """ + sort_sql(ENTRY_SORTS, sort, "type"),
            (pool_id,),
        ).fetchall()

    @staticmethod
    def add_entry(pool_id, item_id=None, currency_id=None, quantity=1):
        if quantity < 1:
            raise RuleError("La cantidad debe ser al menos 1.")
        if (item_id is None) == (currency_id is None):
            raise RuleError("Elige un objeto o una divisa.")
        db = get_db()
        db.execute(
            "INSERT INTO loot_entries (pool_id, item_id, currency_id, quantity) VALUES (?, ?, ?, ?)",
            (pool_id, item_id, currency_id, quantity),
        )
        db.commit()

    @staticmethod
    def remove_entry(entry_id):
        db = get_db()
        db.execute("DELETE FROM loot_entries WHERE id = ?", (entry_id,))
        db.commit()

    # --- Recoger ------------------------------------------------------------------

    @staticmethod
    def claim(entry_id, character_id, quantity):
        with transaction() as db:
            entry = db.execute("SELECT * FROM loot_entries WHERE id = ?", (entry_id,)).fetchone()
            if entry is None:
                raise RuleError("Alguien se te ha adelantado: ese botín ya no está.")
            pool = Loot.get(entry["pool_id"])
            if not pool["active"]:
                raise RuleError("Este botín ya no está disponible.")
            if Campaign.of_character(character_id) != pool["campaign_id"]:
                raise RuleError("Ese botín está en otra campaña.")
            if quantity < 1 or quantity > entry["quantity"]:
                raise RuleError(f"Cantidad no válida (quedan {entry['quantity']}).")

            if entry["item_id"]:
                Inventory.add(character_id, entry["item_id"], quantity)
                label = db.execute("SELECT name FROM items WHERE id = ?", (entry["item_id"],)).fetchone()["name"]
            else:
                Currency.adjust(character_id, entry["currency_id"], quantity)
                label = Currency.get(entry["currency_id"])["code"]

            if quantity == entry["quantity"]:
                db.execute("DELETE FROM loot_entries WHERE id = ?", (entry_id,))
            else:
                db.execute(
                    "UPDATE loot_entries SET quantity = quantity - ? WHERE id = ?", (quantity, entry_id)
                )
            ActivityLog.add(character_id, f"Recoge {quantity}× {label} de «{pool['name']}»")
        return label
