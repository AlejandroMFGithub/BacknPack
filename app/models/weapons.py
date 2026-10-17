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
DAMAGE_TYPES = ["contundente", "cortante", "perforante", "ácido", "frío", "fuego", "fuerza", "necrótico",
                "psíquico", "radiante", "rayo", "trueno", "veneno"]
CATEGORIES = {"simple": "Sencilla", "martial": "Marcial"}
UNARMED = {"dice": "1", "type": "contundente", "cat": None, "ranged": False, "props": [], "two": None,
           "range": None, "bonus": 0, "base": None}

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


def describe(weapon):
    """«Marcial · cuerpo a cuerpo · sutil, ligera» para los detalles del arma."""
    parts = [CATEGORIES.get(weapon.get("cat"), "Arma"), "a distancia" if weapon.get("ranged") else "cuerpo a cuerpo"]
    props = [PROPS[p] for p in weapon.get("props") or [] if p in PROPS]
    if props:
        parts.append(", ".join(props))
    return " · ".join(parts)
