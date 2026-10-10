from ..db import get_db
from .errors import RuleError

CATEGORIES = [
    "Arma", "Armadura", "Escudo", "Munición", "Consumible", "Objeto maravilloso",
    "Herramienta", "Equipo de aventurero", "Tesoro", "Misceláneo",
]
RARITIES = ["Común", "Poco común", "Raro", "Muy raro", "Legendario", "Artefacto"]


class Item:
    @staticmethod
    def all():
        return get_db().execute("SELECT * FROM items ORDER BY category, name").fetchall()

    @staticmethod
    def get(item_id):
        return get_db().execute("SELECT * FROM items WHERE id = ?", (item_id,)).fetchone()

    @staticmethod
    def _clean(data):
        name = (data.get("name") or "").strip()
        if not name:
            raise RuleError("El objeto necesita un nombre.")
        try:
            weight = float(str(data.get("weight") or 0).replace(",", "."))
        except ValueError:
            weight = 0.0
        return {
            "name": name,
            "category": data.get("category") if data.get("category") in CATEGORIES else "Misceláneo",
            "rarity": data.get("rarity") if data.get("rarity") in RARITIES else "Común",
            "weight": max(weight, 0.0),
            "properties": (data.get("properties") or "").strip(),
            "description": (data.get("description") or "").strip(),
            "attunement": 1 if data.get("attunement") else 0,
        }

    @staticmethod
    def create(data):
        clean = Item._clean(data)
        db = get_db()
        item_id = db.insert(
            f"INSERT INTO items ({', '.join(clean)}) VALUES ({', '.join('?' for _ in clean)})",
            tuple(clean.values()),
        )
        db.commit()
        return item_id

    @staticmethod
    def update(item_id, data):
        clean = Item._clean(data)
        db = get_db()
        db.execute(
            f"UPDATE items SET {', '.join(f'{k} = ?' for k in clean)} WHERE id = ?",
            (*clean.values(), item_id),
        )
        db.commit()

    @staticmethod
    def delete(item_id):
        db = get_db()
        db.execute("DELETE FROM items WHERE id = ?", (item_id,))
        db.commit()
