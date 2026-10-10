"""Imagen de cada personaje y su icono por defecto (inicial sobre un color)."""
from datetime import datetime, timezone

from ..db import get_db
from ..images import ImageError, make_avatar
from .errors import RuleError

# Tonos oscuros que combinan con el pergamino y dejan leer la inicial en blanco
COLORS = [
    "#8b1e1e", "#2f6b3a", "#6b2f6b", "#8a5a12", "#1f5a73",
    "#5b4a8a", "#9a4d1f", "#2e5e5a", "#7a3550", "#4f5d2f",
]


def initial(name):
    """Primera letra (o número) del nombre, en mayúscula."""
    return next((ch for ch in (name or "") if ch.isalnum()), "?").upper()


def color_for(character_id):
    """Color fijo por personaje (no cambia aunque se renombre)."""
    return COLORS[(character_id or 0) % len(COLORS)]


class Avatar:
    @staticmethod
    def get(character_id):
        return get_db().execute(
            "SELECT mime, data, version FROM character_avatars WHERE character_id = ?", (character_id,)
        ).fetchone()

    @staticmethod
    def save(character_id, raw):
        """Procesa la imagen subida y la guarda (sustituye a la anterior)."""
        try:
            mime, data = make_avatar(raw)
        except ImageError as e:
            raise RuleError(str(e)) from None
        version = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f")
        db = get_db()
        db.execute(
            """INSERT INTO character_avatars (character_id, mime, data, version) VALUES (?, ?, ?, ?)
               ON CONFLICT (character_id) DO UPDATE
               SET mime = excluded.mime, data = excluded.data, version = excluded.version""",
            (character_id, mime, data, version),
        )
        db.commit()
        return len(data)

    @staticmethod
    def delete(character_id):
        db = get_db()
        db.execute("DELETE FROM character_avatars WHERE character_id = ?", (character_id,))
        db.commit()
