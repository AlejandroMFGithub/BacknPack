"""Utilidades de texto para búsquedas."""
import unicodedata


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
