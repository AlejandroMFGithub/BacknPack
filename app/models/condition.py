from ..db import get_db
from ..text import distances
from .errors import RuleError

KINDS = {"buff": "Bufo", "curse": "Maldición", "condition": "Estado"}

# Estados del Reglamento Básico de 5e, para autocompletar
PRESETS = [
    "Agarrado", "Apresado", "Asustado", "Aturdido", "Cegado", "Derribado",
    "Ensordecido", "Envenenado", "Hechizado", "Incapacitado", "Inconsciente",
    "Invisible", "Paralizado", "Petrificado", "Agotamiento (nivel 1)",
    "Bendición", "Inspiración bardica", "Escudo de fe", "Prisa",
]


class Condition:
    @staticmethod
    def for_character(character_id, include_hidden=False):
        sql = "SELECT * FROM conditions WHERE character_id = ?"
        if not include_hidden:
            sql += " AND visible = 1"
        sql += " ORDER BY kind, name"
        return get_db().execute(sql, (character_id,)).fetchall()

    @staticmethod
    def get(condition_id):
        return get_db().execute(
            "SELECT * FROM conditions WHERE id = ?", (condition_id,)
        ).fetchone()

    @staticmethod
    def create(character_id, data):
        name = distances((data.get("name") or "").strip())
        kind = data.get("kind")
        if not name:
            raise RuleError("El efecto necesita un nombre.")
        if kind not in KINDS:
            raise RuleError("Tipo de efecto no válido.")
        db = get_db()
        condition_id = db.insert(
            """INSERT INTO conditions (character_id, name, kind, description, duration, visible)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                character_id, name, kind,
                distances((data.get("description") or "").strip()),
                distances((data.get("duration") or "").strip()),
                1 if data.get("visible") else 0,
            ),
        )
        db.commit()
        return condition_id

    @staticmethod
    def delete(condition_id):
        db = get_db()
        db.execute("DELETE FROM conditions WHERE id = ?", (condition_id,))
        db.commit()

    @staticmethod
    def toggle_visible(condition_id):
        db = get_db()
        db.execute("UPDATE conditions SET visible = 1 - visible WHERE id = ?", (condition_id,))
        db.commit()
