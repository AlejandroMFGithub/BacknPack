"""Datos iniciales: cuenta de DM, divisas de 5e, catálogo básico y (opcional) una partida de ejemplo."""
from .db import get_db
from .models import (
    Campaign, Character, Condition, Currency, DndClass, Inventory, Item, ItemTrait, Loot, Magic, Shop, Spell, User,
)

CURRENCIES = [
    ("pc", "Pieza de cobre", 1),
    ("pp", "Pieza de plata", 10),
    ("pe", "Pieza de electro", 50),
    ("po", "Pieza de oro", 100),
    ("ppt", "Pieza de platino", 1000),
]

ITEMS = [
    # nombre, categoría, rareza, peso (kg), propiedades, descripción, sintonía
    ("Daga", "Arma", "Común", 0.5, "1d4 perforante · sutil, ligera, arrojadiza (20/60 ft)", "", 0),
    ("Espada larga", "Arma", "Común", 1.5, "1d8 cortante · versátil (1d10)", "", 0),
    ("Cimitarra", "Arma", "Común", 1.5, "1d6 cortante · sutil, ligera", "", 0),
    ("Hacha de batalla", "Arma", "Común", 2, "1d8 cortante · versátil (1d10)", "", 0),
    ("Arco corto", "Arma", "Común", 1, "1d6 perforante · munición (80/320 ft), a dos manos", "", 0),
    ("Flechas (20)", "Munición", "Común", 0.5, "", "Carcaj con 20 flechas.", 0),
    ("Armadura de cuero", "Armadura", "Común", 5, "CA 11 + mod. Des · ligera", "", 0),
    ("Cota de malla", "Armadura", "Común", 27.5, "CA 16 · Fue 13 · desventaja en Sigilo", "", 0),
    ("Escudo", "Escudo", "Común", 3, "+2 CA", "", 0),
    ("Poción de curación", "Consumible", "Común", 0.25, "Recupera 2d4 + 2 PG", "Líquido rojo que brilla al agitarlo.", 0),
    ("Antorcha", "Equipo de aventurero", "Común", 0.5, "Luz brillante 20 ft, tenue 20 ft más · 1 h", "", 0),
    ("Raciones (1 día)", "Equipo de aventurero", "Común", 1, "", "Comida seca para un día.", 0),
    ("Cuerda de cáñamo", "Equipo de aventurero", "Común", 5, "50 ft", "", 0),
    ("Herramientas de ladrón", "Herramienta", "Común", 0.5, "", "Ganzúas, limas y un espejito.", 0),
    ("Anillo de protección", "Objeto maravilloso", "Raro", 0, "+1 CA y tiradas de salvación", "", 1),
    ("Amuleto de hueso", "Objeto maravilloso", "Poco común", 0, "???", "Un amuleto tallado que susurra de noche.", 1),
    ("Varita de proyectiles mágicos", "Objeto maravilloso", "Poco común", 0.5, "Lanza *proyectil mágico*", "", 0),
]

# Efectos en la ficha mientras se lleva equipado (ver models/effects.py)
ITEM_EFFECTS = {
    "Armadura de cuero": [{"t": "armor_class", "op": "armor", "v": 11, "cap": None}],
    "Cota de malla": [{"t": "armor_class", "op": "armor", "v": 16, "cap": 0}],
    "Escudo": [{"t": "armor_class", "op": "add", "v": 2}],
    "Anillo de protección": [{"t": "armor_class", "op": "add", "v": 1}, {"t": "saves", "op": "add", "v": 1}],
}

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
            "effects": ITEM_EFFECTS.get(name),
        })
    item_ids = {row["name"]: row["id"] for row in Item.all()}
    for item_name, data in ITEM_TRAITS:
        ItemTrait.create(data, item_id=item_ids[item_name])
    # Objetos que conceden conjuros mientras se llevan equipados
    spell_ids = {row["name"]: row["id"] for row in db.execute("SELECT id, name FROM spells").fetchall()}
    Spell.add_to_item(item_ids["Varita de proyectiles mágicos"], spell_ids["Proyectil mágico"])
    if demo:
        _seed_demo(db)
    db.commit()


def _seed_demo(db):
    item = {row["name"]: row["id"] for row in Item.all()}
    cur = {row["code"]: row["id"] for row in Currency.all()}
    cur["ficha"] = Currency.create("ficha", "Ficha del Gremio", 0)  # no convertible

    ana = User.create("ana", "ana")
    bruno = User.create("bruno", "bruno")

    costa = Campaign.create({"name": "La Costa de la Espada", "is_open": 1,
                             "description": "Puerto Niebla y sus alrededores: goblins, gremios y contrabando."})
    helada = Campaign.create({"name": "Las Tierras Heladas", "is_open": 1,
                              "description": "Una campaña aparte, en el norte: aquí no llegan las tiendas de la Costa."})

    sub = {row["name"]: row["id"] for row in DndClass.subclasses()}
    lyra = Character.create(ana, {
        "name": "Lyra Vientoalto", "race": "Elfa del bosque", "class_name": "Exploradora",
        "level": 3, "background": "Forastera", "alignment": "Caótica buena", "subclass_id": sub["Cazador"],
        "strength": 11, "dexterity": 17, "constitution": 13, "intelligence": 10,
        "wisdom": 15, "charisma": 8, "hp_max": 28, "hp_current": 24, "armor_class": 13, "speed": 35,
        # Exploradora: salvaciones de FUE y DES; Sigilo con pericia (p. ej. por una dote)
        "save_strength": 1, "save_dexterity": 1, "skill_stealth": 2, "skill_perception": 1,
        "skill_survival": 1, "skill_animal_handling": 1, "skill_acrobatics": 1,
    }, costa)
    thorgar = Character.create(bruno, {
        "name": "Thorgar Puñohierro", "race": "Enano de las montañas", "class_name": "Guerrero",
        "level": 3, "background": "Soldado", "alignment": "Legal neutral", "subclass_id": sub["Campeón"],
        "strength": 17, "dexterity": 10, "constitution": 16, "intelligence": 9,
        "wisdom": 12, "charisma": 10, "hp_max": 34, "hp_current": 34, "armor_class": 10, "speed": 25,
        # Guerrero: salvaciones de FUE y CON
        "save_strength": 1, "save_constitution": 1, "skill_athletics": 1, "skill_intimidation": 1,
        "skill_perception": 1,
    }, costa)
    # Ana juega también en otra campaña: al entrar tendrá que elegir personaje
    sigrid = Character.create(ana, {
        "name": "Sigrid Escarcha", "race": "Humana", "class_name": "Druida", "level": 2,
        "subclass_id": sub["Círculo de la Tierra"],
        "wisdom": 16, "constitution": 14, "hp_max": 17, "hp_current": 17, "armor_class": 12,
        "save_intelligence": 1, "save_wisdom": 1, "skill_nature": 1, "skill_medicine": 1,
    }, helada)

    for char_id, item_name, qty, visible in [
        (lyra, "Arco corto", 1, True), (lyra, "Flechas (20)", 1, True), (lyra, "Daga", 2, True),
        (lyra, "Armadura de cuero", 1, True), (lyra, "Poción de curación", 2, True),
        (lyra, "Amuleto de hueso", 1, False), (lyra, "Varita de proyectiles mágicos", 1, True),
        (thorgar, "Hacha de batalla", 1, True), (thorgar, "Cota de malla", 1, True),
        (thorgar, "Escudo", 1, True), (thorgar, "Raciones (1 día)", 5, True),
        (thorgar, "Antorcha", 3, True),
        (sigrid, "Raciones (1 día)", 3, True), (sigrid, "Cuerda de cáñamo", 1, True),
    ]:
        Inventory.add(char_id, item[item_name], qty, visible)
    for row in Inventory.for_character(lyra) + Inventory.for_character(thorgar):
        if row["category"] in ("Armadura", "Escudo") or row["name"] in (
                "Arco corto", "Hacha de batalla", "Varita de proyectiles mágicos"):
            db.execute("UPDATE inventory_items SET equipped = 1 WHERE id = ?", (row["id"],))
        if row["name"] == "Hacha de batalla":
            ItemTrait.create({"name": "Runa de Moradin", "kind": "blessing", "visible": 1,
                              "uses_max": 1, "recharge": "descanso largo",
                              "description": "Una vez por descanso, +1d8 de daño radiante en un impacto."},
                             inventory_item_id=row["id"])
            ItemTrait.create({"name": "Sed de sangre", "kind": "curse", "visible": 0,
                              "description": "Si no mata en un combate, CD 12 Sab o ataca al aliado más cercano.",
                              "effects": [{"t": "wisdom", "op": "add", "v": -2}]},
                             inventory_item_id=row["id"])

    for char_id, code, amount in [
        (lyra, "po", 25), (lyra, "pp", 30), (lyra, "ficha", 2),
        (thorgar, "po", 40), (thorgar, "ppt", 1), (thorgar, "pc", 57),
        (sigrid, "pp", 12),
    ]:
        Currency.set_amount(char_id, cur[code], amount)
    db.commit()

    Character.change_inspiration(lyra, 1)

    # Conjuros: Lyra (exploradora 3, los conoce) y Sigrid (druida 2, los prepara)
    spell = {row["name"]: row["id"] for row in db.execute("SELECT id, name FROM spells").fetchall()}
    for name in ("Marca del cazador", "Curar heridas", "Buenas bayas"):
        Magic.add(lyra, spell[name])
    Magic.change_slot(Character.get(lyra), "1", +1)  # ya ha gastado un espacio hoy
    for name in ("Guía", "Producir llama", "Buenas bayas", "Curar heridas", "Palabra de curación",
                 "Enmarañar", "Onda atronadora", "Hablar con los animales"):
        Magic.add(sigrid, spell[name])
    db.execute("""UPDATE character_spells SET prepared = 1 WHERE character_id = ? AND spell_id IN
                  (SELECT id FROM spells WHERE name IN ('Buenas bayas', 'Curar heridas', 'Palabra de curación', 'Enmarañar'))""",
               (sigrid,))
    db.commit()
    Condition.create(lyra, {"name": "Bendición", "kind": "buff", "visible": 1, "locked": 1,  # fijo: lo puso el DM
                            "description": "+1d4 a tiradas de ataque y salvación", "duration": "1 minuto"})
    Condition.create(lyra, {"name": "Marca del licántropo", "kind": "curse", "visible": 0,
                            "description": "Mordida por un hombre lobo. Aún no lo sabe.", "duration": "Hasta luna llena",
                            "effects": [{"t": "speed", "op": "add", "v": -5}]})
    Condition.create(lyra, {"name": "Paso largo", "kind": "buff", "visible": 1,  # efecto del reglamento: +10 ft
                            "description": "Conjuro de su compañero druida.", "duration": "1 hora"})
    # Efecto que crea el propio jugador y activa en combate
    Condition.create(thorgar, {"name": "Postura defensiva", "kind": "buff", "duration": "hasta su siguiente turno",
                               "description": "Se cubre con el escudo: −10 ft de velocidad a cambio de +1 a la CA.",
                               "effects": [{"t": "armor_class", "op": "add", "v": 1}, {"t": "speed", "op": "add", "v": -10}]},
                     by_dm=False)
    db.execute("UPDATE conditions SET active = 0 WHERE name = 'Postura defensiva'")
    db.commit()

    forja = Shop.create("Forja de Brunhilda", "Armas y armaduras de calidad en Puerto Niebla.", costa)
    for name, price, code, stock in [
        ("Espada larga", 15, "po", 3), ("Cimitarra", 25, "po", 2), ("Escudo", 10, "po", None),
        ("Cota de malla", 75, "po", 1), ("Flechas (20)", 1, "po", None),
    ]:
        Shop.add_listing(forja, item[name], price, cur[code], stock)

    mercado = Shop.create("Mercado de las Sombras", "Solo acepta fichas del gremio. No hagas preguntas.",
                          costa, allow_exchange=False)
    Shop.add_listing(mercado, item["Anillo de protección"], 3, cur["ficha"], 1)
    Shop.add_listing(mercado, item["Herramientas de ladrón"], 1, cur["ficha"], None)

    guarida = Loot.create("Guarida goblin", "Restos tras derrotar a la banda de Dientepodrido.", "combat", costa)
    Loot.add_entry(guarida, item_id=item["Cimitarra"], quantity=2)
    Loot.add_entry(guarida, item_id=item["Poción de curación"], quantity=1)
    Loot.add_entry(guarida, currency_id=cur["pp"], quantity=15)

    trampero = Shop.create("Puesto del trampero", "Pieles y provisiones a cambio de plata.", helada)
    for name, price, code in [("Raciones (1 día)", 6, "pp"), ("Antorcha", 1, "pc"), ("Cuerda de cáñamo", 1, "po")]:
        Shop.add_listing(trampero, item[name], price, cur[code], None)
    cueva = Loot.create("Cueva del oso blanco", "Lo que quedó tras ahuyentar al oso.", "environment", helada)
    Loot.add_entry(cueva, item_id=item["Poción de curación"], quantity=1)
