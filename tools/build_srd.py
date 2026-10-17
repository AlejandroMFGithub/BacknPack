"""Genera app/data/srd_es.json (conjuros y objetos del SRD 5.1 en castellano).

Uso (solo hace falta al cambiar las traducciones de tools/srd_*_es.py):

    # descarga los JSON del SRD de https://github.com/5e-bits/5e-database (src/2014/en):
    #   5e-SRD-Spells.json, 5e-SRD-Equipment.json, 5e-SRD-Magic-Items.json  →  en una carpeta
    python tools/build_srd.py <carpeta_con_los_json>

El SRD 5.1 es de Wizards of the Coast LLC y se publica bajo CC-BY-4.0. Los textos son
resúmenes propios en castellano; los datos de juego salen del SRD.
"""
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from srd_equipment_es import DESCRIPTIONS, EQUIPMENT  # noqa: E402
from srd_magic_es import EFFECTS, GRANTS, MAGIC, VARIANTS  # noqa: E402
from srd_spells_es import SPELLS  # noqa: E402

OUT = os.path.join(HERE, "..", "app", "data", "srd_es.json")

SCHOOLS = {"Abjuration": "Abjuración", "Divination": "Adivinación", "Conjuration": "Conjuración",
           "Enchantment": "Encantamiento", "Evocation": "Evocación", "Illusion": "Ilusionismo",
           "Necromancy": "Nigromancia", "Transmutation": "Transmutación"}
UNITS = {"action": ("acción", "acciones"), "bonus action": ("acción adicional", "acciones adicionales"),
         "reaction": ("reacción", "reacciones"), "minute": ("minuto", "minutos"), "hour": ("hora", "horas"),
         "day": ("día", "días"), "round": ("asalto", "asaltos"), "mile": ("milla", "millas"),
         "turn": ("turno", "turnos")}
AREAS = {"cone": "cono", "cube": "cubo", "sphere": "esfera", "line": "línea", "cylinder": "cilindro"}
RARITY = {"Common": "Común", "Uncommon": "Poco común", "Rare": "Raro", "Very Rare": "Muy raro",
          "Legendary": "Legendario", "Artifact": "Artefacto"}
DAMAGE = {"Bludgeoning": "contundente", "Piercing": "perforante", "Slashing": "cortante"}
PROPS = {"ammunition": "munición", "finesse": "sutil", "heavy": "pesada", "light": "ligera", "loading": "recarga",
         "reach": "alcance", "special": "especial", "thrown": "arrojadiza", "two-handed": "a dos manos",
         "versatile": "versátil"}
MAGIC_CATEGORY = {"Wondrous Items": "Objeto maravilloso", "Potion": "Consumible", "Ring": "Anillo",
                  "Weapon": "Arma", "Armor": "Armadura", "Wand": "Varita", "Staff": "Bastón",
                  "Scroll": "Pergamino", "Rod": "Vara", "Ammunition": "Munición"}
# Armaduras con las que se expanden «Armadura +1/+2/+3» (una entrada por armadura)
ARMOR_KEYS = ["padded-armor", "leather-armor", "studded-leather-armor", "hide-armor", "chain-shirt", "scale-mail",
              "breastplate", "half-plate-armor", "ring-mail", "chain-mail", "splint-armor", "plate-armor"]
# Peso (lb) de la armadura base de algunos objetos mágicos
MAGIC_BASE_WEIGHT = {"elven-chain": 20, "dwarven-plate": 65, "demon-armor": 65, "plate-armor-of-etherealness": 65,
                     "armor-of-invulnerability": 65, "glamoured-studded-leather-armor": 13, "dragon-scale-mail": 45,
                     "animated-shield": 6, "arrow-catching-shield": 6, "spellguard-shield": 6,
                     "shield-of-missile-attraction": 6}


def _quantity(text):
    """«1 bonus action» → «1 acción adicional», «10 minutes» → «10 minutos»."""
    m = re.match(r"^(\d+)\s+(.+?)s?$", text.strip())
    if not m:
        return text
    n, unit = int(m.group(1)), m.group(2).lower()
    if unit not in UNITS:
        return text
    return f"{n} {UNITS[unit][0] if n == 1 else UNITS[unit][1]}"


def casting_time(text):
    return _quantity(text)


def duration(text):
    fixed = {"Instantaneous": "Instantánea", "Until dispelled": "Hasta que se disipe", "Special": "Especial",
             "Until dispelled or triggered": "Hasta que se disipe o se active"}
    if text in fixed:
        return fixed[text]
    if text.lower().startswith("up to "):
        return "Hasta " + _quantity(text[6:])
    return _quantity(text)


def spell_range(spell):
    text = spell["range"]
    base = {"Self": "Personal", "Touch": "Toque", "Sight": "A la vista", "Unlimited": "Ilimitado",
            "Special": "Especial"}.get(text)
    if base is None:
        m = re.match(r"^(\d[\d,]*) (feet|foot|miles|mile)$", text)
        if m:
            n = m.group(1).replace(",", ".")
            base = f"{n} ft" if m.group(2).startswith("f") else f"{n} {'milla' if n == '1' else 'millas'}"
        else:
            base = text
    area = spell.get("area_of_effect")
    if base == "Personal" and area:
        shape = AREAS.get(area["type"], area["type"])
        base += f" ({shape} de {area['size']} ft)"
    return base


def cost_cp(cost):
    if not cost:
        return None
    factor = {"cp": 1, "sp": 10, "ep": 50, "gp": 100, "pp": 1000}.get(cost.get("unit"), 100)
    return int(cost["quantity"] * factor)


def kg(lb):
    return round((lb or 0) / 2, 2)


def armor_text(e):
    ac = e["armor_class"]
    if e["armor_category"] == "Shield":
        return f"+{ac['base']} CA", [{"t": "armor_class", "op": "add", "v": ac["base"]}]
    if not ac["dex_bonus"]:
        text, cap = f"CA {ac['base']}", 0
    elif ac.get("max_bonus") is not None:
        text, cap = f"CA {ac['base']} + mod. DES (máx. {ac['max_bonus']})", ac["max_bonus"]
    else:
        text, cap = f"CA {ac['base']} + mod. DES", None
    kind = {"Light": "ligera", "Medium": "intermedia", "Heavy": "pesada"}[e["armor_category"]]
    parts = [text, kind]
    if e.get("str_minimum"):
        parts.append(f"FUE {e['str_minimum']}")
    if e.get("stealth_disadvantage"):
        parts.append("desventaja en Sigilo")
    return " · ".join(parts), [{"t": "armor_class", "op": "armor", "v": ac["base"], "cap": cap}]


def weapon_text(e):
    parts = []
    if e.get("damage"):
        parts.append(f"{e['damage']['damage_dice']} {DAMAGE.get(e['damage']['damage_type']['name'], '')}".strip())
    props = []
    for p in e.get("properties", []):
        if p["index"] == "monk":  # marca de esos datos, no es una propiedad del reglamento
            continue
        name = PROPS.get(p["index"], p["name"].lower())
        reach = e.get("throw_range") if p["index"] == "thrown" else e.get("range") if p["index"] == "ammunition" else None
        if reach and reach.get("long"):
            name += f" ({reach['normal']}/{reach['long']} ft)"
        if p["index"] == "versatile" and e.get("two_handed_damage"):
            name += f" ({e['two_handed_damage']['damage_dice']})"
        props.append(name)
    if props:
        parts.append(", ".join(props))
    return " · ".join(parts)


# Armas mágicas: arma base del SRD (o None si vale cualquiera) y bonificador mágico
MAGIC_WEAPONS = {
    "berserker-axe": ("battleaxe", 1), "dagger-of-venom": ("dagger", 1), "dancing-sword": ("longsword", 0),
    "defender": ("longsword", 3), "dragon-slayer": ("longsword", 1), "dwarven-thrower": ("warhammer", 3),
    "flame-tongue": ("longsword", 0), "frost-brand": ("longsword", 0), "giant-slayer": ("longsword", 1),
    "hammer-of-thunderbolts": ("maul", 1), "holy-avenger": ("longsword", 3), "javelin-of-lightning": ("javelin", 0),
    "luck-blade": ("longsword", 1), "mace-of-disruption": ("mace", 0), "mace-of-smiting": ("mace", 1),
    "mace-of-terror": ("mace", 0), "nine-lives-stealer": ("longsword", 2), "oathbow": ("longbow", 0),
    "scimitar-of-speed": ("scimitar", 2), "sun-blade": ("longsword", 2), "sword-of-life-stealing": ("longsword", 0),
    "sword-of-sharpness": ("longsword", 0), "sword-of-wounding": ("longsword", 0), "trident-of-fish-command": ("trident", 0),
    "vicious-weapon": (None, 0), "vorpal-sword": ("longsword", 3), "weapon-1": (None, 1), "weapon-2": (None, 2),
    "weapon-3": (None, 3), "staff-of-power": ("quarterstaff", 2), "staff-of-the-magi": ("quarterstaff", 2),
    "staff-of-striking": ("quarterstaff", 3), "staff-of-the-woodlands": ("quarterstaff", 2),
    "staff-of-thunder-and-lightning": ("quarterstaff", 2), "staff-of-withering": ("quarterstaff", 0),
    "staff-of-charming": ("quarterstaff", 0), "staff-of-fire": ("quarterstaff", 0), "staff-of-frost": ("quarterstaff", 0),
    "staff-of-healing": ("quarterstaff", 0), "staff-of-swarming-insects": ("quarterstaff", 0),
    "rod-of-lordly-might": ("mace", 3),
}
WEAPON_PROPS = ["finesse", "light", "heavy", "two-handed", "reach", "thrown", "ammunition", "loading", "versatile", "special"]


def weapon_data(e, bonus=0):
    """Datos de ataque de un arma del SRD (los usa la tarjeta de Ataques de la ficha)."""
    dmg = e.get("damage") or {}
    reach = e.get("throw_range") or (e.get("range") if e["weapon_range"] == "Ranged" else None)
    return {
        "dice": dmg.get("damage_dice"), "type": DAMAGE.get(dmg.get("damage_type", {}).get("name"), ""),
        "cat": "martial" if e["weapon_category"] == "Martial" else "simple",
        "ranged": e["weapon_range"] == "Ranged",
        "props": [p["index"] for p in e.get("properties", []) if p["index"] in WEAPON_PROPS],
        "two": (e.get("two_handed_damage") or {}).get("damage_dice"),
        "range": [reach["normal"], reach["long"]] if reach and reach.get("long") else None,
        "bonus": bonus, "base": EQUIPMENT[e["index"]],
    }


def equipment_category(e):
    cat = e["equipment_category"]["name"]
    if cat == "Weapon":
        return "Arma"
    if cat == "Armor":
        return "Escudo" if e["armor_category"] == "Shield" else "Armadura"
    if cat == "Tools":
        return "Herramienta"
    if cat == "Mounts and Vehicles":
        return "Montura y vehículo"
    if e.get("gear_category", {}).get("index") == "ammunition":
        return "Munición"
    return "Equipo de aventurero"


def build(src):
    load = lambda name: json.load(open(os.path.join(src, name), encoding="utf-8"))  # noqa: E731
    spells_raw = load("5e-SRD-Spells.json")
    equipment_raw = load("5e-SRD-Equipment.json")
    magic_raw = load("5e-SRD-Magic-Items.json")
    missing = []

    spells = []
    for s in spells_raw:
        if s["index"] not in SPELLS:
            missing.append(("spell", s["index"]))
            continue
        name, summary = SPELLS[s["index"]]
        spells.append({
            "srd": s["index"], "name": name, "level": s["level"], "school": SCHOOLS[s["school"]["name"]],
            "casting_time": casting_time(s["casting_time"]), "spell_range": spell_range(s),
            "components": ", ".join(s["components"]), "duration": duration(s["duration"]),
            "concentration": int(bool(s.get("concentration"))), "ritual": int(bool(s.get("ritual"))),
            "classes": [c["index"] for c in s.get("classes", [])], "description": summary,
        })

    items = []
    base = {e["index"]: e for e in equipment_raw}
    for e in equipment_raw:
        if e["index"] not in EQUIPMENT:
            missing.append(("equipment", e["index"]))
            continue
        props, effects, weapon = "", None, None
        if e["equipment_category"]["name"] == "Armor":
            props, effects = armor_text(e)
        elif e["equipment_category"]["name"] == "Weapon":
            props, weapon = weapon_text(e), weapon_data(e)
        items.append({
            "srd": e["index"], "name": EQUIPMENT[e["index"]], "category": equipment_category(e), "rarity": "Común",
            "weight": kg(e.get("weight")), "properties": props, "description": DESCRIPTIONS.get(e["index"], ""),
            "attunement": 0, "effects": effects, "cost_cp": cost_cp(e.get("cost")), "spells": [], "weapon": weapon,
        })

    for m in magic_raw:
        key = m["index"]
        if m.get("variants"):  # el padre no se importa: sus variantes sí
            continue
        attune = 1 if "requires attunement" in (m["desc"][0] if m["desc"] else "") else 0
        rarity = RARITY.get(m["rarity"]["name"], "Raro")
        category = MAGIC_CATEGORY.get(m["equipment_category"]["name"], "Objeto maravilloso")
        if "shield" in key:
            category = "Escudo"
        if key in ("armor-1", "armor-2", "armor-3"):  # una armadura +N por cada armadura base
            bonus = int(key[-1])
            for akey in ARMOR_KEYS:
                a = base[akey]
                text, eff = armor_text(a)
                eff = [dict(eff[0], v=eff[0]["v"] + bonus)]
                items.append({
                    "srd": f"{key}-{akey}", "name": f"{EQUIPMENT[akey]} +{bonus}", "category": "Armadura",
                    "rarity": rarity, "weight": kg(a.get("weight")), "properties": f"{text} · +{bonus} a la CA",
                    "description": f"Armadura mágica: +{bonus} a la CA.", "attunement": 0, "effects": eff,
                    "cost_cp": None, "spells": [], "weapon": None,
                })
            continue
        if key in VARIANTS:
            name, summary = VARIANTS[key]
            parent = key.rsplit("-", 1)[0]
            while parent and parent not in MAGIC:
                parent = parent.rsplit("-", 1)[0] if "-" in parent else ""
            summary = summary or (MAGIC[parent][1] if parent else "")
        elif key in MAGIC:
            name, summary = MAGIC[key]
            parent = key
        else:
            missing.append(("magic", key))
            continue
        weight_key = next((k for k in MAGIC_BASE_WEIGHT if key.startswith(k)), None)
        weapon = None
        if key in MAGIC_WEAPONS:
            base_key, bonus = MAGIC_WEAPONS[key]
            if base_key:
                weapon = weapon_data(base[base_key], bonus)
                if key == "sun-blade":  # hoja de luz: daño radiante
                    weapon["type"] = "radiante"
            else:
                weapon = {"dice": None, "type": "", "cat": None, "ranged": False, "props": [], "two": None,
                          "range": None, "bonus": bonus, "base": None}
        items.append({
            "srd": key, "name": name, "category": category, "rarity": rarity,
            "weight": kg(MAGIC_BASE_WEIGHT[weight_key]) if weight_key else 0,
            "properties": "", "description": summary, "attunement": attune,
            "effects": EFFECTS.get(key), "cost_cp": None, "spells": GRANTS.get(key, []), "weapon": weapon,
        })

    if missing:
        sys.exit("Sin traducción: " + ", ".join(f"{k}:{i}" for k, i in missing))
    names = [i["name"] for i in items]
    dupes = {n for n in names if names.count(n) > 1}
    if dupes:
        sys.exit("Nombres repetidos: " + ", ".join(sorted(dupes)))
    spell_keys = {s["srd"] for s in spells}
    bad = {g for i in items for g in i["spells"] if g not in spell_keys}
    if bad:
        sys.exit("Conjuros concedidos que no existen: " + ", ".join(sorted(bad)))

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    data = {
        "source": "System Reference Document 5.1 (SRD 5.1) de Wizards of the Coast LLC, CC-BY-4.0 "
                  "(https://creativecommons.org/licenses/by/4.0/). Datos estructurados: 5e-bits/5e-database (MIT). "
                  "Nombres en castellano y resúmenes propios de Back&Pack.",
        "spells": spells, "items": items,
    }
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=0, separators=(",", ":"))
    print(f"{len(spells)} conjuros y {len(items)} objetos -> {os.path.normpath(OUT)}")


if __name__ == "__main__":
    build(sys.argv[1])
