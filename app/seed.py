"""Datos iniciales: cuenta de DM, divisas de 5e, catálogo básico y (opcional) una partida de ejemplo."""
from .db import get_db
from .models import Character, Condition, Currency, Inventory, Item, ItemTrait, Loot, Shop, User

CURRENCIES = [
    ("pc", "Pieza de cobre", 1),
    ("pp", "Pieza de plata", 10),
    ("pe", "Pieza de electro", 50),
    ("po", "Pieza de oro", 100),
    ("ppt", "Pieza de platino", 1000),
]

ITEMS = [
    # nombre, categoría, rareza, peso (kg), propiedades, descripción, sintonía
    ("Daga", "Arma", "Común", 0.5, "1d4 perforante · sutil, ligera, arrojadiza (6/18 m)", "", 0),
    ("Espada larga", "Arma", "Común", 1.5, "1d8 cortante · versátil (1d10)", "", 0),
    ("Cimitarra", "Arma", "Común", 1.5, "1d6 cortante · sutil, ligera", "", 0),
    ("Hacha de batalla", "Arma", "Común", 2, "1d8 cortante · versátil (1d10)", "", 0),
    ("Arco corto", "Arma", "Común", 1, "1d6 perforante · munición (24/96 m), a dos manos", "", 0),
    ("Flechas (20)", "Munición", "Común", 0.5, "", "Carcaj con 20 flechas.", 0),
    ("Armadura de cuero", "Armadura", "Común", 5, "CA 11 + mod. Des · ligera", "", 0),
    ("Cota de malla", "Armadura", "Común", 27.5, "CA 16 · Fue 13 · desventaja en Sigilo", "", 0),
    ("Escudo", "Escudo", "Común", 3, "+2 CA", "", 0),
    ("Poción de curación", "Consumible", "Común", 0.25, "Recupera 2d4 + 2 PG", "Líquido rojo que brilla al agitarlo.", 0),
    ("Antorcha", "Equipo de aventurero", "Común", 0.5, "Luz brillante 6 m, tenue 6 m más · 1 h", "", 0),
    ("Raciones (1 día)", "Equipo de aventurero", "Común", 1, "", "Comida seca para un día.", 0),
    ("Cuerda de cáñamo (15 m)", "Equipo de aventurero", "Común", 5, "", "", 0),
    ("Herramientas de ladrón", "Herramienta", "Común", 0.5, "", "Ganzúas, limas y un espejito.", 0),
    ("Anillo de protección", "Objeto maravilloso", "Raro", 0, "+1 CA y tiradas de salvación", "", 1),
    ("Amuleto de hueso", "Objeto maravilloso", "Poco común", 0, "???", "Un amuleto tallado que susurra de noche.", 1),
    ("Varita de proyectiles mágicos", "Objeto maravilloso", "Poco común", 0.5, "Lanza *proyectil mágico*", "", 0),
]

# Cualidades de plantilla: nombre del objeto -> datos de la cualidad
ITEM_TRAITS = [
    ("Varita de proyectiles mágicos", {
        "name": "Cargas", "kind": "charges", "uses_max": 7, "recharge": "1d6+1 al amanecer", "visible": 1,
        "description": "Gasta 1 carga para lanzar proyectil mágico (nivel 1); +1 nivel por carga extra.",
    }),
    ("Poción de curación", {"name": "Un solo uso", "kind": "property", "visible": 1,
                            "description": "Se consume al beberla."}),
]


def seed(demo=True, dm_password="dm"):
    db = get_db()
    User.create("dm", dm_password, role="dm")
    for code, name, value in CURRENCIES:
        Currency.create(code, name, value)
    for name, cat, rar, w, props, desc, att in ITEMS:
        Item.create({
            "name": name, "category": cat, "rarity": rar, "weight": w,
            "properties": props, "description": desc, "attunement": att,
        })
    item_ids = {row["name"]: row["id"] for row in Item.all()}
    for item_name, data in ITEM_TRAITS:
        ItemTrait.create(data, item_id=item_ids[item_name])
    if demo:
        _seed_demo(db)
    db.commit()


def _seed_demo(db):
    item = {row["name"]: row["id"] for row in Item.all()}
    cur = {row["code"]: row["id"] for row in Currency.all()}
    cur["ficha"] = Currency.create("ficha", "Ficha del Gremio", 0)  # no convertible

    ana = User.create("ana", "ana")
    bruno = User.create("bruno", "bruno")

    lyra = Character.create(ana, {
        "name": "Lyra Vientoalto", "race": "Elfa del bosque", "class_name": "Exploradora",
        "level": 3, "background": "Forastera", "alignment": "Caótica buena",
        "strength": 11, "dexterity": 17, "constitution": 13, "intelligence": 10,
        "wisdom": 15, "charisma": 8, "hp_max": 28, "hp_current": 24, "armor_class": 14, "speed": 10.5,
    })
    thorgar = Character.create(bruno, {
        "name": "Thorgar Puñohierro", "race": "Enano de las montañas", "class_name": "Guerrero",
        "level": 3, "background": "Soldado", "alignment": "Legal neutral",
        "strength": 17, "dexterity": 10, "constitution": 16, "intelligence": 9,
        "wisdom": 12, "charisma": 10, "hp_max": 34, "hp_current": 34, "armor_class": 18, "speed": 7.5,
    })

    for char_id, item_name, qty, visible in [
        (lyra, "Arco corto", 1, True), (lyra, "Flechas (20)", 1, True), (lyra, "Daga", 2, True),
        (lyra, "Armadura de cuero", 1, True), (lyra, "Poción de curación", 2, True),
        (lyra, "Amuleto de hueso", 1, False), (lyra, "Varita de proyectiles mágicos", 1, True),
        (thorgar, "Hacha de batalla", 1, True), (thorgar, "Cota de malla", 1, True),
        (thorgar, "Escudo", 1, True), (thorgar, "Raciones (1 día)", 5, True),
        (thorgar, "Antorcha", 3, True),
    ]:
        Inventory.add(char_id, item[item_name], qty, visible)
    for row in Inventory.for_character(lyra) + Inventory.for_character(thorgar):
        if row["category"] in ("Armadura", "Escudo") or row["name"] in ("Arco corto", "Hacha de batalla"):
            db.execute("UPDATE inventory_items SET equipped = 1 WHERE id = ?", (row["id"],))
        if row["name"] == "Hacha de batalla":
            ItemTrait.create({"name": "Runa de Moradin", "kind": "blessing", "visible": 1,
                              "uses_max": 1, "recharge": "descanso largo",
                              "description": "Una vez por descanso, +1d8 de daño radiante en un impacto."},
                             inventory_item_id=row["id"])
            ItemTrait.create({"name": "Sed de sangre", "kind": "curse", "visible": 0,
                              "description": "Si no mata en un combate, CD 12 Sab o ataca al aliado más cercano."},
                             inventory_item_id=row["id"])

    for char_id, code, amount in [
        (lyra, "po", 25), (lyra, "pp", 30), (lyra, "ficha", 2),
        (thorgar, "po", 40), (thorgar, "ppt", 1), (thorgar, "pc", 57),
    ]:
        Currency.set_amount(char_id, cur[code], amount)
    db.commit()

    Condition.create(lyra, {"name": "Bendición", "kind": "buff", "visible": 1,
                            "description": "+1d4 a tiradas de ataque y salvación", "duration": "1 minuto"})
    Condition.create(lyra, {"name": "Marca del licántropo", "kind": "curse", "visible": 0,
                            "description": "Mordida por un hombre lobo. Aún no lo sabe.", "duration": "Hasta luna llena"})

    forja = Shop.create("Forja de Brunhilda", "Armas y armaduras de calidad en Puerto Niebla.")
    for name, price, code, stock in [
        ("Espada larga", 15, "po", 3), ("Cimitarra", 25, "po", 2), ("Escudo", 10, "po", None),
        ("Cota de malla", 75, "po", 1), ("Flechas (20)", 1, "po", None),
    ]:
        Shop.add_listing(forja, item[name], price, cur[code], stock)

    mercado = Shop.create("Mercado de las Sombras", "Solo acepta fichas del gremio. No hagas preguntas.",
                          allow_exchange=False)
    Shop.add_listing(mercado, item["Anillo de protección"], 3, cur["ficha"], 1)
    Shop.add_listing(mercado, item["Herramientas de ladrón"], 1, cur["ficha"], None)

    guarida = Loot.create("Guarida goblin", "Restos tras derrotar a la banda de Dientepodrido.", "combat")
    Loot.add_entry(guarida, item_id=item["Cimitarra"], quantity=2)
    Loot.add_entry(guarida, item_id=item["Poción de curación"], quantity=1)
    Loot.add_entry(guarida, currency_id=cur["pp"], quantity=15)
