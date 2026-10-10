from ..db import get_db
from ..text import LIKE_ESCAPE, distances, like_prefix, like_terms, normalize
from .errors import RuleError
from .listing import PER_PAGE, paginate, sort_sql

CATEGORIES = [
    "Arma", "Armadura", "Escudo", "Munición", "Consumible", "Objeto maravilloso",
    "Herramienta", "Equipo de aventurero", "Tesoro", "Misceláneo",
]
RARITIES = ["Común", "Poco común", "Raro", "Muy raro", "Legendario", "Artefacto"]


def rarity_order(column="rarity"):
    """Expresión SQL para ordenar por rareza (Común < … < Artefacto)."""
    whens = " ".join(f"WHEN '{r}' THEN {i}" for i, r in enumerate(RARITIES))
    return f"CASE {column} {whens} ELSE 99 END"


SORTS = {
    "name": ("Nombre", "search_name, id"),
    "category": ("Categoría", "category, search_name, id"),
    "rarity": ("Rareza", f"{rarity_order()}, search_name, id"),
    "rarity_desc": ("Rareza (de más rara)", f"{rarity_order()} DESC, search_name, id"),
    "weight": ("Peso", "weight DESC, search_name, id"),
    "recent": ("Añadidos recientemente", "id DESC"),
}


class Item:
    SORTS = SORTS

    @staticmethod
    def all():
        return get_db().execute("SELECT * FROM items ORDER BY category, name").fetchall()

    @staticmethod
    def get(item_id):
        return get_db().execute("SELECT * FROM items WHERE id = ?", (item_id,)).fetchone()

    @staticmethod
    def search(q="", category="", rarity="", sort="name", page=1, per_page=PER_PAGE):
        """Catálogo filtrado y paginado. sort='relevance' pone primero lo que empieza por q."""
        where, params = [], []
        for term in like_terms(q):
            where.append("search_name LIKE ?" + LIKE_ESCAPE)
            params.append(term)
        if category in CATEGORIES:
            where.append("category = ?")
            params.append(category)
        if rarity in RARITIES:
            where.append("rarity = ?")
            params.append(rarity)
        if sort == "relevance" and q:
            order, order_params = "CASE WHEN search_name LIKE ?" + LIKE_ESCAPE + " THEN 0 ELSE 1 END, search_name, id", (like_prefix(q),)
        else:
            order, order_params = sort_sql(SORTS, sort, "name"), ()
        return paginate("SELECT * FROM items", where, params, order, page, per_page, order_params)

    @staticmethod
    def _clean(data):
        name = distances((data.get("name") or "").strip())
        if not name:
            raise RuleError("El objeto necesita un nombre.")
        try:
            weight = float(str(data.get("weight") or 0).replace(",", "."))
        except ValueError:
            weight = 0.0
        return {
            "name": name,
            "search_name": normalize(name),
            "category": data.get("category") if data.get("category") in CATEGORIES else "Misceláneo",
            "rarity": data.get("rarity") if data.get("rarity") in RARITIES else "Común",
            "weight": max(weight, 0.0),
            "properties": distances((data.get("properties") or "").strip()),
            "description": distances((data.get("description") or "").strip()),
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
