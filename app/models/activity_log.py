from ..db import get_db


class ActivityLog:
    @staticmethod
    def add(character_id, message):
        """Registra un evento. No hace commit: va dentro de la transacción del llamador."""
        get_db().execute(
            "INSERT INTO activity_log (character_id, message) VALUES (?, ?)",
            (character_id, message),
        )

    @staticmethod
    def for_character(character_id, limit=20):
        return get_db().execute(
            "SELECT * FROM activity_log WHERE character_id = ? ORDER BY id DESC LIMIT ?",
            (character_id, limit),
        ).fetchall()

    @staticmethod
    def recent(limit=30):
        return get_db().execute(
            """SELECT l.*, c.name AS character_name
               FROM activity_log l LEFT JOIN characters c ON c.id = l.character_id
               ORDER BY l.id DESC LIMIT ?""",
            (limit,),
        ).fetchall()
