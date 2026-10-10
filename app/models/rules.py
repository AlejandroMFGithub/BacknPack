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


# --- Estadísticas modificadas por equipo y efectos --------------------------------------------

def _signed(value):
    return f"{value:+g}".replace("-", "−")


class Stat:
    """Un valor de la ficha con su cálculo paso a paso.

    sign: None (sin modificar por equipo/efectos), "up", "down" o "mixed".
    lines: [(texto, valor)] para mostrar la operación al pasar el ratón o tocar.
    """

    def __init__(self, base, base_label, inherited=()):
        self.total = base
        self.lines = [(base_label, base)]
        self.signs = set(inherited)

    def step(self, text, value, counts=True):
        """Añade un paso. Si viene de equipo o efectos (counts), suma al color."""
        before, self.total = self.total, value
        if counts and value != before:
            self.signs.add("up" if value > before else "down")
        self.lines.append((text, value))

    @property
    def sign(self):
        if not self.signs:
            return None
        return "mixed" if len(self.signs) > 1 else next(iter(self.signs))

    @property
    def modified(self):
        return bool(self.signs)

    def __int__(self):
        return int(self.total)

    def __str__(self):
        return str(self.total)


def _apply(stat, effects):
    """Aplica floor/add/mul/set (la armadura se resuelve aparte) en su orden."""
    order = {"floor": 0, "add": 1, "mul": 2, "set": 3}
    for e in sorted((e for e in effects if e["op"] in order), key=lambda e: order[e["op"]]):
        v, op, src = e["v"], e["op"], e["source"]
        if op == "add":
            stat.step(f"{_signed(v)} · {src}", stat.total + v)
        elif op == "floor":
            new = max(stat.total, v)
            stat.step(f"mínimo {v:g} · {src}" + ("" if new != stat.total else " (sin efecto)"), new)
        elif op == "mul":
            stat.step(f"×{v:g} · {src}".replace(".", ","), int(stat.total * v))
        else:
            stat.step(f"= {v:g} · {src}", v)
    return stat


def sheet(character, proficiencies, effects=()):
    """Todos los valores calculados de la ficha, con equipo y efectos aplicados.

    proficiencies: {("save"|"skill", clave): 1 (competencia) o 2 (pericia)}
    effects: [{"t", "op", "v", "cap"?, "source"}] activos (objetos equipados, estados…)
    """
    by_target = {}
    for e in effects:
        by_target.setdefault(e["t"], []).append(e)
    get = lambda target: by_target.get(target, [])  # noqa: E731

    # Características (todo lo demás depende de ellas)
    abilities = {}
    for key, short, name in ABILITIES:
        abilities[key] = _apply(Stat(character[key], f"{name} base"), get(key))
    mods = {key: modifier(stat.total) for key, stat in abilities.items()}

    def ability_line(key):
        """«Mod. DES +3» y, si la característica está modificada, cuánto vale ahora."""
        st = abilities[key]
        extra = f" ({ABILITY_SHORT[key]} {st.total} modificada)" if st.modified else ""
        return f"Mod. {ABILITY_SHORT[key]}{extra}", st.signs

    prof = proficiency_bonus(character)

    # CA: sin armadura (la de la ficha) o la mejor armadura equipada, y luego el resto
    ac = Stat(character["armor_class"], "CA sin armadura (ficha)")
    armors = [e for e in get("armor_class") if e["op"] == "armor"]
    if armors:
        def armor_value(e):
            dex = mods["dexterity"] if e.get("cap") is None else min(mods["dexterity"], e["cap"])
            return e["v"] + dex
        best = max(armors, key=armor_value)
        uses_dex = best.get("cap") != 0
        cap_txt = "" if not uses_dex else (" + DES" if best.get("cap") is None else f" + DES (máx. {best['cap']})")
        ac.step(f"Armadura: {best['v']}{cap_txt} · {best['source']}", armor_value(best))
        if uses_dex:
            ac.signs |= abilities["dexterity"].signs
    _apply(ac, get("armor_class"))

    speed = _apply(Stat(character["speed"], "Velocidad base (ft)"), get("speed"))
    hp_max = _apply(Stat(character["hp_max"], "PG máximos (ficha)"), get("hp_max"))

    label, inherited = ability_line("dexterity")
    initiative = Stat(mods["dexterity"], f"{label}", inherited)
    if character["initiative_bonus"]:
        initiative.step(f"{_signed(character['initiative_bonus'])} bonus extra (ficha)",
                        initiative.total + character["initiative_bonus"], counts=False)
    _apply(initiative, get("initiative"))

    saves = []
    for key, short, name in ABILITIES:
        level = PROFICIENT if proficiencies.get(("save", key)) else NONE
        label, inherited = ability_line(key)
        st = Stat(mods[key], label, inherited)
        if level:
            st.step(f"+{prof} competencia", st.total + prof, counts=False)
        _apply(st, get("saves") + get(f"save:{key}"))
        saves.append({"key": key, "short": short, "name": name, "level": level, "total": st.total, "stat": st})

    skills = []
    for key, name, ability in SKILLS:
        level = proficiencies.get(("skill", key), NONE)
        label, inherited = ability_line(ability)
        st = Stat(mods[ability], label, inherited)
        if level:
            st.step(f"+{prof * level} {'pericia' if level == EXPERTISE else 'competencia'}",
                    st.total + prof * level, counts=False)
        _apply(st, get("skills") + get(f"skill:{key}"))
        skills.append({"key": key, "name": name, "ability": ABILITY_SHORT[ability], "level": level,
                       "total": st.total, "stat": st})

    perception = next(s["stat"] for s in skills if s["key"] == "perception")
    passive = Stat(10 + perception.total, f"10 + Percepción ({_signed(perception.total)})", perception.signs)
    _apply(passive, get("passive_perception"))

    return {
        "proficiency": prof,
        "proficiency_is_auto": character["proficiency_bonus"] is None,
        "abilities": abilities,
        "mods": mods,
        "armor_class": ac,
        "speed": speed,
        "hp_max": hp_max,
        "initiative": initiative,
        "passive_perception": passive,
        "carry_max": abilities["strength"].total * 7.5,
        "saves": saves,
        "skills": skills,
    }
