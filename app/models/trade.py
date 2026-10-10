from collections import defaultdict

from ..db import get_db, now_text, transaction
from .activity_log import ActivityLog
from .currency import Currency
from .errors import RuleError
from .inventory import Inventory

STATUS = {
    "pending": "Pendiente",
    "accepted": "Aceptado",
    "rejected": "Rechazado",
    "cancelled": "Cancelado",
}

_SELECT = """
    SELECT t.*, fc.name AS from_name, tc.name AS to_name,
           fc.user_id AS from_user_id, tc.user_id AS to_user_id
    FROM trades t
    JOIN characters fc ON fc.id = t.from_character_id
    JOIN characters tc ON tc.id = t.to_character_id
"""


class Trade:
    @staticmethod
    def all():
        return get_db().execute(_SELECT + " ORDER BY t.status != 'pending', t.id DESC").fetchall()

    @staticmethod
    def for_user(user_id):
        return get_db().execute(
            _SELECT + " WHERE fc.user_id = ? OR tc.user_id = ? ORDER BY t.status != 'pending', t.id DESC",
            (user_id, user_id),
        ).fetchall()

    @staticmethod
    def pending_count():
        return get_db().execute("SELECT COUNT(*) FROM trades WHERE status = 'pending'").fetchone()[0]

    @staticmethod
    def get(trade_id):
        return get_db().execute(_SELECT + " WHERE t.id = ?", (trade_id,)).fetchone()

    @staticmethod
    def lines_for(trade_ids):
        """{trade_id: {'give': [...], 'take': [...]}}"""
        result = defaultdict(lambda: {"give": [], "take": []})
        if trade_ids:
            marks = ",".join("?" for _ in trade_ids)
            rows = get_db().execute(
                f"SELECT * FROM trade_lines WHERE trade_id IN ({marks}) ORDER BY id", tuple(trade_ids)
            ).fetchall()
            for row in rows:
                result[row["trade_id"]][row["direction"]].append(row)
        return result

    # --- Proponer -------------------------------------------------------------------

    @staticmethod
    def create(from_id, to_id, give_items, give_currency, take_items, take_currency, message=""):
        """give_*/take_*: dict {inventory_item_id|currency_id: cantidad}."""
        if from_id == to_id:
            raise RuleError("No puedes comerciar contigo mismo.")
        if not (give_items or give_currency or take_items or take_currency):
            raise RuleError("La propuesta está vacía.")

        with transaction() as db:
            trade_id = db.insert(
                "INSERT INTO trades (from_character_id, to_character_id, message) VALUES (?, ?, ?)",
                (from_id, to_id, (message or "").strip()),
            )

            for direction, owner_id, items, currencies in (
                ("give", from_id, give_items, give_currency),
                ("take", to_id, take_items, take_currency),
            ):
                for inv_id, qty in items.items():
                    row = Inventory.get(inv_id)
                    if row is None or row["character_id"] != owner_id or not row["visible"]:
                        raise RuleError("Uno de los objetos seleccionados no está disponible.")
                    if qty > row["quantity"]:
                        raise RuleError(f"Solo hay {row['quantity']}× {row['name']}.")
                    db.execute(
                        """INSERT INTO trade_lines (trade_id, direction, inventory_item_id, quantity, label)
                           VALUES (?, ?, ?, ?, ?)""",
                        (trade_id, direction, inv_id, qty, row["name"]),
                    )
                for cur_id, qty in currencies.items():
                    currency = Currency.get(cur_id)
                    if currency is None:
                        raise RuleError("Divisa no válida.")
                    if direction == "give" and Currency.balance(owner_id, cur_id) < qty:
                        raise RuleError(f"No tienes suficiente {currency['name']}.")
                    db.execute(
                        """INSERT INTO trade_lines (trade_id, direction, currency_id, quantity, label)
                           VALUES (?, ?, ?, ?, ?)""",
                        (trade_id, direction, cur_id, qty, currency["code"]),
                    )
        return trade_id

    # --- Resolver ---------------------------------------------------------------------

    @staticmethod
    def accept(trade_id):
        """Ejecuta el intercambio completo o nada (si algo ya no está, se revierte)."""
        with transaction() as db:
            trade = Trade.get(trade_id)
            if trade is None or trade["status"] != "pending":
                raise RuleError("Este intercambio ya no está pendiente.")
            lines = db.execute("SELECT * FROM trade_lines WHERE trade_id = ?", (trade_id,)).fetchall()
            for line in lines:
                if line["direction"] == "give":
                    src, dst = trade["from_character_id"], trade["to_character_id"]
                else:
                    src, dst = trade["to_character_id"], trade["from_character_id"]
                if line["currency_id"] is not None:
                    Currency.adjust(src, line["currency_id"], -line["quantity"])
                    Currency.adjust(dst, line["currency_id"], line["quantity"])
                elif line["inventory_item_id"] is not None:
                    Inventory.transfer(line["inventory_item_id"], src, dst, line["quantity"])
                else:
                    raise RuleError(f"«{line['label']}» ya no existe; el intercambio no puede completarse.")

            db.execute(
                "UPDATE trades SET status = 'accepted', resolved_at = ? WHERE id = ?",
                (now_text(), trade_id),
            )
            ActivityLog.add(trade["from_character_id"], f"Intercambio #{trade_id} con {trade['to_name']} completado")
            ActivityLog.add(trade["to_character_id"], f"Intercambio #{trade_id} con {trade['from_name']} completado")

    @staticmethod
    def close(trade_id, status):
        if status not in ("rejected", "cancelled"):
            raise ValueError(status)
        db = get_db()
        cur = db.execute(
            "UPDATE trades SET status = ?, resolved_at = ? WHERE id = ? AND status = 'pending'",
            (status, now_text(), trade_id),
        )
        db.commit()
        if cur.rowcount == 0:
            raise RuleError("Este intercambio ya no está pendiente.")
