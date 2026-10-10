from ..db import get_db, now_text
from ..text import LIKE_ESCAPE, like_prefix, like_terms, normalize
from . import rules
from .campaign import Campaign
from .errors import RuleError
from .listing import PER_PAGE, paginate, sort_sql

ABILITIES = [
    ("strength", "FUE"),
    ("dexterity", "DES"),
    ("constitution", "CON"),
    ("intelligence", "INT"),
    ("wisdom", "SAB"),
    ("charisma", "CAR"),
]

TEXT_FIELDS = ["race", "class_name", "background", "alignment", "notes"]
INT_FIELDS = {
    "level": 1,
    **{key: 10 for key, _ in ABILITIES},
    "hp_max": 10,
    "hp_current": 10,
    "armor_class": 10,
    "initiative_bonus": 0,
}
FLOAT_FIELDS = {"speed": 9.0}

_SELECT = """
    SELECT c.*, u.username AS owner, av.version AS avatar_version,
           cp.name AS campaign_name, cp.archived AS campaign_archived
    FROM characters c
    JOIN users u ON u.id = c.user_id
    LEFT JOIN character_avatars av ON av.character_id = c.id
    LEFT JOIN campaigns cp ON cp.id = c.campaign_id
"""

SORTS = {
    "name": ("Nombre", "c.search_name, c.id"),
    "level": ("Nivel (mayor primero)", "c.level DESC, c.search_name, c.id"),
    "owner": ("Jugador", "u.username, c.search_name, c.id"),
    "hp": ("PG actuales (menor primero)", "c.hp_current, c.search_name, c.id"),
    "recent": ("Creados recientemente", "c.id DESC"),
}


class Character:
    SORTS = SORTS

    @staticmethod
    def search(q="", user_id=None, exclude_id=None, campaign_id=None, sort="name", page=1, per_page=PER_PAGE):
        """Personajes filtrados (por nombre o jugador) y paginados.
        sort='relevance' pone primero los nombres que empiezan por q."""
        where, params = [], []
        for term in like_terms(q):  # cada palabra, en el nombre o en el jugador
            where.append("(c.search_name LIKE ?" + LIKE_ESCAPE + " OR LOWER(u.username) LIKE ?" + LIKE_ESCAPE + ")")
            params += [term, term]
        if user_id is not None:
            where.append("c.user_id = ?")
            params.append(user_id)
        if exclude_id is not None:
            where.append("c.id <> ?")
            params.append(exclude_id)
        if campaign_id is not None:
            where.append("c.campaign_id = ?")
            params.append(campaign_id)
        if sort == "relevance" and q:
            order, order_params = "CASE WHEN c.search_name LIKE ?" + LIKE_ESCAPE + " THEN 0 ELSE 1 END, c.search_name, c.id", (like_prefix(q),)
        else:
            order, order_params = sort_sql(SORTS, sort, "name"), ()
        return paginate(_SELECT, where, params, order, page, per_page, order_params)

    @staticmethod
    def for_user(user_id):
        """Todos los personajes del jugador, agrupados por campaña."""
        return get_db().execute(
            _SELECT + " WHERE c.user_id = ? ORDER BY cp.archived, cp.name, c.search_name", (user_id,)
        ).fetchall()

    @staticmethod
    def get(character_id):
        return get_db().execute(_SELECT + " WHERE c.id = ?", (character_id,)).fetchone()

    @staticmethod
    def _clean(data):
        name = (data.get("name") or "").strip()
        if not name:
            raise RuleError("El personaje necesita un nombre.")
        clean = {"name": name, "search_name": normalize(name)}
        for key in TEXT_FIELDS:
            clean[key] = (data.get(key) or "").strip()
        for key, default in INT_FIELDS.items():
            try:
                clean[key] = int(data.get(key, default))
            except (TypeError, ValueError):
                clean[key] = default
        for key, default in FLOAT_FIELDS.items():
            try:
                clean[key] = float(str(data.get(key, default)).replace(",", "."))
            except ValueError:
                clean[key] = default
        # Competencia: vacío = automática según el nivel
        try:
            clean["proficiency_bonus"] = max(0, min(int(data.get("proficiency_bonus")), 10))
        except (TypeError, ValueError):
            clean["proficiency_bonus"] = None
        return clean

    # --- Competencias en salvaciones y habilidades -------------------------------------------

    @staticmethod
    def proficiencies(character_id):
        """{("save"|"skill", clave): 1 competencia | 2 pericia}"""
        rows = get_db().execute(
            "SELECT kind, name, level FROM character_proficiencies WHERE character_id = ?", (character_id,)
        ).fetchall()
        return {(r["kind"], r["name"]): r["level"] for r in rows}

    @staticmethod
    def _save_proficiencies(character_id, data):
        """Sustituye las competencias con las del formulario (save_<car>=1, skill_<hab>=0/1/2). Sin commit."""
        rows = [("save", key, rules.PROFICIENT) for key in rules.SAVE_KEYS if data.get(f"save_{key}")]
        for key in rules.SKILL_KEYS:
            try:
                level = int(data.get(f"skill_{key}") or 0)
            except ValueError:
                level = 0
            if level in (rules.PROFICIENT, rules.EXPERTISE):
                rows.append(("skill", key, level))
        db = get_db()
        db.execute("DELETE FROM character_proficiencies WHERE character_id = ?", (character_id,))
        for kind, name, level in rows:
            db.execute(
                "INSERT INTO character_proficiencies (character_id, kind, name, level) VALUES (?, ?, ?, ?)",
                (character_id, kind, name, level),
            )

    # --- Inspiración ---------------------------------------------------------------------------

    @staticmethod
    def change_inspiration(character_id, delta):
        """Suma o resta puntos de inspiración (nunca por debajo de 0)."""
        character = Character.get(character_id)
        if delta < 0 and character["inspiration"] < -delta:
            raise RuleError("No te quedan puntos de inspiración.")
        db = get_db()
        db.execute("UPDATE characters SET inspiration = inspiration + ? WHERE id = ?", (delta, character_id))
        db.commit()
        return character["inspiration"] + delta

    @staticmethod
    def create(user_id, data, campaign_id, for_player=False):
        """Crea el personaje en una campaña (los jugadores, solo en campañas abiertas)."""
        clean = Character._clean(data)
        clean["campaign_id"] = Campaign.require(campaign_id, player_id=user_id if for_player else None)["id"]
        cols = ", ".join(clean)
        marks = ", ".join("?" for _ in clean)
        db = get_db()
        character_id = db.insert(
            f"INSERT INTO characters (user_id, {cols}) VALUES (?, {marks})",
            (user_id, *clean.values()),
        )
        Campaign.add_member(clean["campaign_id"], user_id)  # su dueño pasa a estar en la campaña
        Character._save_proficiencies(character_id, data)
        db.commit()
        return character_id

    @staticmethod
    def update(character_id, data, campaign_id=None):
        """Actualiza la ficha. Con campaign_id (solo el DM) mueve el personaje de campaña:
        sus intercambios pendientes se cancelan, porque el otro personaje ya no está en su mundo."""
        clean = Character._clean(data)
        current = Character.get(character_id)
        moving = campaign_id is not None and current is not None and campaign_id != current["campaign_id"]
        if moving:
            clean["campaign_id"] = Campaign.require(campaign_id)["id"]
        sets = ", ".join(f"{key} = ?" for key in clean)
        db = get_db()
        db.execute(f"UPDATE characters SET {sets} WHERE id = ?", (*clean.values(), character_id))
        Character._save_proficiencies(character_id, data)
        if moving:
            Campaign.add_member(clean["campaign_id"], current["user_id"])
            db.execute(
                """UPDATE trades SET status = 'cancelled', resolved_at = ?
                   WHERE status = 'pending' AND (from_character_id = ? OR to_character_id = ?)""",
                (now_text(), character_id, character_id),
            )
        db.commit()
        return moving

    @staticmethod
    def delete(character_id):
        db = get_db()
        db.execute("DELETE FROM characters WHERE id = ?", (character_id,))
        db.commit()
