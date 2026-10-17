"""Clases y subclases: las oficiales (se cargan con la migración 15) y las homebrew del DM.

Al elegir clase y subclase para un personaje se copian a su ficha unos valores por defecto
(dado de golpe, salvaciones, tipo de lanzador, característica mágica y forma de preparar
conjuros) que luego el jugador y el DM pueden cambiar a mano.
"""
from ..db import get_db
from ..text import normalize
from .class_data import CASTER_TYPES, HIT_DICE, SPELL_PREP
from .errors import RuleError
from .rules import ABILITIES, SAVE_KEYS

ABILITY_NAMES = {key: name for key, _, name in ABILITIES}


def _choice(value, allowed, default=None):
    return value if value in allowed else default


class DndClass:
    # --- Consultas -------------------------------------------------------------------------

    @staticmethod
    def all():
        """Oficiales primero y luego las homebrew, cada grupo por nombre."""
        return get_db().execute("SELECT * FROM classes ORDER BY official DESC, search_name").fetchall()

    @staticmethod
    def get(class_id):
        return get_db().execute("SELECT * FROM classes WHERE id = ?", (class_id,)).fetchone()

    @staticmethod
    def subclasses(class_id=None):
        sql = "SELECT * FROM subclasses"
        params = ()
        if class_id is not None:
            sql += " WHERE class_id = ?"
            params = (class_id,)
        return get_db().execute(sql + " ORDER BY official DESC, name", params).fetchall()

    @staticmethod
    def get_subclass(subclass_id):
        return get_db().execute("SELECT * FROM subclasses WHERE id = ?", (subclass_id,)).fetchone()

    @staticmethod
    def defaults(cls, sub=None):
        """Valores que la clase (y su subclase, si cambia la magia) ponen en la ficha."""
        if cls is None:
            return {"hit_die": None, "saves": [], "caster": "none", "spell_ability": None, "spell_prep": None}
        pick = lambda key: (sub[key] if sub is not None and sub[key] else cls[key])  # noqa: E731
        return {
            "hit_die": cls["hit_die"],
            "saves": [s for s in (cls["saves"] or "").split(",") if s],
            "caster": pick("caster") or "none",
            "spell_ability": pick("spell_ability"),
            "spell_prep": pick("spell_prep"),
        }

    @staticmethod
    def catalog():
        """Todo lo que necesita el formulario de personaje (en JSON) para rellenar los valores por defecto."""
        subs = {}
        for s in DndClass.subclasses():
            subs.setdefault(s["class_id"], []).append(s)
        result = []
        for c in DndClass.all():
            result.append({
                "id": c["id"], "name": c["name"], "official": bool(c["official"]),
                "subclass_level": c["subclass_level"], "proficiencies": c["proficiencies"] or "",
                "defaults": DndClass.defaults(c),
                "subclasses": [{"id": s["id"], "name": s["name"], "defaults": DndClass.defaults(c, s)}
                               for s in subs.get(c["id"], [])],
            })
        return result

    # --- Elegir clase en la ficha ------------------------------------------------------------

    @staticmethod
    def resolve(data):
        """Columnas de clase de un personaje a partir del formulario.

        class_id: id de una clase, «custom» (nombre escrito en class_name) o vacío.
        Los campos de magia y dado que no vengan en el formulario toman el valor de la clase.
        Devuelve (columnas, salvaciones por defecto de la clase).
        """
        choice = str(data.get("class_id") or "").strip()
        cls = sub = None
        if choice.isdigit():
            cls = DndClass.get(int(choice))
            if cls is None:
                raise RuleError("Esa clase no existe.")
        elif "class_id" not in data and data.get("class_name"):
            # Formularios antiguos y datos de ejemplo: la clase por su nombre («Exploradora»)
            from ..migrations import class_matching
            cls = class_matching(data.get("class_name"), DndClass.all())

        sub_choice = str(data.get("subclass_id") or "").strip()
        subclass_name = (data.get("subclass_name") or "").strip()
        if sub_choice.isdigit():
            sub = DndClass.get_subclass(int(sub_choice))
            if sub is None or cls is None or sub["class_id"] != cls["id"]:
                raise RuleError("Esa subclase no es de la clase elegida.")
            subclass_name = sub["name"]
        elif sub_choice != "custom" and "subclass_id" in data:
            subclass_name = ""

        defaults = DndClass.defaults(cls, sub)
        cols = {
            "class_id": cls["id"] if cls else None,
            "class_name": cls["name"] if cls else (data.get("class_name") or "").strip(),
            "subclass_id": sub["id"] if sub else None,
            "subclass_name": subclass_name or None,
        }
        try:
            die = int(data["hit_die"]) if data.get("hit_die") else None
        except ValueError:
            die = None
        cols["hit_die"] = _choice(die, HIT_DICE) if "hit_die" in data else defaults["hit_die"]
        cols["caster"] = (_choice(data.get("caster"), CASTER_TYPES, "none") if "caster" in data
                          else defaults["caster"])
        cols["spell_ability"] = (_choice(data.get("spell_ability"), SAVE_KEYS) if "spell_ability" in data
                                 else defaults["spell_ability"])
        cols["spell_prep"] = (_choice(data.get("spell_prep"), SPELL_PREP) if "spell_prep" in data
                              else defaults["spell_prep"])
        return cols, defaults["saves"]

    # --- Homebrew (las gestiona el DM) --------------------------------------------------------

    @staticmethod
    def _clean(data):
        name = (data.get("name") or "").strip()
        if not name:
            raise RuleError("La clase necesita un nombre.")
        try:
            die = int(data.get("hit_die") or 8)
        except ValueError:
            die = 8
        try:
            sub_level = max(1, min(int(data.get("subclass_level") or 3), 20))
        except ValueError:
            sub_level = 3
        caster = _choice(data.get("caster"), CASTER_TYPES, "none")
        ability = _choice(data.get("spell_ability"), SAVE_KEYS)
        if caster != "none" and ability is None:
            raise RuleError("Una clase con conjuros necesita su característica mágica.")
        saves = [key for key in SAVE_KEYS if data.get(f"save_{key}")]
        return {
            "name": name, "search_name": normalize(name), "hit_die": _choice(die, HIT_DICE, 8),
            "saves": ",".join(k for k, _, _ in ABILITIES if k in saves),
            "caster": caster, "spell_ability": ability if caster != "none" else None,
            "spell_prep": _choice(data.get("spell_prep"), SPELL_PREP, "known") if caster != "none" else None,
            "subclass_level": sub_level,
            "proficiencies": (data.get("proficiencies") or "").strip(),
            "description": (data.get("description") or "").strip(),
        }

    @staticmethod
    def create(data):
        clean = DndClass._clean(data)
        db = get_db()
        class_id = db.insert(
            f"INSERT INTO classes ({', '.join(clean)}) VALUES ({', '.join('?' for _ in clean)})",
            tuple(clean.values()),
        )
        db.commit()
        return class_id

    @staticmethod
    def update(class_id, data):
        clean = DndClass._clean(data)
        db = get_db()
        db.execute(f"UPDATE classes SET {', '.join(f'{k} = ?' for k in clean)} WHERE id = ?",
                   (*clean.values(), class_id))
        db.commit()

    @staticmethod
    def delete(class_id):
        cls = DndClass.get(class_id)
        if cls is None:
            return
        if cls["official"]:
            raise RuleError("Las clases oficiales no se pueden borrar.")
        db = get_db()
        db.execute("DELETE FROM classes WHERE id = ?", (class_id,))  # los personajes conservan el nombre
        db.commit()

    @staticmethod
    def add_subclass(class_id, data):
        cls = DndClass.get(class_id)
        if cls is None:
            raise RuleError("Esa clase no existe.")
        name = (data.get("name") or "").strip()
        if not name:
            raise RuleError("La subclase necesita un nombre.")
        caster = _choice(data.get("caster"), CASTER_TYPES)  # vacío = la de la clase
        ability = _choice(data.get("spell_ability"), SAVE_KEYS)
        if caster not in (None, "none") and ability is None and not cls["spell_ability"]:
            raise RuleError("Una subclase con conjuros necesita su característica mágica.")
        db = get_db()
        sub_id = db.insert(
            """INSERT INTO subclasses (class_id, name, caster, spell_ability, spell_prep, description)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (class_id, name, caster, ability,
             _choice(data.get("spell_prep"), SPELL_PREP) if caster not in (None, "none") else None,
             (data.get("description") or "").strip()),
        )
        db.commit()
        return sub_id

    @staticmethod
    def delete_subclass(subclass_id):
        sub = DndClass.get_subclass(subclass_id)
        if sub is None:
            return
        if sub["official"]:
            raise RuleError("Las subclases oficiales no se pueden borrar.")
        db = get_db()
        db.execute("DELETE FROM subclasses WHERE id = ?", (subclass_id,))
        db.commit()
