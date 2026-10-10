from ..db import get_db, transaction
from .activity_log import ActivityLog
from .currency import Currency
from .errors import RuleError
from .inventory import Inventory

KINDS = {"combat": "Tras combate", "environment": "Entorno"}


class Loot:
    @staticmethod
    def all(active_only=False):
        sql = "SELECT * FROM loot_pools"
        if active_only:
            sql += " WHERE active = 1"
        return get_db().execute(sql + " ORDER BY id DESC").fetchall()

    @staticmethod
    def get(pool_id):
        return get_db().execute("SELECT * FROM loot_pools WHERE id = ?", (pool_id,)).fetchone()

    @staticmethod
    def create(name, description, kind):
        if not (name or "").strip():
            raise RuleError("El botín necesita un nombre.")
        if kind not in KINDS:
            raise RuleError("Tipo de botín no válido.")
        db = get_db()
        pool_id = db.insert(
            "INSERT INTO loot_pools (name, description, kind) VALUES (?, ?, ?)",
            (name.strip(), (description or "").strip(), kind),
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
    def entries(pool_id):
        return get_db().execute(
            """SELECT le.*, i.name AS item_name, i.category, i.rarity, i.description,
                      c.name AS currency_name, c.code AS currency_code
               FROM loot_entries le
               LEFT JOIN items i ON i.id = le.item_id
               LEFT JOIN currencies c ON c.id = le.currency_id
               WHERE le.pool_id = ?
               ORDER BY le.currency_id IS NULL, le.id""",
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
