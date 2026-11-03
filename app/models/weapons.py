"""Armas: sus datos de ataque y la competencia del personaje con ellas.

Cada arma del catálogo guarda en items.weapon (JSON):
  {"dice": "1d8", "type": "cortante", "cat": "simple"|"martial"|None, "ranged": bool,
   "props": ["finesse", …], "two": "1d10" (versátil), "range": [20, 60], "bonus": 0..3, "base": "Espada larga"}
El cálculo del ataque está en rules.weapon_attack.
"""
import json

from ..text import normalize
from .errors import RuleError

PROPS = {
    "finesse": "sutil", "light": "ligera", "heavy": "pesada", "two-handed": "a dos manos", "reach": "alcance",
    "thrown": "arrojadiza", "ammunition": "munición", "loading": "recarga", "versatile": "versátil",
    "special": "especial",
}
PROP_HELP = {
    "finesse": "Ataca y daña con la mejor de FUE o DES.",
    "light": "Permite atacar también con otra arma ligera en la otra mano.",
    "heavy": "Las criaturas pequeñas tienen desventaja al usarla.",
    "two-handed": "Hay que usarla con las dos manos.",
    "reach": "Alcance cuerpo a cuerpo de 10 ft.",
    "thrown": "Se puede lanzar; usa la misma característica.",
    "ammunition": "Dispara munición; alcance a distancia.",
    "loading": "Solo un ataque por acción, aunque tengas más.",
    "versatile": "A dos manos hace más daño (indica cuánto).",
    "special": "Tiene reglas propias (explícalas en la descripción).",
}
DAMAGE_TYPES = ["contundente", "cortante", "perforante", "ácido", "frío", "fuego", "fuerza", "necrótico",
                "psíquico", "radiante", "rayo", "trueno", "veneno"]
CATEGORIES = {"simple": "Sencilla", "martial": "Marcial"}
# Maestrías de arma (reglamento 2024, SRD 5.2): nombre y efecto (resumen propio)
MASTERIES = {
    "cleave": ("Hendir", "Si impactas, puedes hacer un segundo ataque contra otra criatura a 5 ft del objetivo "
                         "(una vez por turno; ese daño no suma tu modificador)."),
    "graze": ("Rozar", "Si fallas, el objetivo recibe igualmente daño igual a tu modificador de característica."),
    "nick": ("Mellar", "El ataque extra de la propiedad ligera lo haces dentro de la acción de Atacar (una vez por turno)."),
    "push": ("Empujar", "Si impactas, puedes empujar al objetivo hasta 10 ft (Grande o menor)."),
    "sap": ("Debilitar", "Si impactas, el objetivo tiene desventaja en su siguiente tirada de ataque."),
    "slow": ("Ralentizar", "Si impactas y haces daño, el objetivo tiene −10 ft de velocidad hasta tu siguiente turno."),
    "topple": ("Derribar", "Si impactas, el objetivo hace una salvación de CON o cae derribado."),
    "vex": ("Incordiar", "Si impactas y haces daño, tienes ventaja en tu siguiente ataque contra ese objetivo."),
}
UNARMED = {"dice": "1", "type": "contundente", "cat": None, "ranged": False, "props": [], "two": None,
           "range": None, "bonus": 0, "base": None, "mastery": None, "extra": []}

# «armas de druida» (competencias del druida)
_DRUID = {"garrote", "daga", "dardo", "jabalina", "maza", "baston", "cimitarra", "hoz", "honda", "lanza"}
_SMALL_WORDS = {"de", "del", "la", "el", "a", "y"}


def loads(text):
    try:
        data = json.loads(text) if text else None
    except ValueError:
        return None
    return data if isinstance(data, dict) else None


def dumps(weapon):
    return json.dumps(weapon, ensure_ascii=False, separators=(",", ":")) if weapon else None


def _dice(text):
    text = (text or "").strip().lower().replace(" ", "")
    if not text:
        return None
    if text.isdigit() or (text.count("d") == 1 and all(p.isdigit() for p in text.split("d"))):
        return text
    raise RuleError(f"«{text}» no es un dado válido (p. ej. 1d8 o 2d6).")


def from_form(data):
    """Lee el bloque «Arma» del formulario del catálogo. None si no es un arma."""
    if not data.get("w_enabled"):
        return None
    props = [p for p in (data.getlist("w_props") if hasattr(data, "getlist") else data.get("w_props") or [])
             if p in PROPS]
    try:
        bonus = max(0, min(int(data.get("w_bonus") or 0), 5))
        normal, long_ = int(data.get("w_range_normal") or 0), int(data.get("w_range_long") or 0)
    except ValueError:
        raise RuleError("El bonificador y el alcance del arma deben ser números.") from None
    getlist = data.getlist if hasattr(data, "getlist") else (lambda k: data.get(k) or [])
    extra = []
    for dice, kind, note in zip(getlist("w_extra_dice"), getlist("w_extra_type"), getlist("w_extra_note")):
        if (dice or "").strip():
            extra.append({"dice": _dice(dice), "type": kind if kind in DAMAGE_TYPES else "",
                          "note": (note or "").strip()[:80]})
    return {
        "dice": _dice(data.get("w_dice")),
        "type": data.get("w_type") if data.get("w_type") in DAMAGE_TYPES else "",
        "cat": data.get("w_cat") if data.get("w_cat") in CATEGORIES else None,
        "ranged": bool(data.get("w_ranged")),
        "props": props,
        "two": _dice(data.get("w_two")) if "versatile" in props else None,
        "range": [normal, max(long_, normal)] if normal else None,
        "bonus": bonus,
        "base": (data.get("w_base") or "").strip() or None,
        "mastery": data.get("w_mastery") if data.get("w_mastery") in MASTERIES else None,
        "extra": extra,
    }


def _plural(name):
    words = []
    for w in name.split():
        if w in _SMALL_WORDS:
            words.append(w)
        else:
            words.append(w + ("s" if w[-1] in "aeiou" else "es"))
    return " ".join(words)


def auto_proficient(character, weapon, item_name):
    """¿Es competente según las competencias de su clase? Sin clase conocida se supone que sí."""
    text = normalize(character["class_proficiencies"] or "")
    if not text or weapon.get("cat") is None:
        return True
    if "marcial" in text:
        return True
    if weapon["cat"] == "simple" and "sencilla" in text:
        return True
    for name in filter(None, (weapon.get("base"), item_name)):
        n = normalize(name)
        if n in text or _plural(n) in text:
            return True
        if "druida" in text and n in _DRUID:
            return True
    return False


def summary(weapon):
    """Texto de propiedades generado a partir de los datos del arma:
    «1d8 cortante · versátil (1d10) · arrojadiza (20/60 ft) · maestría: Debilitar · +2d6 fuego (con la hoja encendida)»."""
    parts = []
    if weapon.get("dice"):
        parts.append(f"{weapon['dice']} {weapon.get('type') or ''}".strip())
    props = []
    for p in weapon.get("props") or []:
        text = PROPS.get(p, p)
        if p in ("thrown", "ammunition") and weapon.get("range"):
            text += f" ({weapon['range'][0]}/{weapon['range'][1]} ft)"
        if p == "versatile" and weapon.get("two"):
            text += f" ({weapon['two']})"
        props.append(text)
    if weapon.get("ranged") and weapon.get("range") and not ({"thrown", "ammunition"} & set(weapon.get("props") or [])):
        props.append(f"alcance {weapon['range'][0]}/{weapon['range'][1]} ft")
    if props:
        parts.append(", ".join(props))
    if weapon.get("bonus"):
        parts.append(f"+{weapon['bonus']} al ataque y al daño")
    if weapon.get("mastery") in MASTERIES:
        parts.append(f"maestría: {MASTERIES[weapon['mastery']][0]}")
    for e in weapon.get("extra") or []:
        parts.append(f"+{e['dice']} {e.get('type') or ''}".strip() + (f" ({e['note']})" if e.get("note") else ""))
    return " · ".join(parts)


def describe(weapon):
    """«Marcial · cuerpo a cuerpo · sutil, ligera» para los detalles del arma."""
    parts = [CATEGORIES.get(weapon.get("cat"), "Arma"), "a distancia" if weapon.get("ranged") else "cuerpo a cuerpo"]
    props = [PROPS[p] for p in weapon.get("props") or [] if p in PROPS]
    if props:
        parts.append(", ".join(props))
    return " · ".join(parts)
