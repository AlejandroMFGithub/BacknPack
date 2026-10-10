"""Utilidades de texto: búsquedas y distancias."""
import re
import unicodedata

# --- Distancias: siempre en pies y casillas (1 casilla = 5 ft = 1,5 m, convención de 5e) ---

FEET_PER_SQUARE = 5
_NUM = r"\d+(?:[.,]\d+)?"
# «6 m», «24/96 m», «15 metros»  (la «m» sola, no «min» ni «mas»)
_METERS = re.compile(rf"({_NUM})(?:\s*/\s*({_NUM}))?\s*(?:m\b|[Mm]etros?\b)")
# «30 ft», «20/60 pies»… que aún no lleven sus casillas detrás
_FEET = re.compile(
    rf"({_NUM})(?:\s*/\s*({_NUM}))?\s*(?:ft|pies?|feet|foot)\b(?!\s*/\s*{_NUM}(?:\s*/\s*{_NUM})?\s*casillas?)",
    re.IGNORECASE,
)


def _number(text):
    return float(text.replace(",", "."))


def _clean_number(value):
    """30.0 -> «30», 2.4 -> «2,4»."""
    value = round(value, 1)
    return str(int(value)) if value == int(value) else f"{value:.1f}".replace(".", ",")


def meters_to_feet(meters):
    """9 m -> 30 ft. Redondea a múltiplos de 5 (casillas enteras) salvo distancias muy cortas."""
    feet = meters * 10 / 3
    return round(feet / FEET_PER_SQUARE) * FEET_PER_SQUARE if feet >= 4 else round(feet)


def format_feet(feet, feet_end=None):
    """30 -> «30 ft / 6 casillas»; (20, 60) -> «20/60 ft / 4/12 casillas»."""
    if feet_end is None:
        squares = feet / FEET_PER_SQUARE
        return f"{_clean_number(feet)} ft / {_clean_number(squares)} casilla{'' if squares == 1 else 's'}"
    return (f"{_clean_number(feet)}/{_clean_number(feet_end)} ft / "
            f"{_clean_number(feet / FEET_PER_SQUARE)}/{_clean_number(feet_end / FEET_PER_SQUARE)} casillas")


def distances(text):
    """Pasa a «X ft / N casillas» todas las distancias de un texto (metros o pies sin casillas).
    Se puede aplicar varias veces: lo que ya está en ese formato no cambia."""
    if not text:
        return text

    def from_meters(match):
        start, end = match.group(1), match.group(2)
        return format_feet(meters_to_feet(_number(start)), meters_to_feet(_number(end)) if end else None)

    def from_feet(match):
        start, end = match.group(1), match.group(2)
        return format_feet(_number(start), _number(end) if end else None)

    return _FEET.sub(from_feet, _METERS.sub(from_meters, text))


def normalize(text):
    """Minúsculas y sin tildes: «Poción» -> «pocion». Se usa al guardar y al buscar."""
    decomposed = unicodedata.normalize("NFKD", text or "")
    return "".join(c for c in decomposed if not unicodedata.combining(c)).casefold().strip()


def like_contains(query):
    """Patrón LIKE «contiene» para el texto normalizado, con los comodines escapados.
    Úsese con LIKE_ESCAPE."""
    q = normalize(query).replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{q}%"


def like_terms(query):
    """Un patrón «contiene» por palabra: todas deben aparecer, en cualquier orden.
    «pocion cur» encuentra «Poción de curación»."""
    return [like_contains(word) for word in normalize(query).split()]


def matches_all_words(query, text):
    """Lo mismo que like_terms, pero en Python (listas cortas ya cargadas)."""
    haystack = normalize(text)
    return all(word in haystack for word in normalize(query).split())


def like_prefix(query):
    q = normalize(query).replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"{q}%"


LIKE_ESCAPE = " ESCAPE '\\'"
