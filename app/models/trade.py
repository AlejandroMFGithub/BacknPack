from collections import defaultdict

from ..db import get_db, now_text, transaction
from .activity_log import ActivityLog
from .campaign import Campaign
from .currency import Currency
from .errors import RuleError
from .inventory import Inventory
from .listing import PER_PAGE, paginate, sort_sql

STATUS = {
    "pending": "Pendiente",
    "accepted": "Aceptado",
    "rejected": "Rechazado",
    "cancelled": "Cancelado",
}

_SELECT = """
    SELECT t.*, fc.name AS from_name, tc.name AS to_name,
           fc.user_id AS from_user_id, tc.user_id AS to_user_id,
           fa.version AS from_avatar, ta.version AS to_avatar
    FROM trades t
    JOIN characters fc ON fc.id = t.from_character_id
    JOIN characters tc ON tc.id = t.to_character_id
    LEFT JOIN character_avatars fa ON fa.character_id = fc.id
    LEFT JOIN character_avatars ta ON ta.character_id = tc.id
"""


SORTS = {
    "pending": ("Pendientes primero", "t.status <> 'pending', t.id DESC"),
    "recent": ("Más recientes", "t.id DESC"),
    "oldest": ("Más antiguos", "t.id"),
}


class Trade:
    SORTS = SORTS

    @staticmethod
    def search(campaign_id, user_id=None, status="", sort="pending", page=1, per_page=PER_PAGE):
        """Intercambios de una campaña (todos para el DM, o los de los personajes de user_id)."""
        where, params = ["fc.campaign_id = ?"], [campaign_id]
        if user_id is not None:
            where.append("(fc.user_id = ? OR tc.user_id = ?)")
            params += [user_id, user_id]
        if status in STATUS:
            where.append("t.status = ?")
            params.append(status)
        return paginate(_SELECT, where, params, sort_sql(SORTS, sort, "pending"), page, per_page)

    @staticmethod
    def pending_count(campaign_id):
        return get_db().execute(
            """SELECT COUNT(*) FROM trades t JOIN characters fc ON fc.id = t.from_character_id
               WHERE t.status = 'pending' AND fc.campaign_id = ?""", (campaign_id,),
        ).fetchone()[0]

    @staticmethod
    def get(trade_id):
        return get_db().execute(_SELECT + " WHERE t.id = ?", (trade_id,)).fetchone()

    # --- Avisos -----------------------------------------------------------------------------

    @staticmethod
    def pending_for(character_id):
        """Intercambios pendientes de un personaje: (le proponen, propone él)."""
        rows = get_db().execute(
            _SELECT + """ WHERE t.status = 'pending' AND (t.from_character_id = ? OR t.to_character_id = ?)
                          ORDER BY t.id DESC""",
            (character_id, character_id),
        ).fetchall()
        incoming = [t for t in rows if t["to_character_id"] == character_id]
        outgoing = [t for t in rows if t["from_character_id"] == character_id]
        return incoming, outgoing

    @staticmethod
    def mark_seen(character_id, trade_id=None):
        """Marca como vistas las propuestas que ha recibido (todas o una)."""
        sql = """UPDATE trades SET seen_at = ?
                 WHERE to_character_id = ? AND status = 'pending' AND seen_at IS NULL"""
        params = [now_text(), character_id]
        if trade_id is not None:
            sql += " AND id = ?"
            params.append(trade_id)
        db = get_db()
        db.execute(sql, tuple(params))
        db.commit()

    @staticmethod
    def incoming_counts(user_id):
        """{personaje: nº de propuestas pendientes que ha recibido}, de todos los del jugador."""
        rows = get_db().execute(
            """SELECT t.to_character_id, COUNT(*) FROM trades t
               JOIN characters c ON c.id = t.to_character_id
               WHERE c.user_id = ? AND t.status = 'pending' GROUP BY t.to_character_id""",
            (user_id,),
        ).fetchall()
        return {r[0]: r[1] for r in rows}

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
        if Campaign.of_character(from_id) != Campaign.of_character(to_id):
            raise RuleError("Solo se puede comerciar con personajes de la misma campaña.")

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
            if Campaign.of_character(trade["from_character_id"]) != Campaign.of_character(trade["to_character_id"]):
                raise RuleError("Los personajes ya no están en la misma campaña.")
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
