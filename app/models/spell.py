"""Conjuros: el catálogo (oficiales + homebrew del DM) y la magia de cada personaje.

Un personaje tiene la pestaña de conjuros si su clase lanza conjuros, si tiene alguno
apuntado (por raza, dote…) o si lleva equipado un objeto que concede conjuros.
"""
from ..db import get_db, transaction
from ..text import LIKE_ESCAPE, like_prefix, like_terms, normalize
from . import class_data, rules
from .activity_log import ActivityLog
from .errors import RuleError
from .listing import PER_PAGE, paginate, sort_sql

LEVEL_NAMES = {0: "Trucos", **{n: f"Nivel {n}" for n in range(1, 10)}}

SORTS = {
    "level": ("Nivel", "level, search_name, id"),
    "name": ("Nombre", "search_name, id"),
    "school": ("Escuela", "school, level, search_name, id"),
}


def _int(value, default=0, low=None, high=None):
    try:
        value = int(value)
    except (TypeError, ValueError):
        return default
    if low is not None:
        value = max(low, value)
    if high is not None:
        value = min(high, value)
    return value


class Spell:
    SORTS = SORTS

    @staticmethod
    def search(q="", level="", school="", class_code="", sort="level", page=1, per_page=PER_PAGE):
        where, params = [], []
        for term in like_terms(q):
            where.append("search_name LIKE ?" + LIKE_ESCAPE)
            params.append(term)
        if str(level).isdigit():
            where.append("level = ?")
            params.append(int(level))
        if school:
            where.append("school = ?")
            params.append(school)
        if class_code:
            where.append("classes LIKE ?")
            params.append(f"% {class_code} %")
        if sort == "relevance" and q:
            order, order_params = ("CASE WHEN search_name LIKE ?" + LIKE_ESCAPE + " THEN 0 ELSE 1 END, level, search_name, id",
                                   (like_prefix(q),))
        else:
            order, order_params = sort_sql(SORTS, sort, "level"), ()
        return paginate("SELECT * FROM spells", where, params, order, page, per_page, order_params)

    @staticmethod
    def get(spell_id):
        return get_db().execute("SELECT * FROM spells WHERE id = ?", (spell_id,)).fetchone()

    @staticmethod
    def _clean(data):
        name = (data.get("name") or "").strip()
        if not name:
            raise RuleError("El conjuro necesita un nombre.")
        codes = {c["code"] for c in get_db().execute("SELECT code FROM classes WHERE code IS NOT NULL").fetchall()}
        classes = [c for c in (data.getlist("classes") if hasattr(data, "getlist") else data.get("classes") or [])
                   if c in codes]
        return {
            "name": name, "search_name": normalize(name),
            "level": _int(data.get("level"), 0, 0, 9),
            "school": data.get("school") if data.get("school") in class_data.SCHOOLS else None,
            "casting_time": (data.get("casting_time") or "").strip() or "1 acción",
            "spell_range": (data.get("spell_range") or "").strip(),
            "components": (data.get("components") or "").strip(),
            "duration": (data.get("duration") or "").strip() or "Instantánea",
            "concentration": 1 if data.get("concentration") else 0,
            "ritual": 1 if data.get("ritual") else 0,
            "classes": f" {' '.join(classes)} " if classes else None,
            "description": (data.get("description") or "").strip(),
        }

    @staticmethod
    def create(data):
        clean = Spell._clean(data)
        db = get_db()
        spell_id = db.insert(
            f"INSERT INTO spells ({', '.join(clean)}) VALUES ({', '.join('?' for _ in clean)})",
            tuple(clean.values()),
        )
        db.commit()
        return spell_id

    @staticmethod
    def update(spell_id, data):
        clean = Spell._clean(data)
        db = get_db()
        db.execute(f"UPDATE spells SET {', '.join(f'{k} = ?' for k in clean)} WHERE id = ?",
                   (*clean.values(), spell_id))
        db.commit()

    @staticmethod
    def delete(spell_id):
        db = get_db()
        db.execute("DELETE FROM spells WHERE id = ?", (spell_id,))
        db.commit()

    # --- Conjuros que concede un objeto del catálogo (mientras se lleva equipado) ----------------

    @staticmethod
    def for_item(item_id):
        return get_db().execute(
            """SELECT s.* FROM item_spells x JOIN spells s ON s.id = x.spell_id
               WHERE x.item_id = ? ORDER BY s.level, s.search_name""", (item_id,),
        ).fetchall()

    @staticmethod
    def add_to_item(item_id, spell_id):
        if Spell.get(spell_id) is None:
            raise RuleError("Ese conjuro no existe.")
        db = get_db()
        if not db.execute("SELECT 1 FROM item_spells WHERE item_id = ? AND spell_id = ?", (item_id, spell_id)).fetchone():
            db.execute("INSERT INTO item_spells (item_id, spell_id) VALUES (?, ?)", (item_id, spell_id))
        db.commit()

    @staticmethod
    def remove_from_item(item_id, spell_id):
        db = get_db()
        db.execute("DELETE FROM item_spells WHERE item_id = ? AND spell_id = ?", (item_id, spell_id))
        db.commit()


class Magic:
    """La magia de un personaje: conjuros apuntados, espacios y lanzamientos."""

    @staticmethod
    def spells(character_id):
        return get_db().execute(
            """SELECT cs.id AS entry_id, cs.source, cs.prepared, cs.always_prepared, cs.notes, s.*
               FROM character_spells cs JOIN spells s ON s.id = cs.spell_id
               WHERE cs.character_id = ? ORDER BY s.level, s.search_name""", (character_id,),
        ).fetchall()

    @staticmethod
    def entry(character_id, entry_id):
        row = get_db().execute(
            """SELECT cs.id AS entry_id, cs.character_id, cs.prepared, cs.always_prepared, s.*
               FROM character_spells cs JOIN spells s ON s.id = cs.spell_id
               WHERE cs.id = ?""", (entry_id,),
        ).fetchone()
        return row if row is not None and row["character_id"] == character_id else None

    @staticmethod
    def item_spells(character_id, include_hidden=False):
        """Conjuros de los objetos equipados: (conjuro, objeto). Los objetos ocultos solo los ve el DM."""
        sql = """SELECT s.*, i.name AS item_name, ii.visible AS item_visible
                 FROM inventory_items ii JOIN items i ON i.id = ii.item_id
                 JOIN item_spells x ON x.item_id = i.id JOIN spells s ON s.id = x.spell_id
                 WHERE ii.character_id = ? AND ii.equipped = 1"""
        if not include_hidden:
            sql += " AND ii.visible = 1"
        return get_db().execute(sql + " ORDER BY s.level, s.search_name", (character_id,)).fetchall()

    @staticmethod
    def has_magic(character, include_hidden=False):
        if (character["caster"] or "none") != "none" or character["spell_ability"]:
            return True
        db = get_db()
        if db.execute("SELECT 1 FROM character_spells WHERE character_id = ? LIMIT 1", (character["id"],)).fetchone():
            return True
        return bool(Magic.item_spells(character["id"], include_hidden))

    # --- Conjuros apuntados -------------------------------------------------------------------

    @staticmethod
    def add(character_id, spell_id, source="class", always_prepared=False):
        spell = Spell.get(spell_id)
        if spell is None:
            raise RuleError("Ese conjuro no existe.")
        source = source if source in class_data.SPELL_SOURCES else "other"
        db = get_db()
        if db.execute("SELECT 1 FROM character_spells WHERE character_id = ? AND spell_id = ?",
                      (character_id, spell_id)).fetchone():
            raise RuleError(f"Ya tiene «{spell['name']}» en su lista.")
        db.insert(
            """INSERT INTO character_spells (character_id, spell_id, source, prepared, always_prepared)
               VALUES (?, ?, ?, ?, ?)""",
            (character_id, spell_id, source, 1 if always_prepared else 0, 1 if always_prepared else 0),
        )
        db.commit()
        return spell

    @staticmethod
    def remove(entry_id):
        db = get_db()
        db.execute("DELETE FROM character_spells WHERE id = ?", (entry_id,))
        db.commit()

    @staticmethod
    def toggle_prepared(entry_id):
        db = get_db()
        db.execute("UPDATE character_spells SET prepared = 1 - prepared WHERE id = ? AND always_prepared = 0",
                   (entry_id,))
        db.commit()

    @staticmethod
    def toggle_always(entry_id):
        """Siempre preparado (conjuros de dominio, de juramento…): no cuenta para el máximo."""
        db = get_db()
        db.execute("""UPDATE character_spells SET always_prepared = 1 - always_prepared,
                      prepared = CASE WHEN always_prepared = 0 THEN 1 ELSE prepared END WHERE id = ?""",
                   (entry_id,))
        db.commit()

    # --- Espacios de conjuro ------------------------------------------------------------------

    @staticmethod
    def _slot_rows(character_id):
        rows = get_db().execute(
            "SELECT slot, used, max_override FROM character_spell_slots WHERE character_id = ?", (character_id,)
        ).fetchall()
        return {r["slot"]: r for r in rows}

    @staticmethod
    def slots(character):
        """[{key, label, level, max, base, used, overridden}] con los espacios que tiene (o se le han dado)."""
        caster = character["caster"] or "none"
        stored = Magic._slot_rows(character["id"])
        base = {} if caster == "pact" else class_data.spell_slots(caster, character["level"])
        result = []
        for level in range(1, 10):
            key = str(level)
            row = stored.get(key)
            override = row["max_override"] if row is not None else None
            total = override if override is not None else base.get(level, 0)
            if total or base.get(level):
                result.append({"key": key, "label": f"Nivel {level}", "level": level, "max": total,
                               "base": base.get(level, 0), "used": min(row["used"], total) if row else 0,
                               "overridden": override is not None})
        pact_count, pact_level = class_data.pact_slots(character["level"])
        row = stored.get("pact")
        pact_base = pact_count if caster == "pact" else 0
        override = row["max_override"] if row is not None else None
        total = override if override is not None else pact_base
        if total:
            result.append({"key": "pact", "label": f"Pacto (nivel {pact_level})", "level": pact_level,
                           "max": total, "base": pact_base, "used": min(row["used"], total) if row else 0,
                           "overridden": override is not None})
        return result

    @staticmethod
    def _set_used(character_id, key, used):
        db = get_db()
        if db.execute("SELECT 1 FROM character_spell_slots WHERE character_id = ? AND slot = ?",
                      (character_id, key)).fetchone():
            db.execute("UPDATE character_spell_slots SET used = ? WHERE character_id = ? AND slot = ?",
                       (used, character_id, key))
        else:
            db.execute("INSERT INTO character_spell_slots (character_id, slot, used) VALUES (?, ?, ?)",
                       (character_id, key, used))

    @staticmethod
    def change_slot(character, key, delta):
        """Gasta (+1) o recupera (−1) un espacio."""
        slot = next((s for s in Magic.slots(character) if s["key"] == key), None)
        if slot is None:
            raise RuleError("No tiene espacios de ese nivel.")
        used = slot["used"] + delta
        if used > slot["max"]:
            raise RuleError(f"No le quedan espacios de {slot['label'].lower()}.")
        with transaction():
            Magic._set_used(character["id"], key, max(0, used))
        return slot

    @staticmethod
    def set_slot_max(character, values):
        """values: {clave: número o None (= el de la tabla)}"""
        db = get_db()
        for key, value in values.items():
            if key not in [str(n) for n in range(1, 10)] + ["pact"]:
                continue
            value = None if value in (None, "") else _int(value, 0, 0, 9)
            if db.execute("SELECT 1 FROM character_spell_slots WHERE character_id = ? AND slot = ?",
                          (character["id"], key)).fetchone():
                db.execute("UPDATE character_spell_slots SET max_override = ? WHERE character_id = ? AND slot = ?",
                           (value, character["id"], key))
            elif value is not None:
                db.execute("INSERT INTO character_spell_slots (character_id, slot, max_override) VALUES (?, ?, ?)",
                           (character["id"], key, value))
        db.commit()

    @staticmethod
    def rest(character, kind):
        """Descanso largo: recupera todos los espacios. Corto: los de pacto."""
        with transaction() as db:
            sql = "UPDATE character_spell_slots SET used = 0 WHERE character_id = ?"
            if kind == "short":
                sql += " AND slot = 'pact'"
            db.execute(sql, (character["id"],))
            ActivityLog.add(character["id"], "Descanso largo: recupera sus espacios de conjuro" if kind == "long"
                            else "Descanso corto: recupera sus espacios de pacto")

    @staticmethod
    def cast(character, entry, slot_key=None, ritual=False):
        """Lanza un conjuro apuntado: los trucos y rituales no gastan; el resto, un espacio de su nivel o mayor."""
        if entry["level"] == 0 or (ritual and entry["ritual"]):
            with transaction():
                ActivityLog.add(character["id"], f"Lanza «{entry['name']}»" + (" como ritual" if ritual else ""))
            return None
        if (character["spell_prep"] in ("prepared", "prepared_half")
                and not (entry["prepared"] or entry["always_prepared"])):
            raise RuleError(f"«{entry['name']}» no está preparado: prepáralo antes de lanzarlo.")
        slot = next((s for s in Magic.slots(character) if s["key"] == slot_key), None)
        if slot is None or slot["level"] < entry["level"]:
            raise RuleError(f"«{entry['name']}» necesita un espacio de nivel {entry['level']} o superior.")
        if slot["used"] >= slot["max"]:
            raise RuleError(f"No le quedan espacios de {slot['label'].lower()}.")
        with transaction():
            Magic._set_used(character["id"], slot["key"], slot["used"] + 1)
            ActivityLog.add(character["id"], f"Lanza «{entry['name']}» con un espacio de {slot['label'].lower()}")
        return slot

    # --- Resumen para la pestaña ------------------------------------------------------------------

    @staticmethod
    def summary(character, stats, spells):
        """Característica, CD, ataque y cuántos trucos / conjuros tiene frente a su máximo."""
        ability = character["spell_ability"]
        progress = character["subclass_progress"] or character["class_code"]
        level = character["level"]
        cantrips = sum(1 for s in spells if s["level"] == 0)
        leveled = [s for s in spells if s["level"] > 0]
        prep = character["spell_prep"]
        info = {
            "ability": ability,
            "ability_name": dict((k, n) for k, _, n in rules.ABILITIES).get(ability),
            "cantrips": cantrips,
            "cantrips_max": class_data.cantrips_known(progress, level),
            "prep": prep,
            "count": len(leveled),
            "count_max": None,
            "count_label": "Conjuros",
        }
        if prep in ("prepared", "prepared_half") and ability:
            info["count"] = sum(1 for s in leveled if s["prepared"] and not s["always_prepared"])
            info["count_max"] = class_data.prepared_max(prep, stats["mods"][ability], level)
            info["count_label"] = "Preparados"
        elif prep == "known":
            info["count_max"] = class_data.spells_known(progress, level)
            info["count_label"] = "Conocidos"
        return info
