from ..db import get_db, now_text, transaction
from ..text import LIKE_ESCAPE, distances, like_prefix, like_terms, normalize
from . import rules
from .campaign import Campaign
from .dnd_class import DndClass
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

TEXT_FIELDS = ["race", "background", "alignment", "notes"]  # la clase la resuelve DndClass.resolve
INT_FIELDS = {
    "level": 1,
    **{key: 10 for key, _ in ABILITIES},
    "hp_max": 10,
    "hp_current": 10,
    "hp_temp": 0,
    "armor_class": 10,
    "initiative_bonus": 0,
}
FLOAT_FIELDS = {"speed": 30.0}  # velocidad en pies (30 ft = 6 casillas)

_SELECT = """
    SELECT c.*, u.username AS owner, av.version AS avatar_version,
           cp.name AS campaign_name, cp.archived AS campaign_archived,
           cl.code AS class_code, cl.subclass_level, cl.proficiencies AS class_proficiencies,
           sc.progress AS subclass_progress
    FROM characters c
    JOIN users u ON u.id = c.user_id
    LEFT JOIN character_avatars av ON av.character_id = c.id
    LEFT JOIN campaigns cp ON cp.id = c.campaign_id
    LEFT JOIN classes cl ON cl.id = c.class_id
    LEFT JOIN subclasses sc ON sc.id = c.subclass_id
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
    def search(q="", user_id=None, exclude_id=None, campaign_id=None, sort="name", page=1, per_page=PER_PAGE,
               visible_to=None):
        """Personajes filtrados (por nombre o jugador) y paginados.
        sort='relevance' pone primero los nombres que empiezan por q.
        visible_to=<user_id>: sin los personajes ocultos de otros jugadores."""
        where, params = [], []
        if visible_to is not None:
            where.append("(c.hidden_by IS NULL OR c.user_id = ?)")
            params.append(visible_to)
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
        class_cols, default_saves = DndClass.resolve(data)
        clean.update(class_cols)
        for key in TEXT_FIELDS:
            clean[key] = (data.get(key) or "").strip()
        clean["notes"] = distances(clean["notes"])
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
        return clean, default_saves

    # --- Competencias en salvaciones y habilidades -------------------------------------------

    @staticmethod
    def proficiencies(character_id):
        """{("save"|"skill", clave): 1 competencia | 2 pericia}"""
        rows = get_db().execute(
            "SELECT kind, name, level FROM character_proficiencies WHERE character_id = ?", (character_id,)
        ).fetchall()
        return {(r["kind"], r["name"]): r["level"] for r in rows}

    @staticmethod
    def _save_proficiencies(character_id, data, default_saves=()):
        """Sustituye las competencias con las del formulario (save_<car>=1, skill_<hab>=0/1/2). Sin commit.
        Si el formulario no trae el bloque de competencias, las salvaciones son las de su clase."""
        saves = [key for key in rules.SAVE_KEYS if data.get(f"save_{key}")]
        if not data.get("profs_form") and not saves:
            saves = list(default_saves)
        rows = [("save", key, rules.PROFICIENT) for key in saves]
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

    # --- Puntos de golpe en combate --------------------------------------------------------------

    HP_OPS = ("damage", "heal", "temp_add", "temp_sub")

    @staticmethod
    def change_hp(character_id, op, amount, hp_max):
        """Cambia los PG con los botones de la ficha. hp_max: el máximo ya calculado (con efectos).

        damage: el daño gasta antes los PG temporales y luego los actuales (mínimo 0).
        heal: cura hasta el máximo. temp_add / temp_sub: suma o resta PG temporales (mínimo 0).
        """
        if op not in Character.HP_OPS:
            raise RuleError("Operación de PG no válida.")
        amount = max(1, min(int(amount), 999))
        with transaction() as db:
            row = db.execute("SELECT hp_current, hp_temp FROM characters WHERE id = ?", (character_id,)).fetchone()
            current, temp = row["hp_current"], row["hp_temp"]
            if op == "damage":
                absorbed = min(temp, amount)
                temp -= absorbed
                current = max(0, current - (amount - absorbed))
            elif op == "heal":
                current = max(current, min(hp_max, current + amount))  # nunca baja si ya estaba por encima
            elif op == "temp_add":
                temp += amount
            else:
                temp = max(0, temp - amount)
            db.execute("UPDATE characters SET hp_current = ?, hp_temp = ? WHERE id = ?", (current, temp, character_id))
        return {"hp_current": current, "hp_temp": temp, "hp_max": hp_max}

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
        clean, default_saves = Character._clean(data)
        clean["campaign_id"] = Campaign.require(campaign_id, player_id=user_id if for_player else None)["id"]
        cols = ", ".join(clean)
        marks = ", ".join("?" for _ in clean)
        db = get_db()
        character_id = db.insert(
            f"INSERT INTO characters (user_id, {cols}) VALUES (?, {marks})",
            (user_id, *clean.values()),
        )
        Campaign.add_member(clean["campaign_id"], user_id)  # su dueño pasa a estar en la campaña
        Character._save_proficiencies(character_id, data, default_saves)
        db.commit()
        return character_id

    @staticmethod
    def update(character_id, data, campaign_id=None):
        """Actualiza la ficha. Con campaign_id (solo el DM) mueve el personaje de campaña:
        sus intercambios pendientes se cancelan, porque el otro personaje ya no está en su mundo."""
        clean, default_saves = Character._clean(data)
        current = Character.get(character_id)
        moving = campaign_id is not None and current is not None and campaign_id != current["campaign_id"]
        if moving:
            clean["campaign_id"] = Campaign.require(campaign_id)["id"]
        sets = ", ".join(f"{key} = ?" for key in clean)
        db = get_db()
        db.execute(f"UPDATE characters SET {sets} WHERE id = ?", (*clean.values(), character_id))
        Character._save_proficiencies(character_id, data, default_saves)
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
    def is_hidden_from(character, user_id):
        """¿Debe dejar de verlo este jugador? (sus propios personajes los ve siempre)"""
        return character["hidden_by"] is not None and character["user_id"] != user_id

    @staticmethod
    def set_hidden(character_id, hide, by_dm):
        """Oculta o muestra un personaje al resto de jugadores.
        Lo que oculta el DM solo lo puede volver a mostrar el DM."""
        character = Character.get(character_id)
        if hide:
            hidden_by = "dm" if by_dm or character["hidden_by"] == "dm" else "player"
        else:
            if character["hidden_by"] == "dm" and not by_dm:
                raise RuleError("El DM ha ocultado a este personaje: solo el DM puede volver a mostrarlo.")
            hidden_by = None
        db = get_db()
        db.execute("UPDATE characters SET hidden_by = ? WHERE id = ?", (hidden_by, character_id))
        db.commit()
        return hidden_by

    @staticmethod
    def delete(character_id):
        db = get_db()
        db.execute("DELETE FROM characters WHERE id = ?", (character_id,))
        db.commit()
