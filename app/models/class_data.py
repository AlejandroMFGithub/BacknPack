"""Clases y subclases oficiales de 5e y tablas de lanzamiento de conjuros (funciones puras).

Las clases se guardan en la base de datos (tabla classes) para que el DM pueda añadir las
suyas; estas son las que se cargan de serie. «progress» enlaza con las tablas de trucos y
conjuros conocidos de abajo (las clases homebrew no tienen y esas cifras no se muestran).
"""

CASTER_TYPES = {
    "none": "Sin conjuros",
    "full": "Lanzador completo (bardo, clérigo, druida, hechicero, mago)",
    "half": "Medio lanzador (explorador, paladín)",
    "half_up": "Medio lanzador desde nivel 1 (artífice)",
    "third": "Un tercio (caballero arcano, embaucador arcano)",
    "pact": "Magia de pacto (brujo)",
}

SPELL_PREP = {
    "known": "Conocidos (no se preparan)",
    "prepared": "Preparados: mod. + nivel",
    "prepared_half": "Preparados: mod. + mitad del nivel",
}

HIT_DICE = (6, 8, 10, 12)

SPELL_SOURCES = {
    "class": "Clase",
    "subclass": "Subclase",
    "race": "Raza",
    "feat": "Dote",
    "item": "Objeto",
    "other": "Otro",
}

SCHOOLS = ["Abjuración", "Adivinación", "Conjuración", "Encantamiento", "Evocación",
           "Ilusionismo", "Nigromancia", "Transmutación"]

# clave, nombre, dado de golpe, salvaciones, lanzador, característica, preparación, nivel de subclase,
# competencias (resumen) y subclases: (nombre, lanzador propio, característica propia, progress propio)
CLASSES = [
    ("barbarian", "Bárbaro", 12, ("strength", "constitution"), "none", None, None, 3,
     "Armaduras ligeras e intermedias, escudos · armas sencillas y marciales",
     [("Senda del Berserker",), ("Senda del Guerrero Totémico",)]),
    ("bard", "Bardo", 8, ("dexterity", "charisma"), "full", "charisma", "known", 3,
     "Armaduras ligeras · armas sencillas, ballesta de mano, espada larga, estoque, espada corta · 3 instrumentos",
     [("Colegio del Conocimiento",), ("Colegio del Valor",)]),
    ("warlock", "Brujo", 8, ("wisdom", "charisma"), "pact", "charisma", "known", 1,
     "Armaduras ligeras · armas sencillas",
     [("El Archihada",), ("El Infernal",), ("El Primigenio",)]),
    ("cleric", "Clérigo", 8, ("wisdom", "charisma"), "full", "wisdom", "prepared", 1,
     "Armaduras ligeras e intermedias, escudos · armas sencillas",
     [("Dominio del Conocimiento",), ("Dominio de la Guerra",), ("Dominio de la Luz",),
      ("Dominio de la Naturaleza",), ("Dominio del Engaño",), ("Dominio de la Tempestad",), ("Dominio de la Vida",)]),
    ("druid", "Druida", 8, ("intelligence", "wisdom"), "full", "wisdom", "prepared", 2,
     "Armaduras ligeras e intermedias y escudos (no metálicos) · armas de druida · útiles de herborista",
     [("Círculo de la Tierra",), ("Círculo de la Luna",)]),
    ("ranger", "Explorador", 10, ("strength", "dexterity"), "half", "wisdom", "known", 3,
     "Armaduras ligeras e intermedias, escudos · armas sencillas y marciales",
     [("Cazador",), ("Señor de las Bestias",)]),
    ("fighter", "Guerrero", 10, ("strength", "constitution"), "none", None, None, 3,
     "Todas las armaduras, escudos · armas sencillas y marciales",
     [("Campeón",), ("Maestro de Batalla",),
      ("Caballero Arcano", "third", "intelligence", "eldritch_knight", "known")]),
    ("sorcerer", "Hechicero", 6, ("constitution", "charisma"), "full", "charisma", "known", 1,
     "Dagas, dardos, hondas, bastones, ballestas ligeras",
     [("Linaje Dracónico",), ("Magia Salvaje",)]),
    ("wizard", "Mago", 6, ("intelligence", "wisdom"), "full", "intelligence", "prepared", 2,
     "Dagas, dardos, hondas, bastones, ballestas ligeras",
     [("Escuela de Abjuración",), ("Escuela de Adivinación",), ("Escuela de Conjuración",),
      ("Escuela de Encantamiento",), ("Escuela de Evocación",), ("Escuela de Ilusionismo",),
      ("Escuela de Nigromancia",), ("Escuela de Transmutación",)]),
    ("monk", "Monje", 8, ("strength", "dexterity"), "none", None, None, 3,
     "Armas sencillas, espadas cortas · un instrumento o herramienta de artesano",
     [("Camino de la Mano Abierta",), ("Camino de la Sombra",), ("Camino de los Cuatro Elementos",)]),
    ("paladin", "Paladín", 10, ("wisdom", "charisma"), "half", "charisma", "prepared_half", 3,
     "Todas las armaduras, escudos · armas sencillas y marciales",
     [("Juramento de Devoción",), ("Juramento de los Antiguos",), ("Juramento de Venganza",)]),
    ("rogue", "Pícaro", 8, ("dexterity", "intelligence"), "none", None, None, 3,
     "Armaduras ligeras · armas sencillas, ballesta de mano, espada larga, estoque, espada corta · herramientas de ladrón",
     [("Ladrón",), ("Asesino",), ("Embaucador Arcano", "third", "intelligence", "arcane_trickster", "known")]),
    ("artificer", "Artífice", 8, ("constitution", "intelligence"), "half_up", "intelligence", "prepared_half", 3,
     "Armaduras ligeras e intermedias, escudos · armas sencillas · herramientas de ladrón y de manitas",
     [("Alquimista",), ("Artillero",), ("Herrero de Batalla",), ("Armero",)]),
]

# --- Espacios de conjuro -----------------------------------------------------------------------

# Lanzador completo por nivel de lanzador: espacios de nivel 1..9
_FULL = {
    1: [2], 2: [3], 3: [4, 2], 4: [4, 3], 5: [4, 3, 2], 6: [4, 3, 3], 7: [4, 3, 3, 1], 8: [4, 3, 3, 2],
    9: [4, 3, 3, 3, 1], 10: [4, 3, 3, 3, 2], 11: [4, 3, 3, 3, 2, 1], 12: [4, 3, 3, 3, 2, 1],
    13: [4, 3, 3, 3, 2, 1, 1], 14: [4, 3, 3, 3, 2, 1, 1], 15: [4, 3, 3, 3, 2, 1, 1, 1],
    16: [4, 3, 3, 3, 2, 1, 1, 1], 17: [4, 3, 3, 3, 2, 1, 1, 1, 1], 18: [4, 3, 3, 3, 3, 1, 1, 1, 1],
    19: [4, 3, 3, 3, 3, 2, 1, 1, 1], 20: [4, 3, 3, 3, 3, 2, 2, 1, 1],
}


def caster_level(caster, level):
    """Nivel equivalente de lanzador completo (las tablas de medio y tercio coinciden así)."""
    level = max(1, min(int(level or 1), 20))
    if caster == "full":
        return level
    if caster == "half":
        return 0 if level < 2 else -(-level // 2)
    if caster == "half_up":
        return -(-level // 2)
    if caster == "third":
        return 0 if level < 3 else -(-level // 3)
    return 0


def spell_slots(caster, level):
    """{nivel de conjuro: espacios} según el tipo de lanzador y el nivel del personaje."""
    if caster == "pact":
        count, slot_level = pact_slots(level)
        return {slot_level: count}
    return {i + 1: n for i, n in enumerate(_FULL.get(caster_level(caster, level), []))}


def pact_slots(level):
    """Magia de pacto (brujo): (número de espacios, nivel de los espacios)."""
    level = max(1, min(int(level or 1), 20))
    count = 1 if level == 1 else 2 if level <= 10 else 3 if level <= 16 else 4
    return count, min(5, (level + 1) // 2)


# --- Trucos y conjuros conocidos -----------------------------------------------------------------

def _steps(table, level):
    """Valor de una tabla {nivel desde el que aplica: valor} para un nivel dado."""
    value = 0
    for since, n in sorted(table.items()):
        if level >= since:
            value = n
    return value


CANTRIPS = {
    "bard": {1: 2, 4: 3, 10: 4}, "cleric": {1: 3, 4: 4, 10: 5}, "druid": {1: 2, 4: 3, 10: 4},
    "sorcerer": {1: 4, 4: 5, 10: 6}, "warlock": {1: 2, 4: 3, 10: 4}, "wizard": {1: 3, 4: 4, 10: 5},
    "artificer": {1: 2, 10: 3, 14: 4}, "eldritch_knight": {3: 2, 10: 3}, "arcane_trickster": {3: 3, 10: 4},
}

_KNOWN = {
    "bard": [4, 5, 6, 7, 8, 9, 10, 11, 12, 14, 15, 15, 16, 18, 19, 19, 20, 22, 22, 22],
    "sorcerer": [2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 12, 13, 13, 14, 14, 15, 15, 15, 15],
    "warlock": [2, 3, 4, 5, 6, 7, 8, 9, 10, 10, 11, 11, 12, 12, 13, 13, 14, 14, 15, 15],
    "ranger": [0, 2, 3, 3, 4, 4, 5, 5, 6, 6, 7, 7, 8, 8, 9, 9, 10, 10, 11, 11],
    "eldritch_knight": [0, 0, 3, 4, 4, 4, 5, 6, 6, 7, 8, 8, 9, 10, 10, 11, 11, 11, 12, 13],
    "arcane_trickster": [0, 0, 3, 4, 4, 4, 5, 6, 6, 7, 8, 8, 9, 10, 10, 11, 11, 11, 12, 13],
}


def cantrips_known(progress, level):
    """Trucos que conoce a ese nivel (None si la clase no tiene tabla: homebrew)."""
    table = CANTRIPS.get(progress)
    return _steps(table, int(level)) if table else None


def spells_known(progress, level):
    table = _KNOWN.get(progress)
    return table[max(1, min(int(level), 20)) - 1] if table else None


def prepared_max(prep, ability_mod, level):
    """Conjuros que puede preparar (mínimo 1). None si no prepara (los conoce)."""
    if prep == "prepared":
        return max(1, ability_mod + int(level))
    if prep == "prepared_half":
        return max(1, ability_mod + int(level) // 2)
    return None


def default_hp(hit_die, level, con_mod):
    """PG máximos por defecto: el dado entero a nivel 1 y la media (redondeada arriba) después."""
    level = max(1, int(level or 1))
    return max(1, hit_die + con_mod + (level - 1) * (hit_die // 2 + 1 + con_mod))
