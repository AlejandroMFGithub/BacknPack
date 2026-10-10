from ..db import get_db
from .errors import RuleError

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
    SELECT c.*, u.username AS owner
    FROM characters c JOIN users u ON u.id = c.user_id
"""


class Character:
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
        clean = {"name": name}
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
