from ..db import get_db
from ..text import LIKE_ESCAPE, like_prefix, like_terms, normalize
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
}
FLOAT_FIELDS = {"speed": 9.0}

_SELECT = """
    SELECT c.*, u.username AS owner, av.version AS avatar_version
    FROM characters c
    JOIN users u ON u.id = c.user_id
    LEFT JOIN character_avatars av ON av.character_id = c.id
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
    def search(q="", user_id=None, exclude_id=None, sort="name", page=1, per_page=PER_PAGE):
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
        if sort == "relevance" and q:
            order, order_params = "CASE WHEN c.search_name LIKE ?" + LIKE_ESCAPE + " THEN 0 ELSE 1 END, c.search_name, c.id", (like_prefix(q),)
        else:
            order, order_params = sort_sql(SORTS, sort, "name"), ()
        return paginate(_SELECT, where, params, order, page, per_page, order_params)

    @staticmethod
    def all():
        return get_db().execute(_SELECT + " ORDER BY c.name").fetchall()

    @staticmethod
    def for_user(user_id):
        return get_db().execute(
            _SELECT + " WHERE c.user_id = ? ORDER BY c.name", (user_id,)
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
        return clean

    @staticmethod
    def create(user_id, data):
        clean = Character._clean(data)
        cols = ", ".join(clean)
        marks = ", ".join("?" for _ in clean)
        db = get_db()
        character_id = db.insert(
            f"INSERT INTO characters (user_id, {cols}) VALUES (?, {marks})",
            (user_id, *clean.values()),
        )
        db.commit()
        return character_id

    @staticmethod
    def update(character_id, data):
        clean = Character._clean(data)
        sets = ", ".join(f"{key} = ?" for key in clean)
        db = get_db()
        db.execute(f"UPDATE characters SET {sets} WHERE id = ?", (*clean.values(), character_id))
        db.commit()

    @staticmethod
    def delete(character_id):
        db = get_db()
        db.execute("DELETE FROM characters WHERE id = ?", (character_id,))
        db.commit()
