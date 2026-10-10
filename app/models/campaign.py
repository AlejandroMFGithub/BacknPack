"""Campañas («mundos»): agrupan personajes, tiendas y botines.

El catálogo de objetos y las divisas son comunes a todas las campañas.
"""
from ..db import get_db
from .errors import RuleError

_SELECT = """
    SELECT cp.*,
           (SELECT COUNT(*) FROM characters c WHERE c.campaign_id = cp.id) AS character_count,
           (SELECT COUNT(*) FROM shops s WHERE s.campaign_id = cp.id) AS shop_count,
           (SELECT COUNT(*) FROM loot_pools l WHERE l.campaign_id = cp.id) AS loot_count
    FROM campaigns cp
"""


class Campaign:
    @staticmethod
    def all(include_archived=True):
        sql = _SELECT
        if not include_archived:
            sql += " WHERE cp.archived = 0"
        return get_db().execute(sql + " ORDER BY cp.archived, cp.name, cp.id").fetchall()

    @staticmethod
    def get(campaign_id):
        return get_db().execute(_SELECT + " WHERE cp.id = ?", (campaign_id,)).fetchone()

    @staticmethod
    def open_for_players():
        """Campañas en las que un jugador puede crear un personaje."""
        return get_db().execute(
            "SELECT * FROM campaigns WHERE archived = 0 AND is_open = 1 ORDER BY name, id"
        ).fetchall()

    @staticmethod
    def first_active():
        return get_db().execute(
            "SELECT * FROM campaigns WHERE archived = 0 ORDER BY id LIMIT 1"
        ).fetchone()

    @staticmethod
    def remember_for(user_id, campaign_id):
        """Guarda la última campaña del DM para volver a ella al iniciar sesión."""
        db = get_db()
        db.execute("UPDATE users SET last_campaign_id = ? WHERE id = ?", (campaign_id, user_id))
        db.commit()

    @staticmethod
    def _clean(data):
        name = (data.get("name") or "").strip()
        if not name:
            raise RuleError("La campaña necesita un nombre.")
        return name, (data.get("description") or "").strip()

    @staticmethod
    def create(data):
        name, description = Campaign._clean(data)
        db = get_db()
        campaign_id = db.insert(
            "INSERT INTO campaigns (name, description, is_open) VALUES (?, ?, ?)",
            (name, description, 1 if data.get("is_open") else 0),
        )
        db.commit()
        return campaign_id

    @staticmethod
    def update(campaign_id, data):
        name, description = Campaign._clean(data)
        db = get_db()
        db.execute(
            "UPDATE campaigns SET name = ?, description = ? WHERE id = ?", (name, description, campaign_id)
        )
        db.commit()

    @staticmethod
    def toggle(campaign_id, column):
        if column not in ("is_open", "archived"):
            raise ValueError(column)
        db = get_db()
        db.execute(f"UPDATE campaigns SET {column} = 1 - {column} WHERE id = ?", (campaign_id,))
        db.commit()

    @staticmethod
    def delete(campaign_id):
        """Solo si no tiene personajes (con ellos, mejor archivarla). Borra sus tiendas y botines."""
        campaign = Campaign.get(campaign_id)
        if campaign is None:
            return
        if campaign["character_count"]:
            raise RuleError(
                f"«{campaign['name']}» tiene {campaign['character_count']} personaje(s). "
                "Muévelos o elimínalos antes, o archiva la campaña."
            )
        db = get_db()
        db.execute("DELETE FROM campaigns WHERE id = ?", (campaign_id,))
        db.commit()

    @staticmethod
    def of_character(character_id):
        row = get_db().execute("SELECT campaign_id FROM characters WHERE id = ?", (character_id,)).fetchone()
        return row["campaign_id"] if row else None

    @staticmethod
    def require(campaign_id, for_player=False):
        """Devuelve la campaña si se pueden crear personajes en ella; si no, RuleError."""
        campaign = Campaign.get(campaign_id) if campaign_id else None
        if campaign is None:
            raise RuleError("Elige una campaña.")
        if campaign["archived"]:
            raise RuleError("Esa campaña está archivada.")
        if for_player and not campaign["is_open"]:
            raise RuleError("Esa campaña no admite personajes nuevos. Pídeselo al DM.")
        return campaign
