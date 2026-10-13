"""Bufos, maldiciones y estados de un personaje.

Se pueden activar y desactivar (en combate van y vienen: furia, concentración…); solo los
activos modifican la ficha. El jugador crea y maneja los de su personaje, salvo los que el
DM ha marcado como fijos (locked) o le oculta: esos solo los toca el DM.
"""
from ..db import get_db
from ..text import distances
from . import effects
from .activity_log import ActivityLog
from .errors import RuleError

KINDS = {"buff": "Bufo", "curse": "Maldición", "condition": "Estado"}

# Estados del Reglamento Básico de 5e, para autocompletar
PRESETS = [
    "Agarrado", "Apresado", "Asustado", "Aturdido", "Cegado", "Derribado",
    "Ensordecido", "Envenenado", "Hechizado", "Incapacitado", "Inconsciente",
    "Invisible", "Paralizado", "Petrificado", "Agotamiento (nivel 1)",
    "Agotamiento (nivel 2)", "Agotamiento (nivel 5)",
    "Bendición", "Inspiración bardica", "Escudo de fe", "Prisa", "Ralentizar", "Paso largo",
]


class Condition:
    @staticmethod
    def for_character(character_id, include_hidden=False):
        sql = "SELECT * FROM conditions WHERE character_id = ?"
        if not include_hidden:
            sql += " AND visible = 1"
        sql += " ORDER BY active DESC, kind, name"
        return get_db().execute(sql, (character_id,)).fetchall()

    @staticmethod
    def get(condition_id):
        return get_db().execute(
            "SELECT * FROM conditions WHERE id = ?", (condition_id,)
        ).fetchone()

    @staticmethod
    def player_can_change(condition):
        """El jugador maneja los efectos de su personaje que ve y que no son fijos."""
        return bool(condition["visible"]) and not condition["locked"]

    @staticmethod
    def _clean(data, by_dm):
        name = distances((data.get("name") or "").strip())
        kind = data.get("kind")
        if not name:
            raise RuleError("El efecto necesita un nombre.")
        if kind not in KINDS:
            raise RuleError("Tipo de efecto no válido.")
        return {
            "name": name,
            "kind": kind,
            "description": distances((data.get("description") or "").strip()),
            "duration": distances((data.get("duration") or "").strip()),
            "effects": effects.from_form(data),
            # Solo el DM decide qué se oculta y qué es fijo
            "visible": (1 if data.get("visible") else 0) if by_dm else 1,
            "locked": (1 if data.get("locked") else 0) if by_dm else 0,
        }

    @staticmethod
    def create(character_id, data, by_dm=True):
        clean = Condition._clean(data, by_dm)
        if not clean["effects"]:  # estados del reglamento: su efecto se pone solo
            clean["effects"] = effects.clean(effects.CONDITION_PRESETS.get(clean["name"], []))
        clean["effects"] = effects.dumps(clean["effects"])
        db = get_db()
        condition_id = db.insert(
            f"""INSERT INTO conditions (character_id, {', '.join(clean)})
                VALUES (?, {', '.join('?' for _ in clean)})""",
            (character_id, *clean.values()),
        )
        db.commit()
        return condition_id

    @staticmethod
    def update(condition_id, data, by_dm=True):
        condition = Condition.get(condition_id)
        clean = Condition._clean(data, by_dm)
        clean["effects"] = effects.dumps(clean["effects"])
        if not by_dm:  # el jugador no cambia lo que decide el DM
            del clean["visible"], clean["locked"]
        db = get_db()
        db.execute(
            f"UPDATE conditions SET {', '.join(f'{k} = ?' for k in clean)} WHERE id = ?",
            (*clean.values(), condition_id),
        )
        if condition["visible"] and condition["name"] != clean["name"]:
            ActivityLog.add(condition["character_id"], f"«{condition['name']}» pasa a llamarse «{clean['name']}»")
        db.commit()

    @staticmethod
    def toggle_active(condition_id):
        """Activa o desactiva el efecto. Devuelve si queda activo."""
        condition = Condition.get(condition_id)
        active = 0 if condition["active"] else 1
        db = get_db()
        db.execute("UPDATE conditions SET active = ? WHERE id = ?", (active, condition_id))
        if condition["visible"]:
            ActivityLog.add(condition["character_id"], ("Activa" if active else "Desactiva") + f" «{condition['name']}»")
        db.commit()
        return bool(active)

    @staticmethod
    def toggle_locked(condition_id):
        db = get_db()
        db.execute("UPDATE conditions SET locked = 1 - locked WHERE id = ?", (condition_id,))
        db.commit()

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
