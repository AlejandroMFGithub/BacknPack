"""Campañas («mundos»): agrupan personajes, tiendas y botines.

El catálogo de objetos y las divisas son comunes a todas las campañas.
"""
import re
import secrets

from ..db import get_db
from .errors import RuleError

# Sin 0/O ni 1/I para que el código se pueda dictar y copiar sin errores
CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
CODE_LENGTH = 8


def normalize_code(text):
    """«k7qx-m4tp » -> «K7QXM4TP»: da igual mayúsculas, espacios o guiones."""
    return re.sub(r"[^A-Z0-9]", "", (text or "").upper())


def format_code(code):
    """«K7QXM4TP» -> «K7QX-M4TP» (para mostrarlo)."""
    return f"{code[:4]}-{code[4:]}" if code and len(code) == CODE_LENGTH else (code or "")


def new_join_code(db=None):
    """Código aleatorio y único (32^8 ≈ 10^12 combinaciones: imposible de adivinar a ciegas)."""
    db = db or get_db()
    while True:
        code = "".join(secrets.choice(CODE_ALPHABET) for _ in range(CODE_LENGTH))
        if not db.execute("SELECT 1 FROM campaigns WHERE join_code = ?", (code,)).fetchone():
            return code

_SELECT = """
    SELECT cp.*,
           (SELECT COUNT(*) FROM characters c WHERE c.campaign_id = cp.id) AS character_count,
           (SELECT COUNT(*) FROM shops s WHERE s.campaign_id = cp.id) AS shop_count,
           (SELECT COUNT(*) FROM loot_pools l WHERE l.campaign_id = cp.id) AS loot_count,
           (SELECT COUNT(*) FROM campaign_members m WHERE m.campaign_id = cp.id) AS member_count
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
    def for_member(user_id):
        """Campañas (no archivadas) en las que está el jugador."""
        return get_db().execute(
            """SELECT cp.* FROM campaigns cp
               JOIN campaign_members m ON m.campaign_id = cp.id AND m.user_id = ?
               WHERE cp.archived = 0 ORDER BY cp.name, cp.id""",
            (user_id,),
        ).fetchall()

    @staticmethod
    def members(campaign_id):
        return get_db().execute(
            """SELECT u.id, u.username FROM campaign_members m JOIN users u ON u.id = m.user_id
               WHERE m.campaign_id = ? ORDER BY u.username""",
            (campaign_id,),
        ).fetchall()

    @staticmethod
    def is_member(campaign_id, user_id):
        return get_db().execute(
            "SELECT 1 FROM campaign_members WHERE campaign_id = ? AND user_id = ?", (campaign_id, user_id)
        ).fetchone() is not None

    @staticmethod
    def add_member(campaign_id, user_id):
        """Sin commit (se usa dentro de otras operaciones). Si ya era miembro, no hace nada."""
        get_db().execute(
            "INSERT INTO campaign_members (campaign_id, user_id) VALUES (?, ?) ON CONFLICT DO NOTHING",
            (campaign_id, user_id),
        )

    @staticmethod
    def by_code(code):
        code = normalize_code(code)
        if not code:
            return None
        return get_db().execute("SELECT * FROM campaigns WHERE join_code = ?", (code,)).fetchone()

    @staticmethod
    def join(user_id, code):
        """El jugador entra en la campaña del código. Devuelve (campaña, ya_era_miembro)."""
        campaign = Campaign.by_code(code)
        if campaign is None:
            raise RuleError("Ese código de campaña no es válido. Revísalo o pídeselo de nuevo al DM.")
        if campaign["archived"]:
            raise RuleError(f"La campaña «{campaign['name']}» está archivada.")
        already = Campaign.is_member(campaign["id"], user_id)
        if not already and not campaign["is_open"]:
            raise RuleError(f"«{campaign['name']}» no admite jugadores nuevos ahora mismo.")
        Campaign.add_member(campaign["id"], user_id)
        get_db().commit()
        return campaign, already

    @staticmethod
    def regenerate_code(campaign_id):
        """Nuevo código: el anterior deja de servir (quien ya estaba dentro, sigue)."""
        db = get_db()
        db.execute("UPDATE campaigns SET join_code = ? WHERE id = ?", (new_join_code(db), campaign_id))
        db.commit()

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
            "INSERT INTO campaigns (name, description, is_open, join_code) VALUES (?, ?, ?, ?)",
            (name, description, 1 if data.get("is_open") else 0, new_join_code(db)),
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
    def require(campaign_id, player_id=None):
        """Devuelve la campaña si se pueden crear personajes en ella; si no, RuleError.
        Con player_id (un jugador creando su personaje): debe ser miembro y estar abierta."""
        campaign = Campaign.get(campaign_id) if campaign_id else None
        if campaign is None:
            raise RuleError("Elige una campaña.")
        if campaign["archived"]:
            raise RuleError("Esa campaña está archivada.")
        if player_id is not None:
            if not Campaign.is_member(campaign["id"], player_id):
                raise RuleError("No estás en esa campaña. Únete con su código de campaña.")
            if not campaign["is_open"]:
                raise RuleError("Esa campaña no admite personajes nuevos. Pídeselo al DM.")
        return campaign
