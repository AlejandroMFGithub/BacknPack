from ..db import get_db, transaction
from ..text import LIKE_ESCAPE, distances, like_terms, matches_all_words
from .activity_log import ActivityLog
from .campaign import Campaign
from .currency import Currency
from .errors import RuleError
from .inventory import Inventory
from .item import CATEGORIES, rarity_order
from .listing import sort_sql

SORTS = {
    "name": ("Nombre", "name, id"),
    "open": ("Abiertas primero", "active DESC, name, id"),
    "recent": ("Creadas recientemente", "id DESC"),
}

# Precio comparable entre divisas: en piezas de cobre; las no convertibles van al final
_PRICE_CP = "si.price * c.value_cp"
_CONVERTIBLE_FIRST = "CASE WHEN c.value_cp > 0 THEN 0 ELSE 1 END"
LISTING_SORTS = {
    "category": ("Categoría", "i.category, i.search_name, si.id"),
    "name": ("Nombre", "i.search_name, si.id"),
    "price": ("Precio (más barato)", f"{_CONVERTIBLE_FIRST}, {_PRICE_CP}, si.price, i.search_name"),
    "price_desc": ("Precio (más caro)", f"{_CONVERTIBLE_FIRST}, {_PRICE_CP} DESC, si.price DESC, i.search_name"),
    "rarity": ("Rareza (de más rara)", f"{rarity_order('i.rarity')} DESC, i.search_name, si.id"),
    "stock": ("Más unidades", "CASE WHEN si.stock IS NULL THEN 0 ELSE 1 END, si.stock DESC, i.search_name"),
}


def filter_by_name(rows, q):
    """Filtro sin tildes ni mayúsculas para listas cortas (tiendas, botines)."""
    return [r for r in rows if matches_all_words(q, r["name"])] if q else rows


class Shop:
    SORTS = SORTS
    LISTING_SORTS = LISTING_SORTS

    @staticmethod
    def all(campaign_id, active_only=False, q="", sort="name"):
        sql = "SELECT * FROM shops WHERE campaign_id = ?"
        if active_only:
            sql += " AND active = 1"
        rows = get_db().execute(sql + " ORDER BY " + sort_sql(SORTS, sort, "name"), (campaign_id,)).fetchall()
        return filter_by_name(rows, q)

    @staticmethod
    def get(shop_id):
        return get_db().execute("SELECT * FROM shops WHERE id = ?", (shop_id,)).fetchone()

    @staticmethod
    def create(name, description, campaign_id, allow_exchange=True):
        if not (name or "").strip():
            raise RuleError("La tienda necesita un nombre.")
        db = get_db()
        shop_id = db.insert(
            "INSERT INTO shops (name, description, allow_exchange, campaign_id) VALUES (?, ?, ?, ?)",
            (name.strip(), distances((description or "").strip()), 1 if allow_exchange else 0, campaign_id),
        )
        db.commit()
        return shop_id

    @staticmethod
    def toggle(shop_id, column):
        if column not in ("active", "allow_exchange"):
            raise ValueError(column)
        db = get_db()
        db.execute(f"UPDATE shops SET {column} = 1 - {column} WHERE id = ?", (shop_id,))
        db.commit()

    @staticmethod
    def delete(shop_id):
        db = get_db()
        db.execute("DELETE FROM shops WHERE id = ?", (shop_id,))
        db.commit()

    # --- Género a la venta ----------------------------------------------------

    _LISTING_SQL = """
        SELECT si.*, i.name, i.category, i.rarity, i.properties, i.description, i.weight,
               c.code AS currency_code, c.name AS currency_name, c.value_cp
        FROM shop_items si
        JOIN items i ON i.id = si.item_id
        JOIN currencies c ON c.id = si.currency_id
    """

    @staticmethod
    def listings(shop_id, q="", category="", sort="category"):
        sql = Shop._LISTING_SQL + " WHERE si.shop_id = ?"
        params = [shop_id]
        for term in like_terms(q):
            sql += " AND i.search_name LIKE ?" + LIKE_ESCAPE
            params.append(term)
        if category in CATEGORIES:
            sql += " AND i.category = ?"
            params.append(category)
        sql += " ORDER BY " + sort_sql(LISTING_SORTS, sort, "category")
        return get_db().execute(sql, tuple(params)).fetchall()

    @staticmethod
    def get_listing(listing_id):
        return get_db().execute(Shop._LISTING_SQL + " WHERE si.id = ?", (listing_id,)).fetchone()

    @staticmethod
    def add_listing(shop_id, item_id, price, currency_id, stock=None):
        if price < 0:
            raise RuleError("El precio no puede ser negativo.")
        if stock is not None and stock < 0:
            raise RuleError("El stock no puede ser negativo.")
        db = get_db()
        db.execute(
            "INSERT INTO shop_items (shop_id, item_id, price, currency_id, stock) VALUES (?, ?, ?, ?, ?)",
            (shop_id, item_id, price, currency_id, stock),
        )
        db.commit()

    @staticmethod
    def remove_listing(listing_id):
        db = get_db()
        db.execute("DELETE FROM shop_items WHERE id = ?", (listing_id,))
        db.commit()

    # --- Compra -----------------------------------------------------------------

    @staticmethod
    def quote(shop, listing, quantity, pay_currency):
        """Unidades de `pay_currency` necesarias para comprar `quantity` del artículo."""
        total = listing["price"] * quantity
        if pay_currency["id"] == listing["currency_id"]:
            return total
        if not shop["allow_exchange"]:
            raise RuleError(f"Esta tienda solo acepta {listing['currency_name']} para este artículo.")
        if not listing["value_cp"] or not pay_currency["value_cp"]:
            raise RuleError(f"No se puede convertir {pay_currency['name']} a {listing['currency_name']}.")
        cost_cp = total * listing["value_cp"]
        return -(-cost_cp // pay_currency["value_cp"])  # redondeo hacia arriba

    @staticmethod
    def buy(listing_id, character_id, quantity, pay_currency_id):
        with transaction():
            listing = Shop.get_listing(listing_id)
            if listing is None:
                raise RuleError("Ese artículo ya no está a la venta.")
            shop = Shop.get(listing["shop_id"])
            if not shop["active"]:
                raise RuleError("La tienda está cerrada.")
            if Campaign.of_character(character_id) != shop["campaign_id"]:
                raise RuleError("Esa tienda está en otra campaña.")
            if quantity < 1:
                raise RuleError("La cantidad debe ser al menos 1.")
            if listing["stock"] is not None and listing["stock"] < quantity:
                raise RuleError(f"Solo quedan {listing['stock']} unidades.")
            pay = Currency.get(pay_currency_id)
            if pay is None:
                raise RuleError("Divisa no válida.")

            cost = Shop.quote(shop, listing, quantity, pay)
            Currency.adjust(character_id, pay["id"], -cost)
            Inventory.add(character_id, listing["item_id"], quantity)
            if listing["stock"] is not None:
                get_db().execute(
                    "UPDATE shop_items SET stock = stock - ? WHERE id = ?", (quantity, listing_id)
                )
            ActivityLog.add(
                character_id,
                f"Compra {quantity}× {listing['name']} en {shop['name']} por {cost} {pay['code']}",
            )
        return cost, pay
