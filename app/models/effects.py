"""Efectos mecánicos de objetos, cualidades y estados (bufos, maldiciones…).

Cada efecto es un dict {"t": estadística, "op": operación, "v": valor[, "cap": límite de DES]}
y se guarda como JSON en la columna `effects` de items, item_traits y conditions.

Operaciones (en este orden se aplican):
  armor  la CA base pasa a ser «v + mod. DES» (con «cap» como máximo de DES; 0 = sin DES)
  floor  como mínimo v (p. ej. guanteletes de fuerza de ogro: FUE 19)
  add    suma v (negativo resta)
  mul    multiplica por v (p. ej. velocidad ×½)
  set    fija en v (p. ej. velocidad 0)
"""
import json

from .errors import RuleError
from .rules import ABILITIES, SKILLS

OPS = {
    "add": "+/−",
    "set": "= (fija)",
    "floor": "mínimo",
    "mul": "× (multiplica)",
    "armor": "armadura (CA base)",
}

# Estadísticas que se pueden modificar: (clave, etiqueta)
TARGETS = (
    [(key, short) for key, short, _ in ABILITIES]
    + [
        ("armor_class", "CA"),
        ("speed", "Velocidad"),
        ("initiative", "Iniciativa"),
        ("hp_max", "PG máximos"),
        ("passive_perception", "Percepción pasiva"),
        ("spell_dc", "CD de conjuros"),
        ("spell_attack", "Ataque de conjuro"),
        ("saves", "Todas las salvaciones"),
        ("skills", "Todas las habilidades"),
    ]
    + [(f"save:{key}", f"Salvación de {name}") for key, _, name in ABILITIES]
    + [(f"skill:{key}", name) for key, name, _ in SKILLS]
)
TARGET_LABELS = dict(TARGETS)
# Para el desplegable del editor: (grupo, [(clave, etiqueta)])
TARGET_GROUPS = [
    ("Características", [t for t in TARGETS if t[0] in {k for k, _, _ in ABILITIES}]),
    ("Combate y magia", [t for t in TARGETS if ":" not in t[0] and t[0] not in {k for k, _, _ in ABILITIES}]),
    ("Una salvación", [t for t in TARGETS if t[0].startswith("save:")]),
    ("Una habilidad", [t for t in TARGETS if t[0].startswith("skill:")]),
]
# Límite del modificador de DES en armaduras: ligera sin límite, intermedia máx. 2, pesada sin DES
CAP_OPTIONS = [("none", "+ DES (sin límite)"), ("2", "+ DES (máx. 2)"), ("3", "+ DES (máx. 3)"), ("0", "sin DES")]

# Estados del reglamento con efecto mecánico: si no se indican efectos, se aplican estos
CONDITION_PRESETS = {
    "Agarrado": [{"t": "speed", "op": "set", "v": 0}],
    "Apresado": [{"t": "speed", "op": "set", "v": 0}],
    "Paralizado": [{"t": "speed", "op": "set", "v": 0}],
    "Petrificado": [{"t": "speed", "op": "set", "v": 0}],
    "Inconsciente": [{"t": "speed", "op": "set", "v": 0}],
    "Agotamiento (nivel 2)": [{"t": "speed", "op": "mul", "v": 0.5}],
    "Agotamiento (nivel 5)": [{"t": "speed", "op": "set", "v": 0}],
    "Prisa": [{"t": "armor_class", "op": "add", "v": 2}, {"t": "speed", "op": "mul", "v": 2}],
    "Ralentizar": [{"t": "armor_class", "op": "add", "v": -2}, {"t": "speed", "op": "mul", "v": 0.5}],
    "Escudo de fe": [{"t": "armor_class", "op": "add", "v": 2}],
    "Paso largo": [{"t": "speed", "op": "add", "v": 10}],
}


def _number(value):
    value = float(str(value).replace(",", "."))
    return int(value) if value == int(value) else value


def clean(effects):
    """Valida una lista de efectos; descarta los incompletos. RuleError si alguno no tiene sentido."""
    result = []
    for e in effects or []:
        target, op = e.get("t"), e.get("op")
        if target not in TARGET_LABELS or op not in OPS or e.get("v") in (None, ""):
            continue
        try:
            value = _number(e["v"])
        except (TypeError, ValueError):
            raise RuleError(f"El valor del efecto sobre {TARGET_LABELS[target]} no es un número.") from None
        effect = {"t": target, "op": op, "v": value}
        if op == "armor":
            if target != "armor_class":
                raise RuleError("La operación «armadura» solo vale para la CA.")
            cap = e.get("cap")
            effect["cap"] = None if cap in (None, "", "none") else int(cap)
        if op == "mul" and value < 0:
            raise RuleError("No se puede multiplicar por un número negativo.")
        result.append(effect)
    return result


def from_form(data):
    """Lee las filas del editor de efectos (eff_t, eff_op, eff_v, eff_cap) de un formulario."""
    if hasattr(data, "getlist"):
        rows = zip(data.getlist("eff_t"), data.getlist("eff_op"), data.getlist("eff_v"), data.getlist("eff_cap"))
        return clean({"t": t, "op": op, "v": v, "cap": cap} for t, op, v, cap in rows)
    return clean(data.get("effects") or [])  # dict (datos de ejemplo, pruebas)


def dumps(effects):
    return json.dumps(effects, ensure_ascii=False, separators=(",", ":")) if effects else None


def loads(text):
    try:
        return json.loads(text) if text else []
    except ValueError:
        return []


def _fmt(value):
    if isinstance(value, float):
        return {0.5: "½", 0.25: "¼"}.get(value, f"{value:g}".replace(".", ","))
    return str(value)


def describe(effect):
    """Texto corto de un efecto: «CA +2», «Velocidad = 0», «CA 16 + DES (máx. 2)»…"""
    label, op, value = TARGET_LABELS.get(effect["t"], effect["t"]), effect["op"], effect["v"]
    if op == "add":
        unit = " ft" if effect["t"] == "speed" else ""
        return f"{label} {value:+g}{unit}".replace("-", "−")
    if op == "set":
        return f"{label} = {_fmt(value)}"
    if op == "floor":
        return f"{label} mín. {_fmt(value)}"
    if op == "mul":
        return f"{label} ×{_fmt(value)}"
    cap = effect.get("cap")
    dex = "" if cap == 0 else (" + DES" if cap is None else f" + DES (máx. {cap})")
    return f"CA {_fmt(value)}{dex}"


def summary(text):
    """Resumen legible de la columna effects (JSON): «CA +2 · FUE −1»."""
    return " · ".join(describe(e) for e in loads(text))


HIDDEN_SOURCE = "??? (efecto oculto)"


def active(character_id, show_hidden=False):
    """Efectos que pesan ahora sobre un personaje, cada uno con su origen ("source").

    Cuentan los estados activos, los objetos equipados y las cualidades de esos objetos.
    Lo oculto también se aplica: el jugador ve «???» como origen y el DM el nombre real.
    """
    return active_many([character_id], show_hidden)[character_id]


def active_many(character_ids, show_hidden=False):
    """{character_id: [efectos]} con tres consultas en total, para listas de personajes."""
    from ..db import get_db
    ids = list(character_ids)
    found = {cid: [] for cid in ids}
    if not ids:
        return found
    marks = ",".join("?" for _ in ids)
    db = get_db()
    queries = [
        f"""SELECT character_id, name, visible, effects, 0 AS kind, id FROM conditions
            WHERE character_id IN ({marks}) AND active = 1 AND effects IS NOT NULL""",
        f"""SELECT ii.character_id, i.name, ii.visible, i.effects, 1 AS kind, ii.id
            FROM inventory_items ii JOIN items i ON i.id = ii.item_id
            WHERE ii.character_id IN ({marks}) AND ii.equipped = 1 AND i.effects IS NOT NULL""",
        f"""SELECT ii.character_id, t.name || ' (' || i.name || ')' AS name, t.visible * ii.visible AS visible,
                   t.effects, 2 AS kind, t.id
            FROM item_traits t JOIN inventory_items ii ON ii.id = t.inventory_item_id
            JOIN items i ON i.id = ii.item_id
            WHERE ii.character_id IN ({marks}) AND ii.equipped = 1 AND t.effects IS NOT NULL""",
    ]
    rows = [row for sql in queries for row in db.execute(sql, tuple(ids)).fetchall()]
    rows.sort(key=lambda r: (r["kind"], r["id"]))
    for row in rows:
        if row["visible"]:
            label = row["name"]
        else:
            label = f"{row['name']} (oculto)" if show_hidden else HIDDEN_SOURCE
        for effect in loads(row["effects"]):
            found[row["character_id"]].append({**effect, "source": label})
    return found


def sheets_for(characters, show_hidden=False):
    """{id: ficha calculada} de varios personajes (sin competencias: para CA, velocidad… en listas)."""
    from .rules import sheet
    characters = list(characters)
    effects = active_many([c["id"] for c in characters], show_hidden)
    return {c["id"]: sheet(c, {}, effects[c["id"]]) for c in characters}
