"""Reglas de D&D 5e para la ficha: modificadores, competencia, salvaciones y habilidades.

Funciones puras (sin base de datos), para poder probarlas y reutilizarlas.
"""
from ..text import normalize

ABILITIES = [
    ("strength", "FUE", "Fuerza"),
    ("dexterity", "DES", "Destreza"),
    ("constitution", "CON", "Constitución"),
    ("intelligence", "INT", "Inteligencia"),
    ("wisdom", "SAB", "Sabiduría"),
    ("charisma", "CAR", "Carisma"),
]
ABILITY_SHORT = {key: short for key, short, _ in ABILITIES}

# Las 18 habilidades de 5e (nombres del manual en castellano) y su característica
SKILLS = [
    ("acrobatics", "Acrobacias", "dexterity"),
    ("animal_handling", "Trato con animales", "wisdom"),
    ("arcana", "Arcanos", "intelligence"),
    ("athletics", "Atletismo", "strength"),
    ("deception", "Engaño", "charisma"),
    ("history", "Historia", "intelligence"),
    ("insight", "Perspicacia", "wisdom"),
    ("intimidation", "Intimidación", "charisma"),
    ("investigation", "Investigación", "intelligence"),
    ("medicine", "Medicina", "wisdom"),
    ("nature", "Naturaleza", "intelligence"),
    ("perception", "Percepción", "wisdom"),
    ("performance", "Interpretación", "charisma"),
    ("persuasion", "Persuasión", "charisma"),
    ("religion", "Religión", "intelligence"),
    ("sleight_of_hand", "Juego de manos", "dexterity"),
    ("stealth", "Sigilo", "dexterity"),
    ("survival", "Supervivencia", "wisdom"),
]
# En la ficha, por orden alfabético del nombre en castellano (sin tildes: «Engaño» tras «Atletismo»)
SKILLS.sort(key=lambda skill: normalize(skill[1]))
SKILL_KEYS = {key for key, _, _ in SKILLS}
SAVE_KEYS = {key for key, _, _ in ABILITIES}

NONE, PROFICIENT, EXPERTISE = 0, 1, 2


def modifier(score):
    """Modificador de una característica: 20 -> +5, 9 -> -1 (redondeo hacia abajo)."""
    return (int(score) - 10) // 2


def proficiency_for_level(level):
    """Bonificador de competencia por nivel: 1-4 +2, 5-8 +3, 9-12 +4, 13-16 +5, 17-20 +6."""
    level = max(1, min(int(level or 1), 20))
    return 2 + (level - 1) // 4


def proficiency_bonus(character):
    """El fijado a mano en la ficha o, si no hay, el de su nivel."""
    override = character["proficiency_bonus"]
    return override if override is not None else proficiency_for_level(character["level"])


def check_total(score, prof_bonus, level=NONE):
    """Total de una tirada: modificador + competencia (×2 con pericia)."""
    return modifier(score) + prof_bonus * level


def sheet(character, proficiencies):
    """Todos los valores calculados de la ficha.

    proficiencies: {("save"|"skill", clave): 1 (competencia) o 2 (pericia)}
    """
    prof = proficiency_bonus(character)
    saves = []
    for key, short, name in ABILITIES:
        level = PROFICIENT if proficiencies.get(("save", key)) else NONE
        saves.append({"key": key, "short": short, "name": name, "level": level,
                      "total": check_total(character[key], prof, level)})
    skills = []
    for key, name, ability in SKILLS:
        level = proficiencies.get(("skill", key), NONE)
        skills.append({"key": key, "name": name, "ability": ABILITY_SHORT[ability], "level": level,
                       "total": check_total(character[ability], prof, level)})
    perception = next(s["total"] for s in skills if s["key"] == "perception")
    return {
        "proficiency": prof,
        "proficiency_is_auto": character["proficiency_bonus"] is None,
        "initiative": modifier(character["dexterity"]) + (character["initiative_bonus"] or 0),
        "passive_perception": 10 + perception,
        "saves": saves,
        "skills": skills,
    }
